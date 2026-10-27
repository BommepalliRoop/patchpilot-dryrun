"""Stage 1 — clone (T02). Shallow, single-branch, 60 s timeout; token never appears in logged URLs (RISKS S3, S4, N2)."""
from __future__ import annotations

from pathlib import Path


async def clone(repo_url: str, branch: str, scan_id: str) -> Path:
    """Clone `repo_url`@`branch` into `<WORK_DIR>/<scan_id>/repo` and return that path.

    Uses GITHUB_TOKEN for private repos without putting it in any logged URL. Raises on timeout or git failure.
    """
    raise NotImplementedError("T02")


def cleanup(scan_id: str) -> None:
    """Delete `<WORK_DIR>/<scan_id>` (called in `finally`, even after failure or timeout — RISKS E13)."""
    raise NotImplementedError("T02")
