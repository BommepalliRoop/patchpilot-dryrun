"""The only place that calls a model (T04). Prompts live in `app/prompts/<name>.md`; outputs are validated JSON."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import weakref
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import BACKEND_DIR, get_settings
from app.core.security import redact

logger = logging.getLogger("patchpilot.llm")

T = TypeVar("T", bound=BaseModel)

PROMPTS_DIR = BACKEND_DIR / "app" / "prompts"
TIMEOUT_S = 60
MAX_RETRIES = 3          # N1: 429 / 5xx / transport errors, backoff 1 s, 2 s, 4 s
MAX_CONCURRENCY = 4      # N1
MAX_RETRY_AFTER_S = 30
MAX_OUTPUT_TOKENS = 4096
ANTHROPIC_URL = "https://api.anthropic.com"
OPENAI_URL = "https://api.openai.com/v1"
AZURE_API_VERSION = "2024-10-21"

_PROMPT_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_VARIABLE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

_semaphores: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = weakref.WeakKeyDictionary()


class LLMError(Exception):
    """Provider failed or output stayed invalid after retries. Callers use their safe fallback (RISKS N1, E9)."""


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    sem = _semaphores.get(loop)
    if sem is None:
        sem = _semaphores[loop] = asyncio.Semaphore(MAX_CONCURRENCY)
    return sem


def _check_name(prompt_name: str) -> None:
    if not _PROMPT_NAME.match(prompt_name):
        raise LLMError(f"invalid prompt name: {prompt_name!r}")


def render_prompt(prompt_name: str, variables: dict[str, Any]) -> str:
    """Fill `{{variables}}` in a single pass, so substituted values are never re-expanded."""
    _check_name(prompt_name)
    path = PROMPTS_DIR / f"{prompt_name}.md"
    try:
        template = path.read_text(encoding="utf-8")
    except OSError as e:
        raise LLMError(f"prompt not found: {prompt_name}") from e

    def fill(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in variables:
            raise LLMError(f"prompt {prompt_name} needs variable {key!r}")
        value = variables[key]
        return value if isinstance(value, str) else json.dumps(value, default=str)

    return _VARIABLE.sub(fill, template)


def extract_json(text: str) -> Any:
    """Parse the model reply: raw JSON, a ```json fenced block, or JSON surrounded by prose."""
    text = (text or "").strip()
    if not text:
        raise ValueError("empty response")
    candidates = [text]
    candidates += [m.strip() for m in _FENCE.findall(text)]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    last: Exception | None = None
    for c in candidates:
        try:
            return json.loads(c)
        except ValueError as e:
            last = e
    raise ValueError(f"no valid JSON in response: {last}")


# --- providers -----------------------------------------------------------------------------------------------

def _is_azure(base_url: str) -> bool:
    return "openai.azure.com" in base_url or "cognitiveservices.azure.com" in base_url


def _build_request(prompt: str) -> tuple[str, dict[str, str], dict[str, Any]]:
    s = get_settings()
    base = s.llm_base_url.rstrip("/")
    if s.llm_provider == "anthropic":
        url = f"{base or ANTHROPIC_URL}/v1/messages"
        headers = {"x-api-key": s.llm_api_key, "anthropic-version": "2023-06-01"}
        body = {"model": s.llm_model, "max_tokens": MAX_OUTPUT_TOKENS, "temperature": 0,
                "messages": [{"role": "user", "content": prompt}]}
        return url, headers, body
    body = {"model": s.llm_model, "temperature": 0, "messages": [{"role": "user", "content": prompt}]}
    if _is_azure(base):
        # Azure OpenAI: `api-key` header + deployment URL (the deployment is named by LLM_MODEL).
        url = base if "/chat/completions" in base else (
            f"{base}/openai/deployments/{s.llm_model}/chat/completions?api-version={AZURE_API_VERSION}")
        return url, {"api-key": s.llm_api_key}, body
    return f"{base or OPENAI_URL}/chat/completions", {"Authorization": f"Bearer {s.llm_api_key}"}, body


def _parse_response(data: dict[str, Any]) -> tuple[str, int, int]:
    """-> (text, input_tokens, output_tokens)"""
    usage = data.get("usage") or {}
    if get_settings().llm_provider == "anthropic":
        text = "".join(b.get("text", "") for b in data.get("content") or [] if b.get("type") == "text")
        return text, usage.get("input_tokens", 0), usage.get("output_tokens", 0)
    choices = data.get("choices") or []
    text = ((choices[0].get("message") or {}).get("content") or "") if choices else ""
    return text, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)


def _retry_delay(attempt: int, response: httpx.Response | None) -> float:
    delay = float(2 ** attempt)  # 1, 2, 4
    if response is not None:
        try:
            delay = max(delay, float(response.headers.get("retry-after", "")))
        except ValueError:
            pass
    return min(delay, MAX_RETRY_AFTER_S)


async def _call_provider(prompt: str, prompt_name: str) -> str:
    """One provider call with N1 retries. Returns the reply text; logs tokens and latency (O2)."""
    s = get_settings()
    if not s.llm_api_key or not s.llm_model:
        raise LLMError("LLM_API_KEY and LLM_MODEL must be set when LLM_MODE=live")
    url, headers, body = _build_request(prompt)
    last = "unknown error"
    async with _semaphore():
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            for attempt in range(MAX_RETRIES + 1):
                started = time.monotonic()
                response: httpx.Response | None = None
                try:
                    response = await client.post(url, headers=headers, json=body)
                    if response.status_code == 429 or response.status_code >= 500:
                        last = f"HTTP {response.status_code}"
                    elif response.status_code >= 400:
                        raise LLMError(f"provider rejected the request: HTTP {response.status_code}"
                                       f" {redact(response.text[:200])}")
                    else:
                        text, tok_in, tok_out = _parse_response(response.json())
                        logger.info("llm call prompt=%s provider=%s model=%s tokens_in=%d tokens_out=%d latency_ms=%d",
                                    prompt_name, s.llm_provider, s.llm_model, tok_in, tok_out,
                                    (time.monotonic() - started) * 1000)
                        return text
                except httpx.HTTPError as e:
                    last = f"{type(e).__name__}"
                    response = None
                except ValueError as e:  # body was not JSON
                    last = "non-JSON provider response"
                    response = None
                    logger.warning("llm prompt=%s bad provider body: %s", prompt_name, redact(e))
                if attempt == MAX_RETRIES:
                    break
                delay = _retry_delay(attempt, response)
                logger.warning("llm prompt=%s attempt=%d failed (%s), retrying in %.1fs",
                               prompt_name, attempt + 1, last, delay)
                await _sleep(delay)
    raise LLMError(f"LLM unavailable after {MAX_RETRIES + 1} attempts: {last}")


# --- public API ----------------------------------------------------------------------------------------------

def _mock(prompt_name: str, schema: type[T]) -> T:
    _check_name(prompt_name)
    path = PROMPTS_DIR / "mocks" / f"{prompt_name}.json"
    try:
        obj = schema.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise LLMError(f"no mock for prompt {prompt_name}") from e
    except ValidationError as e:
        raise LLMError(f"mock for {prompt_name} does not match {schema.__name__}: {e}") from e
    logger.info("llm call prompt=%s mode=mock tokens_in=0 tokens_out=0 latency_ms=0", prompt_name)
    return obj


async def complete_json(prompt_name: str, variables: dict[str, Any], schema: type[T]) -> T:
    """Fill `{{variables}}` in `prompts/<prompt_name>.md`, call the provider, parse + validate JSON as `schema`.

    Invalid JSON -> one retry with the validation error appended, then raises so the caller uses its safe fallback.
    `LLM_MODE=mock` returns canned JSON from `prompts/mocks/<prompt_name>.json`.
    """
    if get_settings().llm_mode == "mock":
        return _mock(prompt_name, schema)

    prompt = render_prompt(prompt_name, variables)
    error = ""
    for attempt in range(2):  # E9: first try + one retry with the validation error
        text = await _call_provider(prompt if not error else
                                    f"{prompt}\n\nYour previous reply was invalid: {error}\n"
                                    "Reply again with valid JSON only, matching the requested shape.", prompt_name)
        try:
            return schema.model_validate(extract_json(text))
        except (ValueError, ValidationError) as e:  # ValidationError is a ValueError; kept explicit for clarity
            error = redact(str(e))[:500]
            logger.warning("llm prompt=%s attempt=%d invalid output: %s", prompt_name, attempt + 1, error)
    raise LLMError(f"AI output invalid after retry for {prompt_name}: {error}")
