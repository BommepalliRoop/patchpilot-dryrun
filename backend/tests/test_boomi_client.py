"""T10 Boomi client: contract payloads, mock + live paths, N5 Idempotency-Key, N6 failure handling, S4 redaction."""
from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import reset_settings_cache
from app.core.db import init_db
from app.models import repository as repo
from app.services import boomi_client
from app.services.boomi_client import B2Request, B3Request, BoomiError
from tests.seed import contract

B2 = contract("boomi/B2_finding_request.json")
B3 = contract("boomi/B3_scan_summary_request.json")
B4 = contract("boomi/B4_compliance_response.json")
TOKEN = "boomi-secret-token-123456"
_REAL_CLIENT = httpx.AsyncClient


@pytest.fixture(autouse=True)
def _db():
    init_db()


def live(monkeypatch, handler):
    monkeypatch.setenv("BOOMI_MODE", "live")
    monkeypatch.setenv("BOOMI_BASE_URL", "https://boomi.example.com/ws/rest/")
    monkeypatch.setenv("BOOMI_USER", "svc")
    monkeypatch.setenv("BOOMI_TOKEN", TOKEN)
    reset_settings_cache()
    real = _REAL_CLIENT

    def factory(*a, **kw):
        kw["transport"] = httpx.MockTransport(handler)
        return real(*a, **kw)

    monkeypatch.setattr(boomi_client.httpx, "AsyncClient", factory)

    async def no_sleep(_):
        return None

    monkeypatch.setattr(boomi_client, "_sleep", no_sleep)


def events():
    return repo.list_integration_events()


def recorder(response):
    """Handler that records requests and answers with `response` (a Response or a callable on the request)."""
    seen: list[httpx.Request] = []

    def handler(req):
        seen.append(req)
        return response(req) if callable(response) else response

    return seen, handler


# ------------------------------------------------------------- contract shapes

def test_request_models_match_contract_keys():
    assert set(B2Request.model_fields) == set(B2)
    assert set(boomi_client.B2Evidence.model_fields) == set(B2["evidence"][0])
    assert set(B3Request.model_fields) == set(B3)
    assert set(boomi_client.B3Stats.model_fields) == set(B3["stats"])
    assert B2Request.model_validate(B2).model_dump(mode="json") == B2
    assert B3Request.model_validate(B3).model_dump(mode="json") == B3
    assert {"kev", "epss", "epss_percentile", "ecosystem"} <= set(B2Request.model_fields)


@pytest.mark.parametrize("status", ["fixed_untested", "needs_human", "not_attempted"])
def test_fix_status_variants_accepted(status):
    assert B2Request.model_validate({**B2, "fix_status": status}).fix_status == status


async def test_invalid_payload_rejected():
    with pytest.raises(BoomiError, match="contract"):
        await boomi_client.notify_finding({**B2, "surprise": 1})
    with pytest.raises(BoomiError):
        await boomi_client.notify_finding({k: v for k, v in B2.items() if k != "kev"})


def test_sample_ping_payload_is_valid():
    assert B2Request.model_validate(boomi_client.sample_b2_payload())


# ------------------------------------------------------------- mock mode

async def test_mock_b2_returns_stable_sec_key_and_logs():
    r1 = await boomi_client.notify_finding(B2)
    r2 = await boomi_client.notify_finding({**B2, "fix_status": "needs_human", "event": "finding.needs_human"})
    assert r1.ok and r1.jira_key and r1.jira_key.startswith("SEC-1") and len(r1.jira_key) == 7
    assert r1.jira_key == r2.jira_key  # same finding -> same issue (N5)
    assert r1.compliance_log_id == "log_fnd_07" and r1.slack_sent and r1.processed_at
    evs = events()
    assert len(evs) == 2 and all(e.process == "B2" and e.ok and e.finding_id == "fnd_07" for e in evs)


async def test_mock_b3_and_b4():
    r = await boomi_client.send_scan_summary(B3)
    assert r.ok and r.slack_sent
    rep = await boomi_client.get_compliance("Globex", "2026-09-01")
    dumped = rep.model_dump(by_alias=True)
    assert dumped["client_name"] == "Globex" and dumped["from"] == "2026-09-01"
    assert set(dumped["items"][0]) == set(B4["items"][0])
    assert [e.process for e in events()] == ["B4", "B3"]


# ------------------------------------------------------------- live mode

async def test_live_b2_request_shape_auth_and_idempotency(monkeypatch):
    seen, handler = recorder(httpx.Response(200, json={
        "ok": True, "jira_key": "SEC-7", "jira_url": "https://j/SEC-7", "slack_sent": True,
        "compliance_log_id": "log_fnd_07", "processed_at": "2026-10-28T05:11:40Z"}))
    live(monkeypatch, handler)
    r = await boomi_client.notify_finding(B2)
    assert r.jira_key == "SEC-7"
    req = seen[0]
    assert req.method == "POST" and str(req.url) == "https://boomi.example.com/ws/rest/patchpilot/findings"
    assert req.headers["Idempotency-Key"] == "fnd_07"  # N5
    assert req.headers["Authorization"].startswith("Basic ")
    assert json.loads(req.content) == B2
    assert events()[0].status_code == 200 and events()[0].ok


async def test_refix_resends_same_idempotency_key_with_new_status(monkeypatch):
    seen, handler = recorder(httpx.Response(200, json={"ok": True, "jira_key": "SEC-7"}))
    live(monkeypatch, handler)
    await boomi_client.notify_finding({**B2, "event": "finding.needs_human", "fix_status": "needs_human",
                                       "tests_passed": False})
    await boomi_client.notify_finding(B2)
    assert [r.headers["Idempotency-Key"] for r in seen] == ["fnd_07", "fnd_07"]
    assert [json.loads(r.content)["fix_status"] for r in seen] == ["needs_human", "fixed"]


async def test_custom_paths_from_env(monkeypatch):
    monkeypatch.setenv("BOOMI_B3_PATH", "/custom/summary")
    seen, handler = recorder(httpx.Response(200, json={"ok": True, "slack_sent": True}))
    live(monkeypatch, handler)
    await boomi_client.send_scan_summary(B3)
    assert [r.url.path for r in seen] == ["/ws/rest/custom/summary"]
    assert events()[0].endpoint == "/custom/summary"


async def test_b3_idempotency_key_is_scan_id(monkeypatch):
    seen, handler = recorder(httpx.Response(200, json={"ok": True, "slack_sent": True}))
    live(monkeypatch, handler)
    await boomi_client.send_scan_summary(B3)
    assert seen[0].headers["Idempotency-Key"] == "scn_01"


async def test_live_b4_get_with_query(monkeypatch):
    seen, handler = recorder(httpx.Response(200, json=B4))
    live(monkeypatch, handler)
    rep = await boomi_client.get_compliance("Acme Retail", "2026-10-01")
    assert rep.items[0].jira_key == "SEC-101"
    q = seen[0].url.params
    assert seen[0].method == "GET" and q["client_name"] == "Acme Retail" and q["from"] == "2026-10-01"


async def test_retry_once_on_5xx_then_ok(monkeypatch):
    calls: list[str] = []

    def handler(req):
        calls.append(req.headers["Idempotency-Key"])
        if len(calls) == 1:
            return httpx.Response(503, json={"ok": False, "error": "down"})
        return httpx.Response(200, json={"ok": True, "jira_key": "SEC-9"})

    live(monkeypatch, handler)
    r = await boomi_client.notify_finding(B2)
    assert r.ok and calls == ["fnd_07", "fnd_07"]  # retry reuses the key (N5)


async def test_persistent_5xx_returns_error_response_and_logs(monkeypatch):
    seen, handler = recorder(httpx.Response(500, json={"ok": False, "error": "jira_create_failed", "message": "boom"}))
    live(monkeypatch, handler)
    r = await boomi_client.notify_finding(B2)
    assert not r.ok and r.error == "jira_create_failed" and len(seen) == 2  # exactly 1 retry
    e = events()[0]
    assert not e.ok and e.status_code == 500 and "jira_create_failed" in e.summary


async def test_4xx_not_retried(monkeypatch):
    seen, handler = recorder(httpx.Response(400, json={"ok": False, "error": "bad_request"}))
    live(monkeypatch, handler)
    r = await boomi_client.notify_finding(B2)
    assert not r.ok and len(seen) == 1


async def test_timeout_retries_once_then_raises_boomi_error_and_logs(monkeypatch):
    def raise_timeout(req):
        raise httpx.ReadTimeout("slow", request=req)

    seen, handler = recorder(raise_timeout)
    live(monkeypatch, handler)
    with pytest.raises(BoomiError, match="unreachable"):
        await boomi_client.notify_finding(B2)
    assert len(seen) == 2
    e = events()[0]
    assert not e.ok and e.process == "B2" and e.finding_id == "fnd_07"


def test_timeout_is_15s():
    assert boomi_client.TIMEOUT_S == 15.0


async def test_missing_base_url_raises_and_logs(monkeypatch):
    monkeypatch.setenv("BOOMI_MODE", "live")
    monkeypatch.setenv("BOOMI_BASE_URL", "")
    reset_settings_cache()
    with pytest.raises(BoomiError, match="BOOMI_BASE_URL"):
        await boomi_client.send_scan_summary(B3)
    assert not events()[0].ok


async def test_b4_error_raises(monkeypatch):
    live(monkeypatch, lambda req: httpx.Response(502, text="bad gateway"))
    with pytest.raises(BoomiError):
        await boomi_client.get_compliance("Acme Retail")


async def test_garbage_b2_body_raises(monkeypatch):
    live(monkeypatch, lambda req: httpx.Response(200, text="<html>"))
    with pytest.raises(BoomiError, match="unexpected"):
        await boomi_client.notify_finding(B2)


# ------------------------------------------------------------- S4: token never leaks

async def test_token_never_in_events_or_errors(monkeypatch):
    live(monkeypatch, lambda req: httpx.Response(
        500, json={"ok": False, "error": f"auth failed for {TOKEN}", "message": f"Bearer {TOKEN}"}))
    r = await boomi_client.notify_finding(B2)
    assert TOKEN not in repr(r.model_dump()) + repr([e.model_dump() for e in events()])

    def boom(req):
        raise httpx.ConnectError(f"cannot connect https://svc:{TOKEN}@boomi.example.com", request=req)

    live(monkeypatch, boom)
    with pytest.raises(BoomiError) as ei:
        await boomi_client.notify_finding(B2)
    assert TOKEN not in str(ei.value)
    assert TOKEN not in repr([e.model_dump() for e in events()])


# ------------------------------------------------------------- API route + CLI

def test_compliance_route_uses_client(client):
    body = client.get("/api/compliance", params={"client_name": "Globex", "from": "2026-10-02"}).json()
    assert body["client_name"] == "Globex" and body["from"] == "2026-10-02"


def test_compliance_route_502_when_boomi_down(client, monkeypatch):
    live(monkeypatch, lambda req: httpx.Response(503))
    assert client.get("/api/compliance", params={"client_name": "Acme Retail"}).status_code == 502


def test_cli_ping_mock(capsys):
    assert boomi_client.main(["ping"]) == 0
    out = capsys.readouterr().out
    assert "SEC-1" in out and "BOOMI_MODE=mock" in out
    assert boomi_client.main([]) == 2
