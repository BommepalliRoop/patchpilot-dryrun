"""Stage 6 — fix engine (T08): bump, install, test in an isolated venv, AI patch loop (max 2 attempts)."""
from __future__ import annotations

from pathlib import Path

from app.models.domain import FixResult, RawVuln


async def fix_package(scan_id: str, repo_path: Path, package: str, vulns: list[RawVuln]) -> FixResult:
    """One fix per package: smallest version that fixes *all* of `vulns`, one branch `patchpilot/<package>-<version>`.

    Never modifies `repo_path`; works on a copy under `<WORK_DIR>/<scan_id>`. PRs are never auto-merged (RISKS S6).
    """
    raise NotImplementedError("T08")
