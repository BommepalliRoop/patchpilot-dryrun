"""T04 LLM client: mock mode, JSON extraction, retry on invalid output (E9), 429/5xx backoff (N1), logging (O2)."""
from __future__ import annotations

import asyncio
import json
import logging

import httpx
import pytest
from pydantic import BaseModel

from app.core.config import reset_settings_cache
from app.services import llm
from app.services.llm import LLMError


class Symbols(BaseModel):
    package: str
    import_names: list[str] = []
    symbols: list[str] = []
    safe_usage_notes: str = ""
    confidence: float


class Verdict(BaseModel):
    reachability: str
    confidence: float
    explanation: str


class Patch(BaseModel):
    diff: str
    explanation: str


class PrText(BaseModel):
    title: str
    body: str


GOOD = {"package": "PyYAML", "import_names": ["yaml"], "symbols": ["yaml.load"], "confidence": 0.8}
SYM_VARS = {"ecosystem": "PyPI", "package": "PyYAML", "cve_id": "CVE-1", "summary": "s", "details": "d", "references": []}
KEY = "sk-test-secret-123456"


def live(monkeypatch, provider="anthropic", base="", model="m"):
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv("LLM_API_KEY", KEY)
    monkeypatch.setenv("LLM_MODEL", model)
    monkeypatch.setenv("LLM_BASE_URL", base)
    reset_settings_cache()


def serve(monkeypatch, handler):
    """Route every httpx call in llm.py to `handler`; no network, no real sleeping."""
    real = httpx.AsyncClient

    def factory(*a, **kw):
        kw["transport"] = httpx.MockTransport(handler)
        return real(*a, **kw)

    monkeypatch.setattr(llm.httpx, "AsyncClient", factory)
    delays: list[float] = []

    async def fake_sleep(s):
        delays.append(s)

    monkeypatch.setattr(llm, "_sleep", fake_sleep)
    return delays


def anthropic_reply(text: str, status=200, headers=None):
    return httpx.Response(status, headers=headers,
                          json={"content": [{"type": "text", "text": text}],
                                "usage": {"input_tokens": 11, "output_tokens": 7}})


# --- mock mode ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name,schema", [("extract_symbols", Symbols), ("reachability_verdict", Verdict),
                                         ("patch_code", Patch), ("pr_description", PrText)])
async def test_mock_mode_returns_valid_objects(name, schema):
    out = await llm.complete_json(name, {}, schema)
    assert isinstance(out, schema)


async def test_mock_symbols_content():
    out = await llm.complete_json("extract_symbols", {}, Symbols)
    assert "yaml.load" in out.symbols


async def test_mock_unknown_prompt_and_traversal_rejected():
    with pytest.raises(LLMError):
        await llm.complete_json("nope", {}, Symbols)
    with pytest.raises(LLMError):
        await llm.complete_json("../../core/config", {}, Symbols)


async def test_mock_schema_mismatch_raises():
    with pytest.raises(LLMError):
        await llm.complete_json("patch_code", {}, Symbols)


# --- prompt + JSON helpers ------------------------------------------------------------------------------------

def test_render_fills_variables_single_pass():
    out = llm.render_prompt("extract_symbols", {**SYM_VARS, "summary": "{{package}}", "references": ["a", "b"]})
    assert "Package: PyYAML" in out
    assert "Summary: {{package}}" in out  # value not re-expanded
    assert '["a", "b"]' in out


def test_render_missing_variable_raises():
    with pytest.raises(LLMError, match="ecosystem"):
        llm.render_prompt("extract_symbols", {})


@pytest.mark.parametrize("text", [
    json.dumps(GOOD),
    "```json\n" + json.dumps(GOOD) + "\n```",
    "```\n" + json.dumps(GOOD) + "\n```",
    "Here you go:\n" + json.dumps(GOOD) + "\nHope that helps",
])
def test_extract_json_variants(text):
    assert llm.extract_json(text)["package"] == "PyYAML"


@pytest.mark.parametrize("text", ["", "   ", "I cannot help with that.", "{broken"])
def test_extract_json_rejects(text):
    with pytest.raises(ValueError):
        llm.extract_json(text)


# --- live mode: providers -------------------------------------------------------------------------------------

async def test_anthropic_request_and_parse(monkeypatch):
    live(monkeypatch)
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["headers"], seen["body"] = str(req.url), req.headers, json.loads(req.content)
        return anthropic_reply("```json\n" + json.dumps(GOOD) + "\n```")

    serve(monkeypatch, handler)
    out = await llm.complete_json("extract_symbols", SYM_VARS, Symbols)
    assert out.symbols == ["yaml.load"]
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    assert seen["headers"]["x-api-key"] == KEY
    assert seen["body"]["model"] == "m" and "PyYAML" in seen["body"]["messages"][0]["content"]


async def test_openai_request_and_base_url_override(monkeypatch):
    live(monkeypatch, provider="openai", base="https://gw.example.com/v1/")
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["auth"] = str(req.url), req.headers["authorization"]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(GOOD)}}],
                                         "usage": {"prompt_tokens": 5, "completion_tokens": 3}})

    serve(monkeypatch, handler)
    out = await llm.complete_json("extract_symbols", SYM_VARS, Symbols)
    assert out.package == "PyYAML"
    assert seen["url"] == "https://gw.example.com/v1/chat/completions"
    assert seen["auth"] == f"Bearer {KEY}"


async def test_azure_uses_api_key_header_and_deployment_url(monkeypatch):
    live(monkeypatch, provider="openai", base="https://res.openai.azure.com", model="gpt-dep")
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["headers"] = str(req.url), req.headers
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(GOOD)}}]})

    serve(monkeypatch, handler)
    await llm.complete_json("extract_symbols", SYM_VARS, Symbols)
    assert seen["url"].startswith("https://res.openai.azure.com/openai/deployments/gpt-dep/chat/completions?api-version=")
    assert seen["headers"]["api-key"] == KEY
    assert "authorization" not in seen["headers"]


async def test_live_without_key_raises(monkeypatch):
    live(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", "")
    reset_settings_cache()
    with pytest.raises(LLMError, match="LLM_API_KEY"):
        await llm.complete_json("extract_symbols", SYM_VARS, Symbols)


# --- E9: invalid output ---------------------------------------------------------------------------------------

async def test_invalid_json_retried_once_with_error_then_ok(monkeypatch):
    live(monkeypatch)
    bodies = []
    replies = iter(["sorry, no json", json.dumps(GOOD)])

    def handler(req):
        bodies.append(json.loads(req.content)["messages"][0]["content"])
        return anthropic_reply(next(replies))

    serve(monkeypatch, handler)
    out = await llm.complete_json("extract_symbols", SYM_VARS, Symbols)
    assert out.package == "PyYAML" and len(bodies) == 2
    assert "previous reply was invalid" in bodies[1] and "previous reply" not in bodies[0]


async def test_schema_violation_retried_then_raises(monkeypatch):
    live(monkeypatch)
    calls = []

    def handler(req):
        calls.append(1)
        return anthropic_reply(json.dumps({"package": "x"}))  # confidence missing

    serve(monkeypatch, handler)
    with pytest.raises(LLMError, match="invalid after retry"):
        await llm.complete_json("extract_symbols", SYM_VARS, Symbols)
    assert len(calls) == 2


async def test_empty_response_raises_after_one_retry(monkeypatch):
    live(monkeypatch)
    calls = []

    def handler(req):
        calls.append(1)
        return anthropic_reply("")

    serve(monkeypatch, handler)
    with pytest.raises(LLMError):
        await llm.complete_json("extract_symbols", SYM_VARS, Symbols)
    assert len(calls) == 2


# --- N1: rate limits ------------------------------------------------------------------------------------------

async def test_429_then_success_backoff_and_retry_after(monkeypatch):
    live(monkeypatch)
    replies = iter([httpx.Response(429, headers={"retry-after": "7"}), httpx.Response(503),
                    anthropic_reply(json.dumps(GOOD))])
    delays = serve(monkeypatch, lambda req: next(replies))
    out = await llm.complete_json("extract_symbols", SYM_VARS, Symbols)
    assert out.package == "PyYAML"
    assert delays == [7.0, 2.0]  # Retry-After honoured, then exponential


async def test_backoff_schedule_and_gives_up_after_three_retries(monkeypatch):
    live(monkeypatch)
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(500)

    delays = serve(monkeypatch, handler)
    with pytest.raises(LLMError, match="unavailable"):
        await llm.complete_json("extract_symbols", SYM_VARS, Symbols)
    assert len(calls) == 4 and delays == [1.0, 2.0, 4.0]


async def test_timeout_is_retried(monkeypatch):
    live(monkeypatch)
    state = {"n": 0}

    def handler(req):
        state["n"] += 1
        if state["n"] == 1:
            raise httpx.ReadTimeout("slow", request=req)
        return anthropic_reply(json.dumps(GOOD))

    serve(monkeypatch, handler)
    assert (await llm.complete_json("extract_symbols", SYM_VARS, Symbols)).package == "PyYAML"


async def test_client_error_not_retried_and_key_redacted(monkeypatch):
    live(monkeypatch)
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(401, text=f"bad key {KEY}")

    serve(monkeypatch, handler)
    with pytest.raises(LLMError) as e:
        await llm.complete_json("extract_symbols", SYM_VARS, Symbols)
    assert len(calls) == 1 and KEY not in str(e.value)


async def test_concurrency_limited_to_four(monkeypatch):
    live(monkeypatch)
    running = peak = 0
    real = httpx.AsyncClient

    class SlowTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.02)
            running -= 1
            return anthropic_reply(json.dumps(GOOD))

    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda *a, **kw: real(*a, **{**kw, "transport": SlowTransport()}))
    await asyncio.gather(*[llm.complete_json("extract_symbols", SYM_VARS, Symbols) for _ in range(10)])
    assert peak == 4


# --- O2: logging ----------------------------------------------------------------------------------------------

async def test_logs_tokens_and_latency(monkeypatch, caplog):
    live(monkeypatch)
    serve(monkeypatch, lambda req: anthropic_reply(json.dumps(GOOD)))
    with caplog.at_level(logging.INFO, logger="patchpilot.llm"):
        await llm.complete_json("extract_symbols", SYM_VARS, Symbols)
    line = next(r.getMessage() for r in caplog.records if "tokens_in" in r.getMessage())
    assert "prompt=extract_symbols" in line and "tokens_in=11" in line and "tokens_out=7" in line
    assert "latency_ms=" in line
