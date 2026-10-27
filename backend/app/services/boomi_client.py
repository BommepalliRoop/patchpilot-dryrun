"""Stage 8 — Boomi B2/B3/B4 client (T10). A Boomi failure is logged and never fails the scan (RISKS N6).

`BOOMI_MODE=mock` returns contract example responses; `live` calls `BOOMI_BASE_URL` with Basic auth.
Every call (ok or not) is written to `integration_events`. Failures raise `BoomiError`; the pipeline
catches it and carries on.

CLI for the Boomi team: `python -m app.services.boomi_client ping` sends the sample B2 request.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import zlib
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.config import get_settings
from app.core.ids import iso_z
from app.core.security import redact
from app.models import repository as repo
from app.models.domain import B2Response, B3Response
from app.models.schemas import ComplianceReport, Priority, Reachability

logger = logging.getLogger(__name__)

TIMEOUT_S = 15.0
RETRY_DELAY_S = 1.0


class BoomiError(RuntimeError):
    """Boomi unreachable, slow or answered with an error. Message is already redacted (RISKS S4)."""


# ---------------------------------------------------------------- request models (== contracts/boomi/*.json)

class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class B2Evidence(_Strict):
    file: str
    line: int
    in_route: bool


class B2Request(_Strict):
    """contracts/boomi/B2_finding_request.json"""

    event: Literal["finding.fixed", "finding.needs_human", "finding.open"]
    scan_id: str
    finding_id: str
    client_name: str
    repo_url: str
    cve_id: str
    package: str
    ecosystem: str
    installed_version: str
    fixed_version: str | None = None
    cvss: float
    priority: Priority
    score: float
    kev: bool
    epss: float | None = None
    epss_percentile: float | None = None
    reachability: Reachability
    confidence: float
    summary: str = ""
    ai_explanation: str = ""
    evidence: list[B2Evidence]
    fix_status: Literal["fixed", "fixed_untested", "needs_human", "not_attempted"]
    tests_passed: bool
    pr_url: str | None = None
    owner_email: str = ""
    detected_at: str


class B3Stats(_Strict):
    total_alerts: int
    reachable: int
    unsure: int
    not_reachable: int
    p1: int
    p2: int
    fixed: int
    prs_opened: int


class B3Request(_Strict):
    """contracts/boomi/B3_scan_summary_request.json"""

    event: Literal["scan.completed"] = "scan.completed"
    scan_id: str
    client_name: str
    repo_url: str
    finished_at: str
    stats: B3Stats
    dashboard_url: str


# ---------------------------------------------------------------- mock mode

def _mock_jira_key(finding_id: str) -> str:
    """SEC-1xx, stable per finding so a repeated Idempotency-Key returns the same issue (N5)."""
    return f"SEC-{100 + zlib.crc32(finding_id.encode()) % 100}"


def _mock_b2(req: B2Request) -> B2Response:
    key = _mock_jira_key(req.finding_id)
    return B2Response(ok=True, jira_key=key, jira_url=f"https://example.atlassian.net/browse/{key}", slack_sent=True,
                      compliance_log_id=f"log_{req.finding_id}", processed_at=iso_z())


def _mock_compliance(client_name: str, from_date: str | None) -> ComplianceReport:
    """contracts/boomi/B4_compliance_response.json"""
    return ComplianceReport.model_validate({
        "client_name": client_name, "from": from_date or "2026-10-01",
        "items": [{
            "compliance_log_id": "log_fnd_07", "cve_id": "CVE-2020-14343", "package": "pyyaml", "priority": "P1",
            "detected_at": "2026-10-28T05:10:05Z", "fixed_at": "2026-10-28T05:11:40Z", "time_to_fix_minutes": 2,
            "jira_key": "SEC-101", "pr_url": "https://github.com/<org>/demo-target/pull/3", "status": "fixed",
        }],
    })


# ---------------------------------------------------------------- live transport

async def _sleep(seconds: float) -> None:  # separate so tests skip the wait
    await asyncio.sleep(seconds)


def _live_target(path: str) -> tuple[str, httpx.BasicAuth | None]:
    s = get_settings()
    if not s.boomi_base_url:
        raise BoomiError("BOOMI_BASE_URL is not set (BOOMI_MODE=live)")
    auth = httpx.BasicAuth(s.boomi_user, s.boomi_token) if s.boomi_user or s.boomi_token else None
    return s.boomi_base_url.rstrip("/") + path, auth


async def _send(method: str, url: str, auth: httpx.BasicAuth | None, *, json_body: Any = None,
                params: dict[str, str] | None = None, idempotency_key: str | None = None) -> httpx.Response:
    """15 s timeout; one retry on 5xx, timeout or connection error. Retries reuse the same Idempotency-Key (N5)."""
    headers = {"Accept": "application/json"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    last: str = ""
    for attempt in (1, 2):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S) as http:
                resp = await http.request(method, url, auth=auth, headers=headers, json=json_body, params=params)
            if resp.status_code < 500:
                return resp
            last = f"HTTP {resp.status_code}"
            if attempt == 2:
                return resp
        except httpx.HTTPError as e:
            last = f"{type(e).__name__}: {e}"
            if attempt == 2:
                raise BoomiError(redact(f"Boomi unreachable ({last})")) from e
        logger.warning("Boomi %s %s failed (%s), retrying once", method, url.split("?")[0], redact(last))
        await _sleep(RETRY_DELAY_S)
    raise BoomiError(redact(f"Boomi call failed ({last})"))  # pragma: no cover - loop always returns/raises


def _json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return None


def _log(process: str, path: str, ok: bool, *, finding_id: str | None = None, request: Any = None,
         response: Any = None, status_code: int | None = None, summary: str) -> None:
    try:
        repo.add_integration_event(process, path, ok, finding_id=finding_id, request=request, response=response,
                                   status_code=status_code, summary=summary)
    except Exception:  # noqa: BLE001 - logging must never break a call (N6)
        logger.exception("could not record %s integration event", process)


def _validate(model: type[BaseModel], payload: dict[str, Any], what: str) -> Any:
    try:
        return model.model_validate(payload)
    except ValidationError as e:
        raise BoomiError(f"{what} payload does not match the contract: {e.error_count()} error(s)") from e


# ---------------------------------------------------------------- public API

async def notify_finding(payload: dict[str, Any]) -> B2Response:
    """B2: POST `/patchpilot/findings` (payload shape: contracts/boomi/B2_finding_request.json).

    Sends `Idempotency-Key: <finding_id>` (RISKS N5); 15 s timeout, one retry on 5xx. Sending the same
    finding again with a new `fix_status` (manual re-fix) is a status update on Boomi's side.
    """
    s = get_settings()
    req: B2Request = _validate(B2Request, payload, "B2")
    body = req.model_dump(mode="json")
    path = s.boomi_b2_path
    if s.boomi_mode != "live":
        resp = _mock_b2(req)
        _log("B2", path, True, finding_id=req.finding_id, request=body, response=resp.model_dump(),
             status_code=200, summary=f"[mock] Jira {resp.jira_key} created, Slack sent")
        return resp
    try:
        url, auth = _live_target(path)
        http_resp = await _send("POST", url, auth, json_body=body, idempotency_key=req.finding_id)
    except BoomiError as e:
        _log("B2", path, False, finding_id=req.finding_id, request=body, summary=f"B2 failed: {e}")
        raise
    data = _json(http_resp)
    if http_resp.status_code >= 400:
        err = data if isinstance(data, dict) else {}
        reason = redact(err.get("error") or f"HTTP {http_resp.status_code}")
        _log("B2", path, False, finding_id=req.finding_id, request=body, response=err or None,
             status_code=http_resp.status_code, summary=f"B2 failed: {reason}")
        return B2Response(ok=False, error=str(reason), message=redact(err.get("message") or "") or None)
    try:
        resp = B2Response.model_validate(data)
    except ValidationError:
        _log("B2", path, False, finding_id=req.finding_id, request=body, status_code=http_resp.status_code,
             summary="B2 failed: unexpected response body")
        raise BoomiError("Boomi B2 returned an unexpected response body") from None
    _log("B2", path, resp.ok, finding_id=req.finding_id, request=body, response=data,
         status_code=http_resp.status_code,
         summary=f"Jira {resp.jira_key} {'created' if resp.ok else 'failed'}" + (", Slack sent" if resp.slack_sent else ""))
    return resp


async def send_scan_summary(payload: dict[str, Any]) -> B3Response:
    """B3: POST `/patchpilot/scan-summary` (contracts/boomi/B3_scan_summary_request.json), key `<scan_id>`."""
    s = get_settings()
    req: B3Request = _validate(B3Request, payload, "B3")
    body = req.model_dump(mode="json")
    path = s.boomi_b3_path
    if s.boomi_mode != "live":
        resp = B3Response(ok=True, slack_sent=True)
        _log("B3", path, True, request=body, response=resp.model_dump(), status_code=200,
             summary="[mock] Scan summary posted to Slack")
        return resp
    try:
        url, auth = _live_target(path)
        http_resp = await _send("POST", url, auth, json_body=body, idempotency_key=req.scan_id)
    except BoomiError as e:
        _log("B3", path, False, request=body, summary=f"B3 failed: {e}")
        raise
    data = _json(http_resp)
    if http_resp.status_code >= 400 or not isinstance(data, dict):
        err = data if isinstance(data, dict) else {}
        reason = redact(err.get("error") or f"HTTP {http_resp.status_code}")
        _log("B3", path, False, request=body, response=err or None, status_code=http_resp.status_code,
             summary=f"B3 failed: {reason}")
        return B3Response(ok=False)
    resp = B3Response.model_validate(data)
    _log("B3", path, resp.ok, request=body, response=data, status_code=http_resp.status_code,
         summary="Scan summary posted to Slack" if resp.slack_sent else "Scan summary sent")
    return resp


async def get_compliance(client_name: str, from_date: str | None = None) -> ComplianceReport:
    """B4: GET `/patchpilot/compliance?client_name=...&from=...` (contracts/boomi/B4_compliance_response.json)."""
    s = get_settings()
    path = s.boomi_b4_path
    params = {"client_name": client_name, **({"from": from_date} if from_date else {})}
    if s.boomi_mode != "live":
        report = _mock_compliance(client_name, from_date)
        _log("B4", path, True, request=params, response=report.model_dump(by_alias=True), status_code=200,
             summary=f"[mock] {len(report.items)} compliance item(s)")
        return report
    try:
        url, auth = _live_target(path)
        http_resp = await _send("GET", url, auth, params=params)
    except BoomiError as e:
        _log("B4", path, False, request=params, summary=f"B4 failed: {e}")
        raise
    data = _json(http_resp)
    if http_resp.status_code >= 400:
        reason = redact(data.get("error") if isinstance(data, dict) and data.get("error") else f"HTTP {http_resp.status_code}")
        _log("B4", path, False, request=params, response=data if isinstance(data, dict) else None,
             status_code=http_resp.status_code, summary=f"B4 failed: {reason}")
        raise BoomiError(f"Boomi B4 failed: {reason}")
    try:
        report = ComplianceReport.model_validate(data)
    except ValidationError:
        _log("B4", path, False, request=params, status_code=http_resp.status_code,
             summary="B4 failed: unexpected response body")
        raise BoomiError("Boomi B4 returned an unexpected response body") from None
    _log("B4", path, True, request=params, response=data, status_code=http_resp.status_code,
         summary=f"{len(report.items)} compliance item(s)")
    return report


# ---------------------------------------------------------------- CLI

def sample_b2_payload() -> dict[str, Any]:
    """The example in contracts/boomi/B2_finding_request.json, with a fresh key so each ping makes its own issue."""
    return {
        "event": "finding.fixed", "scan_id": "scn_ping", "finding_id": f"fnd_ping_{iso_z()[-9:-1].replace(':', '')}",
        "client_name": "Acme Retail", "repo_url": "https://github.com/<org>/demo-target", "cve_id": "CVE-2020-14343",
        "package": "pyyaml", "ecosystem": "PyPI", "installed_version": "5.3.1", "fixed_version": "5.4.1",
        "cvss": 9.8, "priority": "P1", "score": 10.0, "kev": False, "epss": 0.0598, "epss_percentile": 0.9326,
        "reachability": "reachable", "confidence": 0.93,
        "summary": "Arbitrary code execution via full_load / FullLoader",
        "ai_explanation": "User-supplied YAML from POST /import reaches yaml.load without SafeLoader.",
        "evidence": [{"file": "app/routes.py", "line": 42, "in_route": True}],
        "fix_status": "fixed", "tests_passed": True, "pr_url": "https://github.com/<org>/demo-target/pull/3",
        "owner_email": "owner@easystepin.com", "detected_at": "2026-10-28T05:10:05Z",
    }


async def _ping() -> int:
    s = get_settings()
    print(f"BOOMI_MODE={s.boomi_mode} base={s.boomi_base_url or '(unset)'} path={s.boomi_b2_path}")
    if s.boomi_mode != "live":
        print("Set BOOMI_MODE=live (and BOOMI_BASE_URL/BOOMI_USER/BOOMI_TOKEN) to reach the real Boomi endpoint.")
    try:
        resp = await notify_finding(sample_b2_payload())
    except BoomiError as e:
        print(f"FAILED: {e}")
        return 1
    print(json.dumps(resp.model_dump(), indent=2))
    return 0 if resp.ok else 1


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args != ["ping"]:
        print("usage: python -m app.services.boomi_client ping")
        return 2
    from app.core.db import init_db

    init_db()  # the call is logged to integration_events
    return asyncio.run(_ping())


if __name__ == "__main__":
    raise SystemExit(main())
