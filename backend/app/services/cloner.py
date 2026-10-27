"""Stage 1 — clone (T02). Shallow, single-branch, 60 s timeout; token never appears in logged URLs (RISKS S3, S4, N2)."""
from __future__ import annotations

import base64
import logging
import os
import re
import shutil
import stat
from pathlib import Path

from app.core.config import get_settings
from app.core.security import redact
from app.core.subproc import CommandTimeout, clean_env, run
from app.models.schemas import BRANCH_RE

logger = logging.getLogger("patchpilot.cloner")

CLONE_TIMEOUT_S = 60
_SCAN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_GITHUB_PREFIX = "https://github.com/"


class CloneError(Exception):
    """Clone failed; the message is safe to show to users (no tokens)."""


def scan_dir(scan_id: str) -> Path:
    """`<WORK_DIR>/<scan_id>`; rejects ids that could escape WORK_DIR."""
    if not _SCAN_ID_RE.match(scan_id):
        raise ValueError(f"invalid scan_id: {scan_id!r}")
    return get_settings().work_path / scan_id


def _validate(repo_url: str, branch: str) -> None:
    """RISKS S3: https only, no whitespace, branch cannot look like a git option."""
    if not repo_url.startswith("https://") or any(c in repo_url for c in " \t\r\n\x00"):
        raise CloneError("repo_url must be an https:// URL")
    if branch.startswith("-") or not BRANCH_RE.match(branch):
        raise CloneError("invalid branch name")


def _auth_env() -> dict[str, str]:
    """Pass GITHUB_TOKEN as a scoped HTTP header via env, so it is in no argv, URL or log line."""
    token = get_settings().github_token
    if not token:
        return {}
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": f"http.{_GITHUB_PREFIX}.extraheader",
        "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}",
    }


async def clone(repo_url: str, branch: str, scan_id: str) -> Path:
    """Clone `repo_url`@`branch` into `<WORK_DIR>/<scan_id>/repo` and return that path.

    Uses GITHUB_TOKEN for private repos without putting it in any logged URL. Raises on timeout or git failure.
    """
    _validate(repo_url, branch)
    dest = scan_dir(scan_id) / "repo"
    dest.parent.mkdir(parents=True, exist_ok=True)
    auth = _auth_env() if repo_url.startswith(_GITHUB_PREFIX) else {}  # never send the GitHub token to another host
    env = clean_env({"GIT_TERMINAL_PROMPT": "0", **auth})
    cmd = ["git", "clone", "--depth", "1", "--single-branch", "--no-tags", "--branch", branch, "--", repo_url, str(dest)]
    logger.info("cloning %s@%s", redact(repo_url), branch)
    try:
        result = await run(cmd, env=env, timeout=CLONE_TIMEOUT_S)
    except CommandTimeout:
        cleanup(scan_id)
        raise CloneError(f"git clone timed out after {CLONE_TIMEOUT_S}s") from None
    except FileNotFoundError:
        cleanup(scan_id)
        raise CloneError("git is not installed on the server") from None
    if result.returncode != 0:
        cleanup(scan_id)
        reason = redact(result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown error")
        raise CloneError(f"git clone failed: {reason}")
    return dest


def _make_writable_and_retry(func, path, _exc_info) -> None:  # noqa: ANN001
    """Windows: .git object files are read-only."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def cleanup(scan_id: str) -> None:
    """Delete `<WORK_DIR>/<scan_id>` (called in `finally`, even after failure or timeout — RISKS E13)."""
    target = scan_dir(scan_id)
    if not target.exists():
        return
    try:
        shutil.rmtree(target, onerror=_make_writable_and_retry)
    except OSError as e:
        logger.warning("cleanup of %s failed: %s", target.name, redact(e))
