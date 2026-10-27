"""Stage 3 — vulnerable symbol extraction (T05). LLM via `app.services.llm`, cached by CVE id."""
from __future__ import annotations

from app.models.domain import RawVuln, VulnSymbols


async def extract(vuln: RawVuln) -> VulnSymbols:
    """Turn the advisory text into the fully-qualified functions that are dangerous (e.g. `yaml.load`).

    Falls back to the seed map when the LLM is unsure or unavailable.
    """
    raise NotImplementedError("T05")
