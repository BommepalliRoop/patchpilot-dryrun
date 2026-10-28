"""Demo reset (T17, RISKS O3): leave no rehearsal data behind.

`POST /api/demo/reset` and `python -m app.seed --reset` call `reset()`, which
1. empties the DB and the SSE replay buffers,
2. deletes every scan / fix work dir under `WORK_DIR` (the shared `cache/` with pip, npm and KEV stays, so the
   next demo run is still fast — RISKS N4, E13),
3. in `GITHUB_MODE=live`: closes the open PatchPilot pull requests and deletes their `patchpilot/*` branches on
   every GitHub repo that was scanned, plus `DEMO_REPO_URL`. Only our own `patchpilot/` branches are touched.

GitHub problems are logged and reported, never raised: a reset must always clear the local state.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import stat
from dataclasses import dataclass, field

from github import Auth, Github, GithubException

from app.core.config import get_settings
from app.core.events import bus
from app.core.security import redact
from app.models import repository as repo
from app.services import github_pr

logger = logging.getLogger(__name__)

BRANCH_PREFIX = "patchpilot/"
KEEP_DIRS = {"cache"}


@dataclass
class ResetReport:
    work_dirs_removed: int = 0
    prs_closed: list[str] = field(default_factory=list)
    branches_deleted: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


async def reset() -> ResetReport:
    report = ResetReport()
    repo_urls = _github_repos({s.repo_url for s in repo.list_scans(limit=1000)})
    repo.clear_all()
    bus.clear()
    report.work_dirs_removed = clear_work_dir()
    if get_settings().github_mode == "live":
        await asyncio.to_thread(_clean_github, repo_urls, report)
    logger.info("demo reset: %d work dir(s), %d PR(s) closed, %d branch(es) deleted, %d error(s)",
                report.work_dirs_removed, len(report.prs_closed), len(report.branches_deleted), len(report.errors))
    return report


def clear_work_dir() -> int:
    """Remove everything in WORK_DIR except the shared cache. Returns how many entries were removed."""
    root = get_settings().work_path
    if not root.is_dir():
        return 0
    removed = 0
    for entry in root.iterdir():
        if entry.name in KEEP_DIRS:
            continue
        try:
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry, onerror=_force_remove)
            else:
                entry.unlink()
            removed += 1
        except OSError as e:
            logger.warning("could not remove %s: %s", entry.name, redact(e))
    return removed


def _force_remove(func, path, _exc_info) -> None:  # noqa: ANN001
    """Windows: .git object files are read-only."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _github_repos(scanned: set[str]) -> list[tuple[str, str]]:
    """(owner, name) of every GitHub repo we may have pushed to, demo repo included."""
    urls = set(scanned)
    if get_settings().demo_repo_url:
        urls.add(get_settings().demo_repo_url)
    out: set[tuple[str, str]] = set()
    for url in urls:
        try:
            out.add(github_pr.parse_repo(url))
        except github_pr.PRError:
            continue  # not GitHub: nothing to clean
    return sorted(out)


def _clean_github(repos: list[tuple[str, str]], report: ResetReport) -> None:
    token = get_settings().github_token
    if not token:
        report.errors.append("GITHUB_TOKEN is not set; demo PR branches were not deleted")
        return
    gh = Github(auth=Auth.Token(token), per_page=50)
    try:
        for owner, name in repos:
            try:
                _clean_repo(gh, owner, name, report)
            except GithubException as e:
                report.errors.append(redact(f"{owner}/{name}: GitHub API error {e.status}"))
    finally:
        gh.close()
    for msg in report.errors:
        logger.warning("demo reset: %s", msg)


def _clean_repo(gh: Github, owner: str, name: str, report: ResetReport) -> None:
    r = gh.get_repo(f"{owner}/{name}")
    for pr in r.get_pulls(state="open"):
        if pr.head.ref.startswith(BRANCH_PREFIX) and pr.head.repo is not None and pr.head.repo.full_name == r.full_name:
            pr.edit(state="closed")
            report.prs_closed.append(pr.html_url)
    for branch in r.get_branches():
        if not branch.name.startswith(BRANCH_PREFIX):
            continue
        try:
            r.get_git_ref(f"heads/{branch.name}").delete()
            report.branches_deleted.append(f"{owner}/{name}:{branch.name}")
        except GithubException as e:
            report.errors.append(redact(f"{owner}/{name}: could not delete {branch.name} ({e.status})"))
