"""T09 GitHub PR creator: title/body rules, mock mode, live push + PR paths, S4 token safety, N11 reuse, L7 grouping."""
from __future__ import annotations

import base64
from pathlib import Path

import pytest
from github import GithubException

from app.core.config import reset_settings_cache
from app.core.db import init_db
from app.core.subproc import CommandResult
from app.models import repository as repo
from app.models.domain import FixResult
from app.models.schemas import FindingDetail
from app.services import github_pr
from app.services.github_pr import PRError
from tests.seed import seed_contract_scan, seed_extra_findings

TOKEN = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"
REPO = "https://github.com/BommepalliRoop/demo-target"


@pytest.fixture(autouse=True)
def _db():
    init_db()


def _details() -> list[FindingDetail]:
    scan_id, fid = seed_contract_scan()
    d = repo.get_finding(fid)
    assert d is not None
    return [d]


def _fix(status: str = "fixed", tests: bool = True, work_dir: Path | None = None) -> FixResult:
    return FixResult(package="PyYAML", new_version="6.0.3", tests_passed=tests, attempts=1,
                     branch="patchpilot/pyyaml-6.0.3", work_dir=work_dir, status=status)  # type: ignore[arg-type]


def test_title_single_and_multi_cve_highest_priority():
    d = _details()[0]
    other = d.model_copy(update={"cve_id": "CVE-2099-0001", "priority": "P1", "finding_id": "x"})
    low = d.model_copy(update={"priority": "P3"})
    assert github_pr.build_title(_fix(), [low]) == f"[PatchPilot][P3] Fix {d.cve_id} in PyYAML"
    assert github_pr.build_title(_fix(), [low, other]) == "[PatchPilot][P1] Fix 2 CVEs in PyYAML"


def test_body_lists_every_cve_with_evidence_and_rollback():
    d = _details()[0]
    other = d.model_copy(update={"cve_id": "CVE-2099-0001", "finding_id": "x"})
    body = github_pr.build_body(_fix(), [d, other])
    assert d.cve_id in body and "CVE-2099-0001" in body
    assert f"{d.evidence[0].file}:{d.evidence[0].line}" in body
    assert "Revert this pull request" in body
    assert "Tests passed" in body


async def test_mock_returns_deterministic_url_and_stores_body():
    details = _details()
    url = await github_pr.open_pr(REPO, "main", _fix(), details)
    assert url == await github_pr.open_pr(REPO, "main", _fix(), details)
    assert url.startswith(f"{REPO}/pull/")
    timeline = repo.get_finding(details[0].finding_id).timeline  # type: ignore[union-attr]
    assert any(t.stage == "pr" and url in t.message and "## Rollback" in t.message for t in timeline)


async def test_untested_fix_gets_warning_line_and_label(monkeypatch):
    details = _details()
    await github_pr.open_pr(REPO, "main", _fix("fixed_untested", tests=False), details)
    msg = [t.message for t in repo.get_finding(details[0].finding_id).timeline if t.stage == "pr"][-1]  # type: ignore[union-attr]
    assert "**PatchPilot could not run this project's tests — please run them before merging.**" in msg
    assert github_pr._labels(_fix("fixed_untested")) == ["security", "tests-not-run"]
    assert github_pr._labels(_fix()) == ["security"]


async def test_requires_findings_and_branch():
    with pytest.raises(PRError):
        await github_pr.open_pr(REPO, "main", _fix(), [])
    with pytest.raises(PRError):
        await github_pr.open_pr(REPO, "main", FixResult(package="x", status="fixed"), _details())


def test_parse_repo():
    assert github_pr.parse_repo("https://github.com/a/b.git") == ("a", "b")
    assert github_pr.parse_repo("https://github.com/a/b/") == ("a", "b")
    with pytest.raises(PRError):
        github_pr.parse_repo("https://evil.example.com/a/b")


# ----------------------------------------------------------------------------- live

class FakePR:
    html_url = "https://github.com/BommepalliRoop/demo-target/pull/7"

    def __init__(self) -> None:
        self.edited: dict | None = None
        self.labels: tuple = ()

    def edit(self, **kw):
        self.edited = kw

    def add_to_labels(self, *labels):
        self.labels = labels


class FakeRepo:
    def __init__(self, existing: FakePR | None = None, fail: GithubException | None = None) -> None:
        self.existing, self.fail, self.created = existing, fail, None
        self.made_labels: list[str] = []

    def get_pulls(self, **kw):
        assert kw["head"] == "BommepalliRoop:patchpilot/pyyaml-6.0.3"
        return [self.existing] if self.existing else []

    def create_pull(self, **kw):
        if self.fail:
            raise self.fail
        self.created = kw
        return FakePR()

    def get_label(self, name):
        raise GithubException(404, {}, None)

    def create_label(self, name, color):
        self.made_labels.append(name)


def _live(monkeypatch, fake_repo: FakeRepo) -> list[list[str]]:
    monkeypatch.setenv("GITHUB_MODE", "live")
    monkeypatch.setenv("GITHUB_TOKEN", TOKEN)
    reset_settings_cache()
    calls: list[list[str]] = []

    async def fake_run(cmd, **kw):
        calls.append(list(cmd))
        return CommandResult(0, "", "")

    class FakeGithub:
        def __init__(self, auth=None):
            pass

        def get_repo(self, name):
            assert name == "BommepalliRoop/demo-target"
            return fake_repo

        def close(self):
            pass

    monkeypatch.setattr(github_pr, "run", fake_run)
    monkeypatch.setattr(github_pr, "Github", lambda auth=None, per_page=30: FakeGithub())
    return calls


async def test_live_pushes_with_header_not_url_and_opens_pr(monkeypatch, tmp_path):
    fake = FakeRepo()
    calls = _live(monkeypatch, fake)
    url = await github_pr.open_pr(REPO, "main", _fix("fixed_untested", False, tmp_path), _details())
    assert url.endswith("/pull/7")
    cmd = calls[0]
    assert TOKEN not in " ".join(cmd).replace(base64.b64encode(f"x-access-token:{TOKEN}".encode()).decode(), "")
    assert "https://github.com/BommepalliRoop/demo-target.git" in cmd  # plain URL, no credentials
    assert cmd[-1] == "patchpilot/pyyaml-6.0.3:refs/heads/patchpilot/pyyaml-6.0.3"
    assert fake.created["base"] == "main" and fake.created["head"] == "patchpilot/pyyaml-6.0.3"
    assert fake.created["title"].startswith("[PatchPilot][")
    assert fake.created["body"].startswith("**PatchPilot could not run")
    assert fake.made_labels == ["security", "tests-not-run"]


async def test_live_existing_pr_is_reused_and_updated(monkeypatch, tmp_path):
    existing = FakePR()
    fake = FakeRepo(existing=existing)
    _live(monkeypatch, fake)
    url = await github_pr.open_pr(REPO, "main", _fix(work_dir=tmp_path), _details())
    assert url == existing.html_url and fake.created is None
    assert existing.edited and "Rollback" in existing.edited["body"]
    assert existing.labels == ("security",)


async def test_live_api_error_is_redacted(monkeypatch, tmp_path):
    fake = FakeRepo(fail=GithubException(422, {"message": f"Validation Failed {TOKEN}"}, None))
    _live(monkeypatch, fake)
    with pytest.raises(PRError) as exc:
        await github_pr.open_pr(REPO, "main", _fix(work_dir=tmp_path), _details())
    assert TOKEN not in str(exc.value) and "422" in str(exc.value)


async def test_live_push_failure_is_redacted(monkeypatch, tmp_path):
    _live(monkeypatch, FakeRepo())

    async def bad_run(cmd, **kw):
        return CommandResult(1, "", f"fatal: https://x-access-token:{TOKEN}@github.com/a/b denied")

    monkeypatch.setattr(github_pr, "run", bad_run)
    with pytest.raises(PRError) as exc:
        await github_pr.open_pr(REPO, "main", _fix(work_dir=tmp_path), _details())
    assert TOKEN not in str(exc.value)


async def test_live_without_token_fails_clearly(monkeypatch):
    monkeypatch.setenv("GITHUB_MODE", "live")
    reset_settings_cache()
    with pytest.raises(PRError, match="GITHUB_TOKEN"):
        await github_pr.open_pr(REPO, "main", _fix(), _details())


async def test_one_pr_for_several_cves_in_one_package():
    scan_id, fid = seed_contract_scan()
    seed_extra_findings(scan_id)
    details = [d for d in (repo.get_finding(f.finding_id) for f in repo.list_findings(scan_id)) if d]
    same = [d.model_copy(update={"package": "PyYAML"}) for d in details[:3]]
    title = github_pr.build_title(_fix(), same)
    body = github_pr.build_body(_fix(), same)
    assert "CVEs in PyYAML" in title
    assert all(d.cve_id in body for d in same)
