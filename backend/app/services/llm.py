"""The only place that calls a model (T04). Prompts live in `app/prompts/<name>.md`; outputs are validated JSON."""
from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


async def complete_json(prompt_name: str, variables: dict[str, Any], schema: type[T]) -> T:
    """Fill `{{variables}}` in `prompts/<prompt_name>.md`, call the provider, parse + validate JSON as `schema`.

    Invalid JSON -> one retry with the validation error appended, then raises so the caller uses its safe fallback.
    `LLM_MODE=mock` returns canned JSON from `prompts/mocks/<prompt_name>.json`.
    """
    raise NotImplementedError("T04")
