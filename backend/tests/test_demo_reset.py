"""T17 demo reset (RISKS O3, S8, E13): DB, SSE buffers, WORK_DIR and our `patchpilot/*` PR branches."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from github import GithubException

from app import seed
from app.core.config import get_settings, reset_settings_cache
from app.core.db import init_db
from app.core.events import ScanEvent, bus
from app.models import repository as repo
from app.services import demo_reset

KEY = "test-api-key-0123456789abcdef"


@pytest.fixture(autouse=True)
def _db():
    init_db()


@pytest.fixture
def demo_mode(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    reset_settings_cache()


def _leftovers() -> None:
    work = get_settings().work_path
    (work / "scn_old" / "repo").mkdir(parents=True)
    (work / "scn_old-fix-abc").mkdir()
    (work / "cache" / "pip").mkdir(parents=True)
    (work / "cache" / "kev.json").write_text("{}", encoding="utf-8")
    bus.publish(ScanEvent(scan_id="scn_old", stage="clone"))


def test_reset_clears_db_buffers_and_work_dirs_but_keeps_the_cache(client, demo_mode):
    seed.seed()
    _leftovers()
    r = client.post("/api/demo/reset", headers={"X-API-Key": KEY})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert repo.list_scans() == [] and repo.list_integration_events() == []
    assert bus.history("scn_old") == []
    work = get_settings().work_path
    assert sorted(p.name for p in work.iterdir()) == ["cache"]
    assert (work / "cache" / "kev.json").exists()  # N4: next demo run stays fast


def test_reset_needs_demo_mode_and_the_api_key(client, demo_mode, monkeypatch):
    assert client.post("/api/demo/reset").status_code == 401
    assert client.post("/api/demo/reset", headers={"X-API-Key": "wrong"}).status_code == 401
    monkeypatch.setenv("DEMO_MODE", "false")
    reset_settings_cache()
    assert client.post("/api/demo/reset", headers={"X-API-Key": KEY}).status_code == 404


async def test_mock_github_mode_never_calls_github(monkeypatch):
    monkeypatch.setattr(demo_reset, "Github", lambda **_: pytest.fail("GitHub called in mock mode"))
    report = await demo_reset.reset()
    assert report.errors == [] and report.prs_closed == []


# ---------------------------------------------------------------- live GitHub cleanup with a fake PyGithub

class FakeRef:
    def __init__(self, repo: FakeRepo, name: str) -> None:
        self.repo, self.name = repo, name

    def delete(self) -> None:
        if self.name in self.repo.undeletable:
            raise GithubException(422, {"message": "protected"}, None)
        self.repo.deleted.append(self.name)


class FakeRepo:
    def __init__(self, full_name: str, pulls: list[tuple[str, str]], branches: list[str]) -> None:
        self.full_name = full_name
        self.closed: list[str] = []
        self.deleted: list[str] = []
        self.undeletable: set[str] = set()
        self._pulls = pulls  # (head ref, head repo full name)
        self._branches = branches

    def get_pulls(self, state: str):  # noqa: ANN201
        assert state == "open"
        out = []
        for i, (ref, head_repo) in enumerate(self._pulls, start=1):
            pr = SimpleNamespace(head=SimpleNamespace(ref=ref, repo=SimpleNamespace(full_name=head_repo)),
                                 html_url=f"https://github.com/{self.full_name}/pull/{i}")
            pr.edit = lambda state, _ref=ref: self.closed.append(_ref) if state == "closed" else None
            out.append(pr)
        return out

    def get_branches(self):  # noqa: ANN201
        return [SimpleNamespace(name=b) for b in self._branches]

    def get_git_ref(self, ref: str) -> FakeRef:
        assert ref.startswith("heads/")
        return FakeRef(self, ref.removeprefix("heads/"))


class FakeGithub:
    def __init__(self, repos: dict[str, FakeRepo]) -> None:
        self.repos = repos
        self.closed_client = False

    def __call__(self, **_kw) -> FakeGithub:  # used as the `Github(...)` constructor
        return self

    def get_repo(self, full_name: str) -> FakeRepo:
        if full_name not in self.repos:
            raise GithubException(404, {"message": "Not Found"}, None)
        return self.repos[full_name]

    def close(self) -> None:
        self.closed_client = True


@pytest.fixture
def live_github(monkeypatch):
    monkeypatch.setenv("GITHUB_MODE", "live")
    monkeypatch.setenv("GITHUB_TOKEN", "github_pat_" + "x" * 30)
    monkeypatch.setenv("DEMO_REPO_URL", "https://github.com/BommepalliRoop/demo-target")
    reset_settings_cache()
    target = FakeRepo("BommepalliRoop/demo-target",
                      pulls=[("patchpilot/pyyaml-6.0.3", "BommepalliRoop/demo-target"),
                             ("feature/login", "BommepalliRoop/demo-target"),
                             ("patchpilot/evil", "someone/fork")],
                      branches=["main", "feature/login", "patchpilot/pyyaml-6.0.3", "patchpilot/lodash-4.18.0"])
    fake = FakeGithub({"BommepalliRoop/demo-target": target})
    monkeypatch.setattr(demo_reset, "Github", fake)
    return fake


async def test_live_reset_closes_only_our_prs_and_deletes_only_patchpilot_branches(live_github):
    seed.seed()  # scanned repos: demo-target + clean-service (404 -> reported, not raised)
    report = await demo_reset.reset()
    target = live_github.repos["BommepalliRoop/demo-target"]
    assert target.closed == ["patchpilot/pyyaml-6.0.3"]  # not feature/login, not a fork's PR
    assert sorted(target.deleted) == ["patchpilot/lodash-4.18.0", "patchpilot/pyyaml-6.0.3"]
    assert report.prs_closed == ["https://github.com/BommepalliRoop/demo-target/pull/1"]
    assert any("clean-service" in e and "404" in e for e in report.errors)
    assert repo.list_scans() == []  # GitHub trouble never blocks the local reset
    assert live_github.closed_client


async def test_live_reset_reports_branch_errors_and_missing_token(live_github, monkeypatch):
    live_github.repos["BommepalliRoop/demo-target"].undeletable = {"patchpilot/lodash-4.18.0"}
    report = await demo_reset.reset()
    assert report.branches_deleted == ["BommepalliRoop/demo-target:patchpilot/pyyaml-6.0.3"]
    assert any("could not delete patchpilot/lodash-4.18.0" in e for e in report.errors)

    monkeypatch.setenv("GITHUB_TOKEN", "")
    reset_settings_cache()
    report = await demo_reset.reset()
    assert report.errors == ["GITHUB_TOKEN is not set; demo PR branches were not deleted"]


async def test_reset_errors_never_contain_the_token(live_github, monkeypatch):
    token = get_settings().github_token

    def boom(_name: str):  # noqa: ANN202
        raise GithubException(401, {"message": f"bad credentials {token}"}, None)

    monkeypatch.setattr(live_github, "get_repo", boom)
    report = await demo_reset.reset()
    assert report.errors and all(token not in e for e in report.errors)  # S4
