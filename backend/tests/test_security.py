"""S4 redact(), S12 CORS, S13 gitignore, S8 demo reset auth."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.core.config import REPO_ROOT, reset_settings_cache
from app.core.events import ScanEvent, bus
from app.core.logging import log_context, setup_logging
from app.core.security import redact


@pytest.mark.parametrize(
    "secret",
    [
        "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8",
        "github_pat_" + "11ABCDEFG0abcdefghijkl_mnopqrstuvwxyz0123456789",
        "sk-" + "ant-api03-abcdefghijklmnop",
        "glpat-" + "abcdefghijklmnopqrst",
    ],
)
def test_redact_token_formats(secret):
    out = redact(f"failed with token {secret} in header")
    assert secret not in out
    assert "***" in out


def test_redact_bearer_and_url_credentials():
    assert "abc123def456" not in redact("Authorization: Bearer abc123def456")
    assert "abc123def456" not in redact("curl -H 'Authorization: Basic abc123def456'")
    out = redact("cloning https://x-access-token:s3cr3tvalue@github.com/org/repo.git")
    assert "s3cr3tvalue" not in out and "github.com/org/repo.git" in out
    assert "supersecretkey1" not in redact("X-API-Key: supersecretkey1")


def test_redact_configured_secret_and_plain_text(monkeypatch):
    monkeypatch.setenv("BOOMI_TOKEN", "boomi-opaque-token-value")
    reset_settings_cache()
    assert "boomi-opaque-token-value" not in redact("boom: boomi-opaque-token-value")
    assert redact("Scan finished: 2 reachable") == "Scan finished: 2 reachable"
    assert redact(ValueError("oops")) == "oops"


def test_log_lines_are_redacted_and_carry_ids(capfd):
    setup_logging()
    log = logging.getLogger("patchpilot.test")
    with log_context(scan_id="scn_42", finding_id="fnd_9"):
        log.warning("push failed for https://user:hunter2hunter2@github.com/a/b token=ghp_%s", "Z" * 30)
    err = capfd.readouterr().err
    assert "scan_id=scn_42" in err and "finding_id=fnd_9" in err
    assert "hunter2hunter2" not in err and "ghp_" + "Z" * 30 not in err


def test_sse_messages_are_redacted():
    bus.publish(ScanEvent(scan_id="scn_1", stage="clone", message="cloning with ghp_" + "Q" * 30))
    assert "ghp_" not in bus.history("scn_1")[0].message


def test_api_error_text_is_redacted(client, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    reset_settings_cache()
    r = client.post("/api/demo/reset", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401
    assert "wrong" not in r.text.replace("Missing or invalid X-API-Key", "")


def test_cors_allows_only_frontend_and_localhost(client):
    for origin in ("http://localhost:5173", "https://patchpilot.example.app"):
        r = client.get("/api/health", headers={"Origin": origin})
        assert r.headers.get("access-control-allow-origin") == origin
    r = client.get("/api/health", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in r.headers


def test_gitignore_covers_secrets():
    lines = (REPO_ROOT / ".gitignore").read_text().splitlines()
    assert ".env*" in lines and "!.env.example" in lines
    assert "!frontend/.env.example" in lines
    assert any(line.rstrip("/") in ("node_modules", "frontend/node_modules") for line in lines)


def test_env_example_lists_every_setting():
    from app.core.config import Settings

    text = (REPO_ROOT / ".env.example").read_text()
    declared = {line.split("=")[0].strip() for line in text.splitlines() if "=" in line and not line.startswith("#")}
    expected = {name.upper() for name in Settings.model_fields} - {"DATABASE_URL"}
    assert expected <= declared, f"missing in .env.example: {sorted(expected - declared)}"
    assert Path(REPO_ROOT / "frontend" / ".env.example").read_text().count("VITE_") >= 2


def test_demo_reset_needs_demo_mode_then_key(client, monkeypatch):
    assert client.post("/api/demo/reset", headers={"X-API-Key": "test-api-key-0123456789abcdef"}).status_code == 404
    monkeypatch.setenv("DEMO_MODE", "true")
    reset_settings_cache()
    assert client.post("/api/demo/reset").status_code == 401
    assert client.post("/api/demo/reset", headers={"X-API-Key": "nope"}).status_code == 401
    r = client.post("/api/demo/reset", headers={"X-API-Key": "test-api-key-0123456789abcdef"})
    assert r.status_code == 200 and r.json() == {"ok": True}
