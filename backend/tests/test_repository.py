"""T01 acceptance: create / read / filter, E8 (SQLite concurrency), L10 (UTC timestamps), S4 (redaction)."""
from __future__ import annotations

import re
import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.core.db import get_engine, init_db
from app.core.ids import iso_z
from app.models import repository as repo
from tests.seed import seed_contract_scan, seed_extra_findings

ISO_Z = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
URL = "https://github.com/BommepalliRoop/a"


@pytest.fixture(autouse=True)
def _db():
    init_db()


def _finding(scan_id: str, **kw) -> str:
    data = {"cve_id": "CVE-1", "package": "p", "installed_version": "1", **kw}
    return repo.add_finding(scan_id, repo.FindingCreate(**data))


def test_id_prefixes():
    scan_id = repo.create_scan("Acme", URL)
    fnd = _finding(scan_id)
    fix = repo.add_fix(scan_id, "p", finding_ids=[fnd])
    assert scan_id.startswith("scn_") and fnd.startswith("fnd_") and fix.startswith("fix_")


def test_scan_create_read_update():
    scan_id = repo.create_scan("Acme", URL, "dev", auto_fix=False, owner_email="o@x.com")
    scan = repo.get_scan(scan_id)
    assert scan and scan.status == "queued" and scan.branch == "dev" and scan.finished_at is None
    repo.update_scan_stage(scan_id, "scan", "running")
    assert repo.get_scan(scan_id).current_stage == "scan"
    repo.update_scan_stage(scan_id, "done", "completed")
    done = repo.get_scan(scan_id)
    assert done and done.status == "completed" and done.finished_at
    assert repo.get_scan("scn_missing") is None
    with pytest.raises(LookupError):
        repo.update_scan_stage("scn_missing", "scan")


def test_list_scans_newest_first_and_filters():
    a = repo.create_scan("Acme", URL)
    b = repo.create_scan("Beta", "https://github.com/BommepalliRoop/b")
    repo.update_scan_stage(b, "done", "completed")
    assert [s.scan_id for s in repo.list_scans()] == [b, a]
    assert [s.scan_id for s in repo.list_scans(client_name="Acme")] == [a]
    assert [s.scan_id for s in repo.list_scans(status="completed")] == [b]


def test_find_active_scan_guard():
    a = repo.create_scan("Acme", URL)
    active = repo.find_active_scan(URL, "main")
    assert active and active.scan_id == a
    assert repo.find_active_scan(URL, "other") is None
    repo.update_scan_stage(a, "done", "completed")
    assert repo.find_active_scan(URL, "main") is None
    assert repo.count_scans_since("2000-01-01T00:00:00Z") == 1


def test_finding_detail_roundtrip_with_fix_and_integration():
    _, fnd = seed_contract_scan()
    d = repo.get_finding(fnd)
    assert d
    assert d.vulnerable_symbols == ["yaml.load", "yaml.full_load"]
    assert d.evidence[0].line == 42 and d.evidence[0].in_route
    assert d.fix and d.fix.pr_url and d.fix.new_version == "5.4.1" and d.fix.tests_passed
    assert d.integration and d.integration.jira_key == "SEC-101" and d.integration.slack_sent
    assert d.timeline[0].stage == "scan"
    repo.append_timeline(fnd, "fix", "Upgraded")
    assert [t.stage for t in repo.get_finding(fnd).timeline] == ["scan", "fix"]


def test_finding_without_fix_or_integration_has_nulls():
    fnd = _finding(repo.create_scan("Acme", URL))
    d = repo.get_finding(fnd)
    assert d and d.fix is None and d.integration is None
    assert repo.get_finding("fnd_missing") is None


def test_finding_filters_and_order():
    scan_id, fnd = seed_contract_scan()
    seed_extra_findings(scan_id)
    other = repo.create_scan("Beta", "https://github.com/BommepalliRoop/b")
    _finding(other, cve_id="CVE-9", package="z", score=9.5, priority="P1")
    assert len(repo.list_findings()) == 4
    assert [f.score for f in repo.list_findings(scan_id=scan_id)] == [10.0, 3.2, 1.8]
    assert [f.finding_id for f in repo.list_findings(scan_id=scan_id, priority="P1")] == [fnd]
    assert [f.package for f in repo.list_findings(reachability="not_reachable")] == ["requests"]
    assert [f.package for f in repo.list_findings(status="fixed")] == ["pyyaml"]
    assert repo.list_findings(scan_id=scan_id, priority="P1", reachability="unsure") == []


def test_update_finding_rejects_unknown_fields_and_serialises_lists():
    fnd = _finding(repo.create_scan("Acme", URL))
    with pytest.raises(ValueError):
        repo.update_finding(fnd, nope=1)
    repo.update_finding(fnd, status="fixing", vulnerable_symbols=["a.b"], reachability="reachable", priority="P2")
    d = repo.get_finding(fnd)
    assert d and d.status == "fixing" and d.vulnerable_symbols == ["a.b"] and d.priority == "P2"


def test_scan_stats_computed_from_findings():
    scan_id, _ = seed_contract_scan()
    seed_extra_findings(scan_id)
    stats = repo.get_scan(scan_id).stats
    assert stats.model_dump() == {"total_alerts": 3, "reachable": 1, "unsure": 1, "not_reachable": 1,
                                  "p1": 1, "p2": 0, "fixed": 1, "prs_opened": 1}


def test_grouped_fix_counts_one_pr_for_many_findings():
    scan_id = repo.create_scan("Acme", URL)
    ids = [_finding(scan_id, cve_id=f"CVE-{i}", package="requests") for i in range(3)]
    repo.add_fix(scan_id, "requests", "2.31.0", pr_url="https://github.com/x/y/pull/1", status="fixed", finding_ids=ids)
    assert repo.get_scan(scan_id).stats.prs_opened == 1
    assert {repo.get_finding(i).fix.pr_url for i in ids} == {"https://github.com/x/y/pull/1"}


def test_update_fix():
    scan_id = repo.create_scan("Acme", URL)
    fnd = _finding(scan_id)
    fix = repo.add_fix(scan_id, "p", finding_ids=[fnd])
    assert repo.get_finding(fnd).fix.status == "needs_human"
    repo.update_fix(fix, status="fixed", tests_passed=True, attempts=2, new_version="2")
    f = repo.get_finding(fnd).fix
    assert f and f.status == "fixed" and f.attempts == 2
    with pytest.raises(ValueError):
        repo.update_fix(fix, bogus=1)


def test_integration_events_newest_first_limit_and_redaction():
    for i in range(3):
        repo.add_integration_event("B2", "/patchpilot/findings", True, finding_id=f"fnd_{i}", status_code=200,
                                   summary=f"event {i}")
    repo.add_integration_event("B3", "/patchpilot/scan-summary", False, status_code=500,
                               request={"Authorization": "Bearer abcdefghijkl123456"},
                               summary="failed with ghp_abcdefghijklmnop1234")
    events = repo.list_integration_events(limit=3)
    assert [e.process for e in events] == ["B3", "B2", "B2"]
    assert events[0].finding_id is None and "ghp_" not in events[0].summary
    assert len(repo.list_integration_events(finding_id="fnd_1")) == 1
    with repo._session() as s:
        raw = s.exec(text("select request_json from integration_events where process='B3'")).one()[0]
    assert "abcdefghijkl123456" not in raw


def test_clear_all():
    seed_contract_scan()
    repo.add_integration_event("B2", "/x", True)
    repo.clear_all()
    assert repo.list_scans() == [] and repo.list_findings() == [] and repo.list_integration_events() == []


# ---- RISKS E8: SQLite stays usable under concurrent writes
def test_e8_wal_and_busy_timeout():
    with get_engine().connect() as c:
        assert c.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert c.exec_driver_sql("PRAGMA busy_timeout").scalar() == 5000


def test_e8_concurrent_writes_do_not_lock():
    scan_id = repo.create_scan("Acme", URL)
    errors: list[Exception] = []

    def worker(n: int) -> None:
        try:
            for i in range(10):
                fid = _finding(scan_id, cve_id=f"CVE-{n}-{i}")
                repo.update_finding(fid, status="fixing")
                repo.add_integration_event("B2", "/x", True, finding_id=fid)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert repo.get_scan(scan_id).stats.total_alerts == 60
    assert len(repo.list_integration_events(limit=500)) == 60


# ---- RISKS L10: timezone-aware UTC, ISO-8601 with Z
def test_l10_timestamps_are_utc_z():
    scan_id, fnd = seed_contract_scan()
    repo.add_integration_event("B2", "/x", True)
    scan = repo.get_scan(scan_id)
    assert scan and ISO_Z.match(scan.started_at or "") and ISO_Z.match(scan.finished_at or "")
    repo.append_timeline(fnd, "fix", "x")
    assert all(ISO_Z.match(t.at) for t in repo.get_finding(fnd).timeline)
    assert ISO_Z.match(repo.list_integration_events()[0].created_at)
    plus2 = datetime(2026, 10, 28, 7, 0, 0, tzinfo=timezone(timedelta(hours=2)))
    assert iso_z(plus2) == "2026-10-28T05:00:00Z"
    assert iso_z(datetime(2026, 10, 28, 5, 0, 0)) == "2026-10-28T05:00:00Z"
