"""Every Part A endpoint exists and the stub responses match the contracts/ examples."""
from __future__ import annotations

import json

from app.models import repository as repo
from tests.seed import contract, seed_contract_scan, seed_extra_findings


def test_create_scan_accepts_contract_request(client):
    body = contract("api/scan_create_request.json")
    body["repo_url"] = "https://github.com/BommepalliRoop/demo-target"
    repo.update_scan_stage(repo.create_scan("x", body["repo_url"], body["branch"]), "clone", "running")
    r = client.post("/api/scans", json=body)  # duplicate guard: returns the active scan, starts nothing
    assert r.status_code == 202
    assert set(r.json()) == {"scan_id", "status"} and r.json()["status"] == "running"


def test_scan_shape(client):
    scan_id, _ = seed_contract_scan()
    scans = client.get("/api/scans").json()
    assert scans and set(scans[0]) == {
        "scan_id", "client_name", "repo_url", "branch", "status", "current_stage",
        "started_at", "finished_at", "languages", "stats",
    }
    assert set(scans[0]["stats"]) == {"total_alerts", "reachable", "unsure", "not_reachable", "p1", "p2", "fixed", "prs_opened"}
    assert set(scans[0]["languages"][0]) == {"ecosystem", "manifests", "analysis"}
    assert client.get(f"/api/scans/{scan_id}").json()["scan_id"] == scan_id
    assert client.get("/api/scans/scn_nope").status_code == 404


def test_finding_summary_and_detail_shape(client):
    scan_id, fnd = seed_contract_scan()
    summary = client.get("/api/findings", params={"scan_id": scan_id}).json()[0]
    assert set(summary) == {
        "finding_id", "cve_id", "package", "installed_version", "fixed_version", "cvss", "reachability",
        "confidence", "score", "priority", "status", "kev", "epss", "epss_percentile", "ecosystem", "analysis",
    }
    detail = client.get(f"/api/findings/{fnd}").json()
    assert set(detail) == set(summary) | {
        "summary", "kev_date_added", "vulnerable_symbols", "evidence", "ai_explanation", "fix", "integration", "timeline",
    }
    assert set(detail["evidence"][0]) == {"file", "line", "in_route", "code_snippet", "start_line"}
    assert set(detail["fix"]) == {"new_version", "attempts", "tests_passed", "patch_diff", "pr_url", "status"}
    assert set(detail["integration"]) == {"jira_key", "jira_url", "slack_sent", "compliance_log_id"}
    assert client.get("/api/findings/fnd_nope").status_code == 404


def test_finding_filters(client):
    scan_id, fnd = seed_contract_scan()
    seed_extra_findings(scan_id)
    assert [f["finding_id"] for f in client.get("/api/findings", params={"priority": "P1"}).json()] == [fnd]
    assert client.get("/api/findings", params={"reachability": "not_reachable"}).json()[0]["package"] == "requests"
    assert client.get("/api/findings", params={"scan_id": "scn_other"}).json() == []


def test_fix_endpoint(client):
    _, fnd = seed_contract_scan()
    r = client.post(f"/api/findings/{fnd}/fix")
    assert r.status_code == 202 and r.json() == {"finding_id": fnd, "status": "fixing"}
    assert client.post("/api/findings/fnd_99/fix").status_code == 404


def test_integration_activity_shape(client):
    c = contract("api/integration_event.json")
    repo.add_integration_event("B2", c["endpoint"], True, finding_id="fnd_07", status_code=200, summary=c["summary"])
    row = client.get("/api/integrations/activity", params={"limit": 5}).json()[0]
    assert set(row) == set(c)


def test_compliance_matches_b4_contract_shape(client):
    expected = contract("boomi/B4_compliance_response.json")
    body = client.get("/api/compliance", params={"client_name": "Acme Retail", "from": "2026-10-01"}).json()
    assert set(body) == set(expected)
    assert set(body["items"][0]) == set(expected["items"][0])


def test_sse_stream_ends_with_done(client):
    scan_id, _ = seed_contract_scan()
    with client.stream("GET", f"/api/scans/{scan_id}/events") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        assert r.headers["cache-control"] == "no-cache" and r.headers["x-accel-buffering"] == "no"
        events = [json.loads(line[5:]) for line in r.iter_lines() if line.startswith("data:")]
    assert [e["stage"] for e in events][-1] == "done"
    assert set(events[0]) == {"scan_id", "stage", "status", "message", "progress", "data"}
    assert client.get("/api/scans/nope/events").status_code == 404
