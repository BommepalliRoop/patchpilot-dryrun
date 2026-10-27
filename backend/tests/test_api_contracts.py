"""API responses from the DB validate against the example JSON in contracts/api (and the schemas accept them)."""
from __future__ import annotations

from app.core.config import reset_settings_cache
from app.models import repository as repo
from app.models.schemas import FindingDetail, IntegrationEvent, Scan
from tests.seed import contract, seed_contract_scan

KEY = "test-api-key-0123456789abcdef"


def _types(value):  # structural fingerprint: key sets and value types, recursively
    if isinstance(value, dict):
        return {k: _types(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_types(value[0])] if value else []
    return type(value).__name__


def test_contract_examples_parse_with_schemas():
    Scan.model_validate(contract("api/scan.json"))
    FindingDetail.model_validate(contract("api/finding_detail.json"))
    IntegrationEvent.model_validate(contract("api/integration_event.json"))


def test_scan_response_matches_contract(client):
    scan_id, _ = seed_contract_scan()
    body = client.get(f"/api/scans/{scan_id}").json()
    expected = contract("api/scan.json")
    assert _types(body) == _types(expected)
    for key in ("client_name", "repo_url", "branch", "status", "current_stage", "languages"):
        assert body[key] == expected[key]


def test_finding_detail_response_equals_contract_values(client):
    _, fnd = seed_contract_scan()
    body = client.get(f"/api/findings/{fnd}").json()
    expected = contract("api/finding_detail.json")
    assert body.pop("finding_id") == fnd
    expected.pop("finding_id")
    assert body == expected


def test_finding_summary_is_detail_subset(client):
    scan_id, _ = seed_contract_scan()
    summary = client.get("/api/findings", params={"scan_id": scan_id}).json()[0]
    expected = contract("api/finding_detail.json")
    keys = set(summary) - {"finding_id"}
    assert {k: summary[k] for k in keys} == {k: expected[k] for k in keys}


def test_integration_activity_matches_contract(client):
    c = contract("api/integration_event.json")
    repo.add_integration_event(c["process"], c["endpoint"], c["ok"], finding_id=c["finding_id"],
                               status_code=c["status_code"], summary=c["summary"])
    row = client.get("/api/integrations/activity").json()[0]
    assert _types(row) == _types(c)
    same = ("finding_id", "process", "endpoint", "status_code", "ok", "summary")
    assert {k: row[k] for k in same} == {k: c[k] for k in same}


def test_demo_reset_clears_db(client, monkeypatch):
    seed_contract_scan()
    monkeypatch.setenv("DEMO_MODE", "true")
    reset_settings_cache()
    assert client.post("/api/demo/reset").status_code == 401  # S8: no key leaves data intact
    assert client.get("/api/scans").json() != []
    r = client.post("/api/demo/reset", headers={"X-API-Key": KEY})
    assert r.status_code == 200
    assert client.get("/api/scans").json() == [] and client.get("/api/findings").json() == []


def test_demo_reset_404_when_demo_mode_off_keeps_data(client):
    seed_contract_scan()
    assert client.post("/api/demo/reset", headers={"X-API-Key": KEY}).status_code == 404
    assert len(client.get("/api/scans").json()) == 1
