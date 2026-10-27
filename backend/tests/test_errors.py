"""E1 global handlers, E2 validation mapping."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_unhandled_exception_returns_envelope_without_trace(app):
    async def boom() -> None:
        raise RuntimeError("secret detail at /srv/app/secret.py ghp_" + "X" * 30)

    app.add_api_route("/api/boom", boom)
    r = TestClient(app, raise_server_exceptions=False).get("/api/boom")
    assert r.status_code == 500
    assert r.json() == {"error": {"code": "internal_error", "message": "Internal server error"}}
    assert "Traceback" not in r.text and "secret.py" not in r.text


def test_validation_error_maps_to_400_with_field_names(client):
    r = client.post("/api/scans", json={"client_name": "Acme", "repo_url": "http://insecure.example/x"})
    assert r.status_code == 400
    body = r.json()["error"]
    assert body["code"] == "invalid_request"
    assert "repo_url" in body["message"]


def test_missing_field_names_listed(client):
    r = client.post("/api/scans", json={})
    assert r.status_code == 400
    msg = r.json()["error"]["message"]
    assert "client_name" in msg and "repo_url" in msg


def test_bad_query_enum_is_400(client):
    r = client.get("/api/findings", params={"priority": "P9"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_request"


def test_branch_injection_rejected(client):
    for branch in ("--upload-pack=evil", "a b", "x;rm", ""):
        r = client.post("/api/scans", json={"client_name": "A", "repo_url": "https://github.com/o/r", "branch": branch})
        assert r.status_code == 400, branch


def test_not_found_uses_envelope(client):
    r = client.get("/api/scans/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_method_not_allowed_uses_envelope(client):
    r = client.delete("/api/health")
    assert r.status_code == 405 and "error" in r.json()
