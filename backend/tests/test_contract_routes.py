"""Every Part A endpoint exists and the stub responses match the contracts/ examples."""
from __future__ import annotations

import json

from app.core.config import REPO_ROOT


def _contract(name: str) -> dict:
    return json.loads((REPO_ROOT / "contracts" / name).read_text(encoding="utf-8"))


def test_create_scan_accepts_contract_request(client):
    body = _contract("api/scan_create_request.json")
    body["repo_url"] = "https://github.com/BommepalliRoop/demo-target"
    r = client.post("/api/scans", json=body)
    assert r.status_code == 202
    assert r.json() == {"scan_id": "scn_01", "status": "queued"}


def test_scan_shape(client):
    scans = client.get("/api/scans").json()
    assert scans and set(scans[0]) == {
        "scan_id", "client_name", "repo_url", "branch", "status", "current_stage",
        "started_at", "finished_at", "languages", "stats",
    }
    assert set(scans[0]["stats"]) == {"total_alerts", "reachable", "unsure", "not_reachable", "p1", "p2", "fixed", "prs_opened"}
    assert set(scans[0]["languages"][0]) == {"ecosystem", "manifests", "analysis"}
    assert client.get("/api/scans/scn_01").json()["scan_id"] == "scn_01"


def test_finding_summary_and_detail_shape(client):
    summary = client.get("/api/findings", params={"scan_id": "scn_01"}).json()[0]
    assert set(summary) == {
        "finding_id", "cve_id", "package", "installed_version", "fixed_version", "cvss", "reachability",
        "confidence", "score", "priority", "status", "kev", "epss", "epss_percentile", "ecosystem", "analysis",
    }
    detail = client.get("/api/findings/fnd_07").json()
    assert set(detail) == set(summary) | {
        "summary", "kev_date_added", "vulnerable_symbols", "evidence", "ai_explanation", "fix", "integration", "timeline",
    }
    assert set(detail["evidence"][0]) == {"file", "line", "in_route", "code_snippet", "start_line"}
    assert set(detail["fix"]) == {"new_version", "attempts", "tests_passed", "patch_diff", "pr_url", "status"}
    assert set(detail["integration"]) == {"jira_key", "jira_url", "teams_sent", "compliance_log_id"}


def test_finding_filters(client):
    assert [f["finding_id"] for f in client.get("/api/findings", params={"priority": "P1"}).json()] == ["fnd_07"]
    assert client.get("/api/findings", params={"reachability": "not_reachable"}).json()[0]["package"] == "requests"


def test_fix_endpoint(client):
    r = client.post("/api/findings/fnd_07/fix")
    assert r.status_code == 202 and r.json() == {"finding_id": "fnd_07", "status": "fixing"}
    assert client.post("/api/findings/fnd_99/fix").status_code == 404


def test_integration_activity_shape(client):
    row = client.get("/api/integrations/activity", params={"limit": 5}).json()[0]
    assert set(row) == {"id", "finding_id", "process", "endpoint", "status_code", "ok", "summary", "created_at"}


def test_compliance_matches_b4_contract_shape(client):
    contract = _contract("boomi/B4_compliance_response.json")
    body = client.get("/api/compliance", params={"client_name": "Acme Retail", "from": "2026-10-01"}).json()
    assert set(body) == set(contract)
    assert set(body["items"][0]) == set(contract["items"][0])


def test_sse_stream_ends_with_done(client):
    with client.stream("GET", "/api/scans/scn_01/events") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        assert r.headers["cache-control"] == "no-cache" and r.headers["x-accel-buffering"] == "no"
        events = [json.loads(line[5:]) for line in r.iter_lines() if line.startswith("data:")]
    assert [e["stage"] for e in events][-1] == "done"
    assert set(events[0]) == {"scan_id", "stage", "status", "message", "progress", "data"}
    assert client.get("/api/scans/nope/events").status_code == 404
