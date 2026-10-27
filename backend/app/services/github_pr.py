"""Stage 7 — push the fix branch and open a pull request (T09). GitHub required; GitLab is a stretch."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import re
from urllib.parse import urlparse

from github import Auth, Github, GithubException
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.security import redact
from app.core.subproc import CommandTimeout, clean_env, run
from app.models import repository as repo
from app.models.domain import FixResult
from app.models.schemas import FindingDetail
from app.services import llm

logger = logging.getLogger(__name__)

PUSH_TIMEOUT = 120.0
PRIORITY_ORDER = ("P1", "P2", "P3", "P4")
UNTESTED_NOTE = "**PatchPilot could not run this project's tests — please run them before merging.**"
_GITHUB_PATH = re.compile(r"^/([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?$")


class PRError(Exception):
    """Pull request could not be opened; the message is already redacted (RISKS S4)."""


class PRText(BaseModel):
    title: str = ""
    body: str


def parse_repo(repo_url: str) -> tuple[str, str]:
    """`https://github.com/owner/name(.git)` -> (owner, name)."""
    u = urlparse(repo_url)
    m = _GITHUB_PATH.match(u.path)
    if u.hostname != "github.com" or not m:
        raise PRError(f"not a GitHub repository URL: {redact(repo_url)}")
    return m.group(1), m.group(2)


def _highest_priority(findings: list[FindingDetail]) -> str:
    ranks = [PRIORITY_ORDER.index(f.priority) for f in findings if f.priority in PRIORITY_ORDER]
    return PRIORITY_ORDER[min(ranks)] if ranks else "P3"


def build_title(fix: FixResult, findings: list[FindingDetail]) -> str:
    """One CVE -> `Fix CVE in pkg`; several (RISKS L7) -> `Fix n CVEs in pkg`, highest priority wins."""
    cves = sorted({f.cve_id for f in findings})
    what = cves[0] if len(cves) == 1 else f"{len(cves)} CVEs"
    return f"[PatchPilot][{_highest_priority(findings)}] Fix {what} in {fix.package}"


def _evidence_lines(f: FindingDetail) -> list[str]:
    return [f"`{e.file}:{e.line}`" + (" (inside a route)" if e.in_route else "") for e in f.evidence[:3]]


def build_body(fix: FixResult, findings: list[FindingDetail]) -> str:
    """Deterministic markdown body; the LLM version (live mode) replaces only the narrative."""
    old = sorted({f.installed_version for f in findings})
    lines = [f"## Risk summary", "",
             f"Upgrades **{fix.package}** {', '.join(old)} -> **{fix.new_version}**, fixing "
             f"{len(findings)} advisory(ies):", ""]
    for f in sorted(findings, key=lambda x: (PRIORITY_ORDER.index(x.priority), x.cve_id)):
        threat = ", in CISA KEV" if f.kev else ""
        epss = f", EPSS {f.epss:.2f}" if f.epss is not None else ""
        lines.append(f"- **{f.cve_id}** — {f.priority}, risk score {f.score}, CVSS {f.cvss}{threat}{epss}, "
                     f"reachability: {f.reachability}")
    lines += ["", "## Why this is reachable", ""]
    for f in findings:
        ev = ", ".join(_evidence_lines(f)) or "no call site evidence recorded"
        lines.append(f"- {f.cve_id}: {f.ai_explanation or 'see evidence'} ({ev})")
    lines += ["", "## Changes", "", f"- Dependency `{fix.package}` upgraded to `{fix.new_version}`"]
    if fix.attempts:
        lines.append(f"- Code patched by AI to stay compatible ({fix.attempts} attempt(s))")
    lines += ["", "## Test results", ""]
    lines.append("Tests passed after the upgrade." if fix.tests_passed
                 else "Tests were not run (no test suite or toolchain available).")
    lines += ["", "## Rollback", "", "Revert this pull request.", "",
              "_Opened automatically by PatchPilot._"]
    return "\n".join(lines)


async def _narrative(fix: FixResult, findings: list[FindingDetail], fallback: str) -> str:
    """LLM-written body in live mode; any failure falls back to the template (RISKS E9 style)."""
    if get_settings().llm_mode != "live":
        return fallback
    f0 = findings[0]
    try:
        out = await llm.complete_json("pr_description", {
            "package": fix.package, "old_version": f0.installed_version, "new_version": fix.new_version,
            "cve_id": ", ".join(f.cve_id for f in findings), "severity": _highest_priority(findings),
            "risk_score": max(f.score for f in findings),
            "reachability_explanation": " ".join(f.ai_explanation for f in findings),
            "evidence": "; ".join(x for f in findings for x in _evidence_lines(f)),
            "changes": f"upgraded {fix.package} to {fix.new_version}",
            "test_result": "passed" if fix.tests_passed else "not run",
        }, PRText)
        return out.body or fallback
    except Exception as e:  # noqa: BLE001
        logger.warning("pr_description LLM failed, using template: %s", redact(e))
        return fallback


def _labels(fix: FixResult) -> list[str]:
    return ["security"] + (["tests-not-run"] if fix.status == "fixed_untested" else [])


def _mock_url(repo_url: str, branch: str) -> str:
    base = repo_url.rstrip("/").removesuffix(".git")
    return f"{base}/pull/{1 + int(hashlib.sha1(branch.encode()).hexdigest()[:6], 16) % 900}"


async def open_pr(repo_url: str, branch: str, fix: FixResult, findings: list[FindingDetail]) -> str:
    """Push `fix.branch` and open (or reuse) a PR; return its URL.

    `findings` are all the CVEs fixed by this package bump (one PR per package, RISKS L7). In `GITHUB_MODE=mock`
    returns a deterministic fake URL and pushes nothing.
    """
    if not findings:
        raise PRError("no findings to describe")
    if not fix.branch:
        raise PRError("fix has no branch to push")
    title = build_title(fix, findings)
    body = await _narrative(fix, findings, build_body(fix, findings))
    if fix.status == "fixed_untested":
        body = f"{UNTESTED_NOTE}\n\n{body}"

    settings = get_settings()
    if settings.github_mode == "mock":
        url = _mock_url(repo_url, fix.branch)
        for f in findings:  # the body is kept in the DB so the demo UI can show it
            repo.append_timeline(f.finding_id, "pr", f"[mock] {url} — {title}\n\n{body}")
        logger.info("github mock PR %s labels=%s", url, _labels(fix))
        return url

    if not settings.github_token:
        raise PRError("GITHUB_TOKEN is not set")
    owner, name = parse_repo(repo_url)
    await _push(repo_url, fix)
    try:
        return await asyncio.to_thread(_open_or_update, owner, name, branch, fix, title, body)
    except GithubException as e:
        raise PRError(redact(f"GitHub API error {e.status}: {getattr(e, 'data', '')}")) from None


async def _push(repo_url: str, fix: FixResult) -> None:
    """Push to the real URL (work_dir's `origin` is a local clone). Token goes in a header, never in the URL (S4).

    Force is limited to our own `patchpilot/...` branch so a re-run updates it (N11).
    """
    if fix.work_dir is None:
        raise PRError("fix has no work directory to push from")
    token = get_settings().github_token
    auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    url = repo_url.rstrip("/")
    if not url.endswith(".git"):
        url += ".git"
    cmd = ["git", "-c", f"http.extraheader=Authorization: Basic {auth}", "push", "--force", url,
           f"{fix.branch}:refs/heads/{fix.branch}"]
    try:
        res = await run(cmd, cwd=fix.work_dir, env=clean_env({"GIT_TERMINAL_PROMPT": "0"}), timeout=PUSH_TIMEOUT)
    except CommandTimeout:
        raise PRError("git push timed out") from None
    if res.returncode != 0:
        raise PRError(redact(f"git push failed: {res.stderr.strip()[-300:]}"))


def _open_or_update(owner: str, name: str, base: str, fix: FixResult, title: str, body: str) -> str:
    gh = Github(auth=Auth.Token(get_settings().github_token), per_page=30)
    try:
        r = gh.get_repo(f"{owner}/{name}")
        existing = list(r.get_pulls(state="open", head=f"{owner}:{fix.branch}", base=base))
        if existing:  # N11: reuse the PR, refresh its text
            pr = existing[0]
            pr.edit(title=title, body=body)
        else:
            pr = r.create_pull(title=title, body=body, head=fix.branch, base=base)
        _ensure_labels(r, pr, _labels(fix))
        return pr.html_url
    finally:
        gh.close()


def _ensure_labels(r, pr, labels: list[str]) -> None:
    colors = {"security": "d73a4a", "tests-not-run": "fbca04"}
    for label in labels:
        try:
            r.get_label(label)
        except GithubException:
            try:
                r.create_label(label, colors.get(label, "ededed"))
            except GithubException:  # label creation is cosmetic, never fail the PR for it
                logger.warning("could not create label %s", label)
    try:
        pr.add_to_labels(*labels)
    except GithubException:
        logger.warning("could not label PR")
