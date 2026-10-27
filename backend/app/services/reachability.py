"""Stage 4 — reachability (T06). Python: `ast` ("deep"); other languages: text search + AI ("generic")."""
from __future__ import annotations

from pathlib import Path

from app.models.domain import RawVuln, Verdict, VulnSymbols


async def analyze(repo_path: Path, vuln: RawVuln, symbols: VulnSymbols) -> Verdict:
    """Decide whether application code calls the vulnerable symbols; return file:line evidence.

    No call-site matches -> `not_reachable` (confidence 0.9) without an LLM call. AST evidence is authoritative
    over LLM output (RISKS S5).
    """
    raise NotImplementedError("T06")
