"""T17 demo seed: `python -m app.seed` gives the dashboard 2 historical scans, offline (RISKS O1)."""
from __future__ import annotations

from datetime import datetime

from app import seed
from app.core.ids import utcnow
from app.models import repository as repo
from app.services import github_pr

ISO_Z = "%Y-%m-%dT%H:%M:%SZ"


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts, ISO_Z).replace(tzinfo=utcnow().tzinfo)


def test_seed_adds_two_completed_historical_scans_newest_is_the_demo():
    result = seed.seed()
    scans = repo.list_scans()
    assert [s.scan_id for s in scans] == list(reversed(result.scan_ids))
    demo, clean = scans
    assert (demo.client_name, demo.repo_url) == ("Acme Retail", seed.DEMO_REPO)
    assert clean.client_name == "Globex Logistics" and clean.stats.total_alerts == 0
    for s in scans:
        assert s.status == "completed" and s.current_stage == "done"
        assert s.started_at.endswith("Z") and s.finished_at.endswith("Z")  # L10
        assert _parse(s.started_at) < _parse(s.finished_at) < utcnow()
    assert [lang.ecosystem for lang in demo.languages] == ["PyPI", "npm"]


def test_demo_scan_tells_the_noise_to_signal_story():
    seed.seed()
    demo = repo.list_scans()[0]
    st = demo.stats
    assert st.total_alerts == len(seed.advisories()) == 40
    assert (st.reachable, st.p1, st.prs_opened) == (1, 1, 2)
    assert st.not_reachable + st.unsure + st.reachable == st.total_alerts
    p1 = repo.list_findings(scan_id=demo.scan_id, priority="P1")
    assert [(f.package, f.cve_id, f.status) for f in p1] == [("pyyaml", "CVE-2020-14343", "fixed")]

    d = repo.get_finding(p1[0].finding_id)
    assert d is not None and d.evidence[0].in_route and d.evidence[0].file == "demo_app/importer.py"
    assert d.fix is not None and d.fix.tests_passed and d.fix.attempts == 1 and d.fix.new_version == "6.0.3"
    assert "Loader=yaml.SafeLoader" in d.fix.patch_diff
    assert d.integration is not None and d.integration.jira_key and d.integration.slack_sent
    stages = [t.stage for t in d.timeline]
    assert stages == ["scan", "symbols", "reachability", "risk", "fix", "pr", "notify"]
    assert [t.at for t in d.timeline] == sorted(t.at for t in d.timeline)
    assert all(_parse(t.at) <= _parse(demo.finished_at) for t in d.timeline)


def test_routed_findings_share_one_pr_per_package_and_each_got_a_b2_event():
    seed.seed()
    demo = repo.list_scans()[0]
    fixed = repo.list_findings(scan_id=demo.scan_id, status="fixed")
    assert {f.package for f in fixed} == {"pyyaml", "requests"}
    prs = {f.package: repo.get_finding(f.finding_id).fix.pr_url for f in fixed}  # type: ignore[union-attr]
    assert len(set(prs.values())) == 2
    for url in prs.values():
        github_pr.parse_repo(url.rsplit("/pull/", 1)[0])  # a demo-target URL
    events = repo.list_integration_events(limit=100)
    b2 = [e for e in events if e.process == "B2"]
    assert {e.finding_id for e in b2} == {f.finding_id for f in fixed}
    assert all(e.ok and e.status_code == (202 if e.process == "B1" else 200) for e in events)
    assert sum(e.process == "B1" for e in events) == 2 and sum(e.process == "B3" for e in events) == 2
    assert all(_parse(e.created_at) < utcnow() for e in events)


def test_seeded_scans_are_served_by_the_api_in_contract_shape(client):
    seed.seed()
    scans = client.get("/api/scans").json()
    assert len(scans) == 2 and scans[0]["stats"]["p1"] == 1
    findings = client.get("/api/findings", params={"scan_id": scans[0]["scan_id"], "priority": "P1"}).json()
    detail = client.get(f"/api/findings/{findings[0]['finding_id']}").json()
    assert detail["integration"]["jira_url"].startswith(seed.JIRA_BROWSE)
    assert client.get("/api/integrations/activity").status_code == 200


def test_cli_if_empty_is_idempotent_and_reset_starts_over(capsys):
    assert seed.main([]) == 0
    assert seed.main(["--if-empty"]) == 0
    assert len(repo.list_scans()) == 2
    assert "nothing to do" in capsys.readouterr().out
    assert seed.main(["--reset"]) == 0
    assert len(repo.list_scans()) == 2  # reset, then seeded once
    assert seed.main([]) == 0
    assert len(repo.list_scans()) == 4
