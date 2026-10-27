"""Scan routes: start a scan (dashboard or Boomi B1), list/read scans, live progress over SSE."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header
from sse_starlette.sse import EventSourceResponse

from app import pipeline
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.events import ScanEvent, bus
from app.core.security import require_api_key
from app.models import repository as repo
from app.models.schemas import Scan, ScanCreate, ScanCreated

logger = logging.getLogger("patchpilot.api.scans")

router = APIRouter(prefix="/api/scans", tags=["scans"])

# Characters that could make a URL that starts with an allowed prefix point somewhere else (dot segments,
# backslashes, query/fragment tricks, encoded dots or slashes).
_URL_TRICKS = ("..", "\\", "?", "#", "%2e", "%2f", "%5c", "@")


def repo_allowed(repo_url: str) -> bool:
    """RISKS S1: only repos under ALLOWED_REPO_PREFIXES may be scanned (the engine runs their tests)."""
    lowered = repo_url.lower()
    if any(t in lowered for t in _URL_TRICKS):
        return False
    return any(repo_url.startswith(p) and len(repo_url) > len(p) for p in get_settings().allowed_repo_prefix_list)


def _start(body: ScanCreate, background: BackgroundTasks) -> ScanCreated:
    if not repo_allowed(body.repo_url):
        raise ApiError(400, "repo_not_allowed", "repo_url is not on the allow-list (ALLOWED_REPO_PREFIXES)")
    active = repo.find_active_scan(body.repo_url, body.branch)  # S9 / N9: no second scan for the same repo+branch
    if active is not None:
        return ScanCreated(scan_id=active.scan_id, status=active.status)
    if repo.count_scans_since(pipeline.rate_window_start()) >= get_settings().max_scans_per_hour:
        raise ApiError(429, "rate_limited", "Too many scans in the last hour; try again later")
    # No await between the duplicate check and the insert, so two concurrent POSTs cannot both create a scan.
    scan_id = repo.create_scan(body.client_name, body.repo_url, body.branch, body.auto_fix, body.owner_email)
    background.add_task(pipeline.run_scan, scan_id)
    logger.info("scan %s queued for %s@%s", scan_id, body.repo_url, body.branch)
    return ScanCreated(scan_id=scan_id, status="queued")


@router.post("", status_code=202, response_model=ScanCreated)
async def create_scan(body: ScanCreate, background: BackgroundTasks,
                      x_api_key: str | None = Header(default=None)) -> ScanCreated:
    """Dashboard callers send no key; machine callers (Boomi B1) send `X-API-Key`, which must then be valid."""
    if x_api_key is None:
        return _start(body, background)
    require_api_key(x_api_key)  # 401 on a wrong key; constant-time compare (S10)
    status_code, response = 202, {}
    try:
        created = _start(body, background)
        response = created.model_dump()
        return created
    except ApiError as e:
        status_code, response = e.status_code, {"error": {"code": e.code, "message": e.message}}
        raise
    finally:
        _record_b1(body, status_code, response)


def _record_b1(body: ScanCreate, status_code: int, response: dict[str, Any]) -> None:
    """Integration event so the Integrations page can show B1 health."""
    ok = status_code < 400
    summary = (f"Scan {response.get('scan_id')} {response.get('status')} for {body.client_name}" if ok
               else f"Rejected ({response.get('error', {}).get('code', status_code)}) for {body.client_name}")
    try:
        repo.add_integration_event("B1", "/api/scans", ok, direction="in", request=body.model_dump(),
                                   response=response, status_code=status_code, summary=summary)
    except Exception:  # noqa: BLE001 - logging B1 must never break the B1 call itself
        logger.exception("could not record B1 integration event")


@router.get("", response_model=list[Scan])
async def list_scans() -> list[Scan]:
    return repo.list_scans()


@router.get("/{scan_id}", response_model=Scan)
async def get_scan(scan_id: str) -> Scan:
    scan = repo.get_scan(scan_id)
    if scan is not None:
        return scan
    raise ApiError(404, "not_found", f"Scan {scan_id} not found")


@router.get("/{scan_id}/events")
async def scan_events(scan_id: str) -> EventSourceResponse:
    """Replay (last 200 events, RISKS N8) then live events until `done`.

    A finished scan whose events are no longer in memory (e.g. after a restart) gets one synthetic `done` event
    built from the DB, so the client never waits forever.
    """
    scan = repo.get_scan(scan_id)
    if scan is None and not bus.history(scan_id):
        raise ApiError(404, "not_found", f"Scan {scan_id} not found")

    async def stream() -> AsyncIterator[dict[str, str]]:
        if not bus.history(scan_id) and scan is not None and scan.status in ("completed", "failed"):
            done = ScanEvent(scan_id=scan_id, stage="done", status=scan.status, progress=1.0,
                             message="Scan complete" if scan.status == "completed" else "Scan failed",
                             data={"stats": scan.stats.model_dump()})
            yield {"data": done.model_dump_json()}
            return
        async for event in bus.subscribe(scan_id):
            yield {"data": event.model_dump_json()}

    # RISKS N7: no proxy buffering, heartbeat every 15 s.
    return EventSourceResponse(stream(), ping=15, headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
