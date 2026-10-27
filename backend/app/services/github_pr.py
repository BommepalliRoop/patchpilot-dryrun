"""Stage 7 — push the fix branch and open a pull request (T09). GitHub required; GitLab is a stretch."""
from __future__ import annotations

from app.models.domain import FixResult
from app.models.schemas import FindingDetail


async def open_pr(repo_url: str, branch: str, fix: FixResult, findings: list[FindingDetail]) -> str:
    """Push `fix.branch` and open (or reuse) a PR; return its URL.

    `findings` are all the CVEs fixed by this package bump (one PR per package, RISKS L7). In `GITHUB_MODE=mock`
    returns a deterministic fake URL and pushes nothing.
    """
    raise NotImplementedError("T09")
