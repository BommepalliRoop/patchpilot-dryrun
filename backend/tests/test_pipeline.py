"""T03 orchestrator, SSE and scan API. Hardening: S1, S3, S9, S10, N6, N7, N8, N9, E3, E4, E5, E6, E7, L7.

Every external stage is faked (or left as its NotImplementedError stub); all modes are mock, no network.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import pipeline
from app.core import security, subproc
from app.core.config import reset_settings_cache
from app.core.events import bus
from app.models import repository as repo
from app.models.domain import B2Response, B3Response, FixResult, RawVuln, Verdict, VulnSymbols
from app.models.schemas import Evidence
from app.services import boomi_client, cloner, fixer, github_pr, reachability, scanner, symbols
from app.services.cloner import CloneError

URL = "https://github.com/BommepalliRoop/demo-target"
KEY = "test-api-key-0123456789abcdef"  # conftest TEST_ENV
BODY = {"client_name": "Acme Retail", "repo_url": URL, "branch": "main", "auto_fix": True,
        "owner_email": "owner@easystepin.com"}
STAGES = ["clone", "scan", "symbols", "reachability", "risk", "fix", "pr", "notify", "done"]

VULNS = [
    RawVuln(cve_id="CVE-2020-14343", ecosystem="PyPI", analysis="deep", package="pyyaml", installed_version="5.3.1",
            fixed_versions=["5.4"], summary="Arbitrary code execution via full_load", cvss=9.8),
    RawVuln(cve_id="CVE-2020-1747", ecosystem="PyPI", analysis="deep", package="pyyaml", installed_version="5.3.1",
            fixed_versions=["5.3.1.post1"], summary="FullLoader code execution", cvss=9.8),
    RawVuln(cve_id="CVE-2023-32681", ecosystem="PyPI", analysis="deep", package="requests", installed_version="2.25.1",
            fixed_versions=["2.31.0"], summary="Proxy-Authorization leak", cvss=6.1),
    RawVuln(cve_id="CVE-2024-22195", ecosystem="PyPI", analysis="deep", package="jinja2", installed_version="2.11.3",
            fixed_versions=["3.1.3"], summary="XSS in xmlattr", cvss=5.4),
]
# cve -> (reachability, confidence, in_route)
VERDICTS = {
    "CVE-2020-14343": ("reachable", 0.93, True),
    "CVE-2020-1747": ("reachable", 0.9, True),
    "CVE-2023-32681": ("not_reachable", 0.9, False),
    "CVE-2024-22195": ("unsure", 0.4, False),
}


class Fakes:
    """Records every call the pipeline makes to the stage modules."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, stubs: tuple[str, ...] = ()) -> None:
        self.cloned: list[Path] = []
        self.fix_calls: list[tuple[str, list[str]]] = []
        self.pr_calls: list[tuple[str, list[str]]] = []
        self.b2: list[dict] = []
        self.b3: list[dict] = []
        self.reach_active = 0
        self.reach_max = 0
        self.vulns = [v.model_copy(deep=True) for v in VULNS]
        self.verdicts = dict(VERDICTS)
        self.reach_error: dict[str, Exception] = {}
        self.reach_delay = 0.0
        self.fix_status = "fixed"
        self.b2_error: Exception | None = None
        self.b3_error: Exception | None = None
        self.pr_error: Exception | None = None
        monkeypatch.setattr(cloner, "clone", self.clone)
        monkeypatch.setattr(scanner, "scan", self.scan)
        for name, module, attr, fn in (("symbols", symbols, "extract", self.extract),
                                       ("reachability", reachability, "analyze", self.analyze),
                                       ("fix", fixer, "fix_package", self.fix_package),
                                       ("pr", github_pr, "open_pr", self.open_pr),
                                       ("notify", boomi_client, "notify_finding", self.notify),
                                       ("summary", boomi_client, "send_scan_summary", self.summary)):
            if name not in stubs:
                monkeypatch.setattr(module, attr, fn)

    async def clone(self, repo_url: str, branch: str, scan_id: str) -> Path:
        dest = cloner.scan_dir(scan_id) / "repo"
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "requirements.txt").write_text("PyYAML==5.3.1\n", encoding="utf-8")
        self.cloned.append(dest)
        return dest

    async def scan(self, path: Path) -> list[RawVuln]:
        return [v.model_copy(deep=True) for v in self.vulns]

    async def extract(self, vuln: RawVuln) -> VulnSymbols:
        return VulnSymbols(package=vuln.package, symbols=[f"{vuln.package}.load"], confidence=0.9)

    async def analyze(self, repo_path: Path, vuln: RawVuln, syms: VulnSymbols) -> Verdict:
        self.reach_active += 1
        self.reach_max = max(self.reach_max, self.reach_active)
        try:
            await asyncio.sleep(self.reach_delay or 0.01)
            if vuln.cve_id in self.reach_error:
                raise self.reach_error[vuln.cve_id]
            reach, conf, in_route = self.verdicts[vuln.cve_id]
            ev = [Evidence(file="app/routes.py", line=42, in_route=in_route)] if reach != "not_reachable" else []
            return Verdict(reachable=reach, confidence=conf, evidence=ev, explanation=f"{reach} because test")
        finally:
            self.reach_active -= 1

    async def fix_package(self, scan_id: str, repo_path: Path, package: str, vulns: list[RawVuln]) -> FixResult:
        self.fix_calls.append((package, sorted(v.cve_id for v in vulns)))
        if self.fix_status == "needs_human":
            return FixResult(package=package, status="needs_human", reason="tests_failed", attempts=2)
        return FixResult(package=package, new_version="5.4.1", patch_diff="-PyYAML==5.3.1\n+PyYAML==5.4.1\n",
                         tests_passed=self.fix_status == "fixed", attempts=1, branch=f"patchpilot/{package}-5.4.1",
                         status=self.fix_status)

    async def open_pr(self, repo_url, branch, fix, findings) -> str:  # noqa: ANN001
        self.pr_calls.append((fix.package, sorted(f.cve_id for f in findings)))
        if self.pr_error:
            raise self.pr_error
        return f"{repo_url}/pull/{len(self.pr_calls)}"

    async def notify(self, payload: dict) -> B2Response:
        self.b2.append(payload)
        if self.b2_error:
            raise self.b2_error
        n = 100 + len(self.b2)
        return B2Response(ok=True, jira_key=f"SEC-{n}", jira_url=f"https://x.atlassian.net/browse/SEC-{n}",
                          slack_sent=True, compliance_log_id=f"log_{payload['finding_id']}")

    async def summary(self, payload: dict) -> B3Response:
        self.b3.append(payload)
        if self.b3_error:
            raise self.b3_error
        return B3Response(ok=True, slack_sent=True)


@pytest.fixture
def fakes(monkeypatch):
    return Fakes(monkeypatch)


def _events(client, scan_id: str) -> list[dict]:
    with client.stream("GET", f"/api/scans/{scan_id}/events") as r:
        assert r.status_code == 200
        return [json.loads(line[5:]) for line in r.iter_lines() if line.startswith("data:")]


def _start(client, body: dict | None = None, **headers: str) -> str:
    r = client.post("/api/scans", json=body or BODY, headers=headers)
    assert r.status_code == 202, r.text
    assert r.json()["status"] in ("queued", "running")
    return r.json()["scan_id"]


def _finding(scan_id: str, cve: str):  # noqa: ANN202
    f = next(f for f in repo.list_findings(scan_id=scan_id) if f.cve_id == cve)
    return repo.get_finding(f.finding_id)


# --------------------------------------------------------------------------- acceptance: full run


def test_post_scan_streams_every_stage_and_saves_stats(client, fakes):
    scan_id = _start(client)
    events = _events(client, scan_id)
    seen = [e["stage"] for e in events]
    assert [s for s in STAGES if s in seen] == STAGES  # every stage, in order
    assert seen.index("clone") < seen.index("scan") < seen.index("notify") < seen.index("done")
    assert events[-1]["stage"] == "done" and events[-1]["status"] == "completed" and events[-1]["progress"] == 1.0
    assert all(set(e) == {"scan_id", "stage", "status", "message", "progress", "data"} for e in events)
    progress = [e["progress"] for e in events]
    assert progress == sorted(progress)

    scan = client.get(f"/api/scans/{scan_id}").json()
    assert scan["status"] == "completed" and scan["current_stage"] == "done" and scan["finished_at"]
    assert scan["languages"] == [{"ecosystem": "PyPI", "manifests": ["requirements.txt"], "analysis": "deep"}]
    assert scan["stats"] == {"total_alerts": 4, "reachable": 2, "unsure": 1, "not_reachable": 1, "p1": 2, "p2": 0,
                             "fixed": 2, "prs_opened": 1}
    assert events[-1]["data"]["stats"] == scan["stats"]

    y1 = _finding(scan_id, "CVE-2020-14343")
    assert y1.status == "fixed" and y1.priority == "P1" and y1.vulnerable_symbols == ["pyyaml.load"]
    assert y1.fix and y1.fix.pr_url == f"{URL}/pull/1" and y1.fix.tests_passed
    assert y1.integration and y1.integration.jira_key and y1.integration.slack_sent
    assert [t.stage for t in y1.timeline][:1] == ["scan"] and "notify" in [t.stage for t in y1.timeline]
    assert _finding(scan_id, "CVE-2023-32681").status == "open"  # not routed: untouched
    assert not cloner.scan_dir(scan_id).exists()  # workdir cleaned


def test_l7_one_fix_and_one_pr_per_package_notify_per_finding(client, fakes):
    scan_id = _start(client)
    assert fakes.fix_calls == [("pyyaml", ["CVE-2020-14343", "CVE-2020-1747"])]
    assert fakes.pr_calls == [("pyyaml", ["CVE-2020-14343", "CVE-2020-1747"])]
    assert sorted(p["cve_id"] for p in fakes.b2) == ["CVE-2020-14343", "CVE-2020-1747"]
    assert {p["pr_url"] for p in fakes.b2} == {f"{URL}/pull/1"}  # shared PR
    a, b = _finding(scan_id, "CVE-2020-14343"), _finding(scan_id, "CVE-2020-1747")
    assert a.fix == b.fix  # same fix row
    assert len(fakes.b3) == 1 and fakes.b3[0]["scan_id"] == scan_id and fakes.b3[0]["event"] == "scan.completed"
    assert fakes.b3[0]["dashboard_url"].endswith(f"/scans/{scan_id}")


def test_b2_payload_matches_contract_keys(client, fakes):
    from tests.seed import contract

    _start(client)
    expected = contract("boomi/B2_finding_request.json")
    p = fakes.b2[0]
    assert set(p) == set(expected)
    assert set(p["evidence"][0]) == set(expected["evidence"][0])
    assert p["event"] == "finding.fixed" and p["fix_status"] == "fixed" and p["tests_passed"] is True
    assert p["owner_email"] == "owner@easystepin.com" and p["detected_at"].endswith("Z")


def test_routing_unsure_threshold(client, fakes):
    fakes.verdicts["CVE-2024-22195"] = ("unsure", 0.5, False)
    _start(client)
    assert ("jinja2", ["CVE-2024-22195"]) in fakes.fix_calls
    assert pipeline.is_routed("unsure", 0.5) and not pipeline.is_routed("unsure", 0.49)
    assert pipeline.is_routed("reachable", 0.1) and not pipeline.is_routed("not_reachable", 1.0)


def test_auto_fix_false_skips_fix_and_pr_but_notifies_open(client, fakes):
    scan_id = _start(client, {**BODY, "auto_fix": False})
    events = _events(client, scan_id)
    assert {e["status"] for e in events if e["stage"] in ("fix", "pr")} == {"skipped"}
    assert fakes.fix_calls == [] and fakes.pr_calls == []
    assert len(fakes.b2) == 2
    assert all(p["event"] == "finding.open" and p["fix_status"] == "not_attempted" and p["pr_url"] is None
               for p in fakes.b2)
    assert _finding(scan_id, "CVE-2020-14343").status == "open"


def test_needs_human_and_fixed_untested_map_to_b2(client, fakes):
    fakes.fix_status = "needs_human"
    scan_id = _start(client)
    assert fakes.pr_calls == []
    assert {p["event"] for p in fakes.b2} == {"finding.needs_human"}
    assert _finding(scan_id, "CVE-2020-14343").status == "needs_human"

    bus.clear()
    repo.clear_all()
    fakes.b2.clear()
    fakes.fix_status = "fixed_untested"
    _start(client)
    assert {(p["event"], p["fix_status"], p["tests_passed"]) for p in fakes.b2} == {("finding.fixed", "fixed_untested", False)}


def test_pipeline_completes_with_every_other_stage_stubbed(client, monkeypatch, caplog):
    """Modules of lanes not merged yet raise NotImplementedError -> clearly logged stub results."""
    f = Fakes(monkeypatch, stubs=("symbols", "reachability", "fix", "pr", "notify", "summary"))
    with caplog.at_level(logging.WARNING, logger="patchpilot.pipeline"):
        scan_id = _start(client)
    events = _events(client, scan_id)
    assert events[-1]["stage"] == "done" and events[-1]["status"] == "completed"
    assert [s for s in STAGES if s in {e["stage"] for e in events}] == STAGES
    stub_lines = [r.getMessage() for r in caplog.records if "STUB" in r.getMessage()]
    assert not any("stage reachability" in m for m in stub_lines)  # symbols (T05) and reachability (T06) are real now
    assert not any("stage risk" in m for m in stub_lines)  # risk (T07) is real now
    scan = repo.get_scan(scan_id)
    # the fake clone has no source code, so the real analyzer finds nothing imported
    assert scan.status == "completed" and scan.stats.total_alerts == 4 and scan.stats.not_reachable == 4
    assert all(x.score > 0 for x in repo.list_findings(scan_id=scan_id))  # stub risk formula ran
    assert f.fix_calls == []


# --------------------------------------------------------------------------- E3 / E4 / E5 / E6


def test_e3_failing_stage_for_one_finding_marks_it_and_continues(client, fakes):
    fakes.reach_error["CVE-2020-1747"] = RuntimeError("boom in analyzer")
    scan_id = _start(client)
    events = _events(client, scan_id)
    assert events[-1]["status"] == "completed"
    bad = _finding(scan_id, "CVE-2020-1747")
    assert bad.status == "needs_human"
    assert any(t.stage == "reachability" and "boom in analyzer" in t.message for t in bad.timeline)
    assert any(e["data"].get("failed") for e in events if e["stage"] == "reachability")
    assert fakes.fix_calls == [("pyyaml", ["CVE-2020-14343"])]  # the others continued
    assert _finding(scan_id, "CVE-2020-14343").status == "fixed"


def test_e3_failing_fix_or_pr_marks_findings_only(client, fakes):
    fakes.pr_error = RuntimeError("GitHub 502")
    scan_id = _start(client)
    assert repo.get_scan(scan_id).status == "completed"
    f = _finding(scan_id, "CVE-2020-14343")
    assert f.status == "needs_human" and any("GitHub 502" in t.message for t in f.timeline)
    assert {p["event"] for p in fakes.b2} == {"finding.needs_human"}


@pytest.mark.parametrize(("stage", "patch"), [
    ("clone", lambda f, mp: mp.setattr(cloner, "clone", _raise(CloneError("git clone failed: not found")))),
    ("scan", lambda f, mp: mp.setattr(scanner, "scan", _raise(scanner.ScanError("Vulnerability scan failed: x")))),
])
def test_e4_whole_scan_stage_failure(client, monkeypatch, stage, patch):
    f = Fakes(monkeypatch)
    patch(f, monkeypatch)
    scan_id = _start(client)
    events = _events(client, scan_id)
    assert events[-2]["stage"] == stage and events[-2]["status"] == "failed" and "failed" in events[-2]["message"]
    assert events[-1]["stage"] == "done" and events[-1]["status"] == "failed"
    scan = client.get(f"/api/scans/{scan_id}").json()
    assert scan["status"] == "failed" and scan["current_stage"] == stage and scan["finished_at"]
    assert not cloner.scan_dir(scan_id).exists()


def _raise(exc: Exception):  # noqa: ANN202
    async def fn(*a, **k):  # noqa: ANN002, ANN003, ANN202
        raise exc
    return fn


@pytest.fixture
def _keep_log_handlers():
    """The lifespan installs a log handler bound to this test's stderr; drop it so later tests get their own."""
    before = list(logging.getLogger().handlers)
    yield
    root = logging.getLogger()
    for h in list(root.handlers):
        if h not in before:
            root.removeHandler(h)


def test_e5_startup_marks_interrupted_scans_failed(app, _keep_log_handlers):
    from app.core.db import init_db

    init_db()
    running = repo.create_scan("Acme", URL, "main")
    repo.update_scan_stage(running, "reachability", "running")
    queued = repo.create_scan("Acme", URL, "dev")
    done = repo.create_scan("Acme", URL, "old")
    repo.update_scan_stage(done, "done", "completed")
    with TestClient(app) as c:  # runs the lifespan
        assert c.get(f"/api/scans/{running}").json()["status"] == "failed"
        assert c.get(f"/api/scans/{running}").json()["current_stage"] == "reachability"
        assert c.get(f"/api/scans/{queued}").json()["status"] == "failed"
        assert c.get(f"/api/scans/{done}").json()["status"] == "completed"
        events = _events(c, running)
        assert events[-1]["stage"] == "done" and "interrupted by restart" in events[-1]["message"]


async def test_e6_scan_timeout_fails_and_cleans(monkeypatch, fakes):
    from app.core.db import init_db

    init_db()
    monkeypatch.setenv("SCAN_TIMEOUT_S", "1")
    reset_settings_cache()
    fakes.reach_delay = 5
    scan_id = repo.create_scan("Acme", URL, "main")
    await asyncio.wait_for(pipeline.run_scan(scan_id), 4)
    scan = repo.get_scan(scan_id)
    assert scan.status == "failed" and scan.current_stage == "reachability"
    last = bus.history(scan_id)
    assert last[-1].stage == "done" and "timeout" in last[-1].message and "timed out" in last[-2].message
    assert not cloner.scan_dir(scan_id).exists()


# --------------------------------------------------------------------------- E7 + concurrency


async def test_e7_pipeline_never_blocks_event_loop_and_streams_live(fakes):
    from app.core.db import init_db

    init_db()
    fakes.reach_delay = 0.05
    scan_id = repo.create_scan("Acme", URL, "main")
    task = asyncio.create_task(pipeline.run_scan(scan_id))
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while not task.done():
            ticks += 1
            await asyncio.sleep(0.005)

    tick_task = asyncio.create_task(ticker())
    stages = [e.stage async for e in bus.subscribe(scan_id)]
    await task
    await tick_task
    assert stages[-1] == "done" and "reachability" in stages
    assert ticks > 5  # the loop kept running other coroutines during the scan


async def test_per_finding_work_runs_in_parallel_limit_4(monkeypatch, fakes):
    from app.core.db import init_db

    init_db()
    fakes.vulns = [VULNS[0].model_copy(update={"cve_id": f"CVE-2099-{i:04d}"}) for i in range(10)]
    fakes.verdicts = {v.cve_id: ("not_reachable", 0.9, False) for v in fakes.vulns}
    fakes.reach_delay = 0.05
    scan_id = repo.create_scan("Acme", URL, "main")
    await pipeline.run_scan(scan_id)
    assert fakes.reach_max == pipeline.CONCURRENCY == 4


async def test_e7_subprocess_killed_when_scan_is_cancelled(monkeypatch):
    procs = []
    real = asyncio.create_subprocess_exec

    async def spy(*a, **k):  # noqa: ANN002, ANN003, ANN202
        p = await real(*a, **k)
        procs.append(p)
        return p

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(subproc.run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=60), 0.5)
    if procs:  # Windows selector loops fall back to a thread and never reach here
        await asyncio.wait_for(procs[0].wait(), 5)
        assert procs[0].returncode is not None


# --------------------------------------------------------------------------- N6 Boomi never fails anything


def test_n6_boomi_failure_never_fails_scan_or_finding(client, fakes):
    fakes.b2_error = TimeoutError("Boomi timed out")
    fakes.b3_error = RuntimeError("Boomi 503")
    scan_id = _start(client)
    assert repo.get_scan(scan_id).status == "completed"
    f = _finding(scan_id, "CVE-2020-14343")
    assert f.status == "fixed" and f.integration is None
    assert any("Boomi notification failed" in t.message for t in f.timeline)
    events = repo.list_integration_events()
    assert {e.process for e in events if not e.ok} == {"B2", "B3"}
    assert all(not e.ok for e in events)


def test_n6_boomi_error_response_keeps_finding(client, fakes, monkeypatch):
    async def bad(payload: dict) -> B2Response:
        return B2Response(ok=False, error="jira_create_failed", message="Jira down")

    monkeypatch.setattr(boomi_client, "notify_finding", bad)
    scan_id = _start(client)
    f = _finding(scan_id, "CVE-2020-14343")
    assert f.status == "fixed" and any("jira_create_failed" in t.message for t in f.timeline)


# --------------------------------------------------------------------------- POST /api/scans hardening


@pytest.mark.parametrize("url", [
    "https://github.com/someone-else/repo",
    "https://gitlab.com/BommepalliRoop/demo-target",
    "https://github.com/BommepalliRoop/../evil/repo",
    "https://github.com/BommepalliRoop/%2e%2e/evil/repo",
    "https://github.com/BommepalliRoop%2F..%2Fevil",
    "https://github.com/BommepalliRoop/",
    "https://github.com/BommepalliRoopX/repo",
])
def test_s1_repo_not_allowed(client, fakes, url):
    r = client.post("/api/scans", json={**BODY, "repo_url": url})
    assert r.status_code == 400 and r.json()["error"]["code"] == "repo_not_allowed"
    assert repo.list_scans() == [] and fakes.cloned == []


def test_s1_prefix_list_is_configurable(client, fakes, monkeypatch):
    monkeypatch.setenv("ALLOWED_REPO_PREFIXES", "https://github.com/acme/, https://github.com/BommepalliRoop/")
    reset_settings_cache()
    assert client.post("/api/scans", json={**BODY, "repo_url": "https://github.com/acme/shop"}).status_code == 202


@pytest.mark.parametrize("change", [
    {"branch": "--upload-pack=touch /tmp/pwned"}, {"branch": "-x"}, {"branch": "main;rm -rf /"}, {"branch": "a" * 101},
    {"repo_url": "http://github.com/BommepalliRoop/demo-target"}, {"repo_url": "git@github.com:BommepalliRoop/x.git"},
    {"repo_url": "https://github.com/BommepalliRoop/demo target"}, {"client_name": ""},
])
def test_s3_invalid_request(client, fakes, change):
    r = client.post("/api/scans", json={**BODY, **change})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_request"
    assert repo.list_scans() == []


def test_s9_n9_duplicate_active_scan_returns_same_id(client, fakes):
    existing = repo.create_scan("Acme Retail", URL, "main")
    repo.update_scan_stage(existing, "scan", "running")
    for headers in ({}, {"X-API-Key": KEY}):  # dashboard and Boomi B1 retry
        r = client.post("/api/scans", json=BODY, headers=headers)
        assert r.status_code == 202 and r.json() == {"scan_id": existing, "status": "running"}
    assert len(repo.list_scans()) == 1 and fakes.cloned == []
    other_branch = client.post("/api/scans", json={**BODY, "branch": "dev"}).json()["scan_id"]
    assert other_branch != existing


def test_s9_rate_limited(client, fakes, monkeypatch):
    monkeypatch.setenv("MAX_SCANS_PER_HOUR", "2")
    reset_settings_cache()
    _start(client, {**BODY, "branch": "a"})
    _start(client, {**BODY, "branch": "b"})
    r = client.post("/api/scans", json={**BODY, "branch": "c"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    assert len(repo.list_scans()) == 2


def test_s10_api_key_compared_in_constant_time(client, fakes, monkeypatch):
    calls = []
    real = security.hmac.compare_digest

    def spy(a, b):  # noqa: ANN001, ANN202
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(security.hmac, "compare_digest", spy)
    r = client.post("/api/scans", json=BODY, headers={"X-API-Key": "wrong-key"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
    assert calls and repo.list_scans() == []
    assert client.post("/api/scans", json=BODY, headers={"X-API-Key": KEY}).status_code == 202


def test_b1_inbound_integration_event_recorded(client, fakes):
    scan_id = _start(client, None, **{"X-API-Key": KEY})
    events = repo.list_integration_events()
    b1 = [e for e in events if e.process == "B1"]
    assert len(b1) == 1 and b1[0].ok and b1[0].status_code == 202 and b1[0].endpoint == "/api/scans"
    assert scan_id in b1[0].summary
    r = client.post("/api/scans", json={**BODY, "repo_url": "https://github.com/evil/x"}, headers={"X-API-Key": KEY})
    assert r.status_code == 400
    b1 = [e for e in repo.list_integration_events() if e.process == "B1"]
    assert len(b1) == 2 and not b1[0].ok and b1[0].status_code == 400
    _start(client, {**BODY, "branch": "ui"})  # dashboard call: no B1 event
    assert len([e for e in repo.list_integration_events() if e.process == "B1"]) == 2


def test_b1_event_direction_is_inbound(client, fakes):
    from sqlmodel import Session, select

    from app.core.db import get_engine
    from app.models.tables import IntegrationEventRow

    _start(client, None, **{"X-API-Key": KEY})
    with Session(get_engine()) as s:
        row = s.exec(select(IntegrationEventRow).where(IntegrationEventRow.process == "B1")).one()
    assert row.direction == "in" and KEY not in row.request_json + row.response_json


# --------------------------------------------------------------------------- SSE N7 / N8


def test_n7_sse_headers(client, fakes):
    scan_id = _start(client)
    with client.stream("GET", f"/api/scans/{scan_id}/events") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        assert r.headers["cache-control"] == "no-cache" and r.headers["x-accel-buffering"] == "no"
    assert client.get("/api/scans/scn_nope/events").status_code == 404


def test_n7_sse_heartbeat_is_15s(client, fakes, monkeypatch):
    from app.api import scans as scans_api

    seen = {}
    real = scans_api.EventSourceResponse

    def spy(*a, **k):  # noqa: ANN002, ANN003, ANN202
        seen.update(k)
        return real(*a, **k)

    monkeypatch.setattr(scans_api, "EventSourceResponse", spy)
    _events(client, _start(client))
    assert seen["ping"] == 15


def test_n8_late_subscriber_gets_replay_and_restart_gets_done(client, fakes):
    scan_id = _start(client)
    first, second = _events(client, scan_id), _events(client, scan_id)
    assert first == second and first[0]["stage"] == "clone"
    bus.clear()  # events gone (restart / eviction): synthetic done from the DB
    only = _events(client, scan_id)
    assert len(only) == 1 and only[0]["stage"] == "done" and only[0]["status"] == "completed"
    assert only[0]["data"]["stats"]["total_alerts"] == 4


# --------------------------------------------------------------------------- POST /api/findings/{id}/fix


def test_manual_fix_reruns_fix_pr_and_notify(client, fakes):
    scan_id = _start(client, {**BODY, "auto_fix": False})
    f = _finding(scan_id, "CVE-2020-14343")
    fakes.b2.clear()
    r = client.post(f"/api/findings/{f.finding_id}/fix")
    assert r.status_code == 202 and r.json() == {"finding_id": f.finding_id, "status": "fixing"}
    # both routed pyyaml findings are fixed together (one fix per package)
    assert fakes.fix_calls == [("pyyaml", ["CVE-2020-14343", "CVE-2020-1747"])]
    after = repo.get_finding(f.finding_id)
    assert after.status == "fixed" and after.fix and after.fix.pr_url
    assert {p["finding_id"] for p in fakes.b2} >= {f.finding_id}
    assert all(p["event"] == "finding.fixed" for p in fakes.b2)
    assert any(t.message == "Manual fix requested" for t in after.timeline)
    assert len(fakes.cloned) == 2 and all(not p.exists() for p in fakes.cloned)  # fresh clone, cleaned


def test_manual_fix_conflict_and_not_found(client, fakes):
    scan_id = _start(client, {**BODY, "auto_fix": False})
    f = _finding(scan_id, "CVE-2020-14343")
    repo.update_finding(f.finding_id, status="fixing")
    r = client.post(f"/api/findings/{f.finding_id}/fix")
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    assert client.post("/api/findings/fnd_nope/fix").status_code == 404


def test_manual_fix_failure_marks_needs_human(client, fakes, monkeypatch):
    scan_id = _start(client, {**BODY, "auto_fix": False})
    f = _finding(scan_id, "CVE-2023-32681")
    monkeypatch.setattr(cloner, "clone", _raise(CloneError("git clone failed: gone")))
    assert client.post(f"/api/findings/{f.finding_id}/fix").status_code == 202
    after = repo.get_finding(f.finding_id)
    assert after.status == "needs_human" and any("gone" in t.message for t in after.timeline)


async def test_n8_big_scan_fits_in_replay_buffer(fakes):
    from app.core.db import init_db
    from app.core.events import REPLAY_SIZE

    init_db()
    fakes.vulns = [VULNS[0].model_copy(update={"cve_id": f"CVE-2099-{i:04d}"}) for i in range(150)]
    fakes.verdicts = {v.cve_id: ("not_reachable", 0.9, False) for v in fakes.vulns}
    scan_id = repo.create_scan("Acme", URL, "main")
    await pipeline.run_scan(scan_id)
    history = bus.history(scan_id)
    assert len(history) < REPLAY_SIZE and history[0].stage == "clone" and history[-1].stage == "done"
