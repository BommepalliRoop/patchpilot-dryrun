"""Stage 2 — OSV scan (T02). Falls back to the OSV.dev querybatch API when the CLI is missing (RISKS N3)."""
from __future__ import annotations

from pathlib import Path

from app.models.domain import RawVuln


async def scan(path: Path) -> list[RawVuln]:
    """Run `osv-scanner scan source -r <path> --format json`; return one RawVuln per vulnerable package + advisory.

    Exit code 1 from osv-scanner means "vulnerabilities found" and is success. Pinned dependencies only (RISKS L6).
    """
    raise NotImplementedError("T02")
