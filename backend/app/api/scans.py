"""Scan routes (reads come from the DB; T03 replaces the POST stub and the SSE fixture playback)."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.api import fixtures
from app.core.errors import ApiError
from app.core.events import bus
from app.models import repository as repo
from app.models.schemas import Scan, ScanCreate, ScanCreated

router = APIRouter(prefix="/api/scans", tags=["scans"])


@router.post("", status_code=202, response_model=ScanCreated)
async def create_scan(body: ScanCreate) -> ScanCreated:
    return ScanCreated(scan_id=fixtures.SCAN_ID, status="queued")


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
    if not bus.history(scan_id) and scan_id != fixtures.SCAN_ID:
        raise ApiError(404, "not_found", f"Scan {scan_id} not found")

    async def stream() -> AsyncIterator[dict[str, str]]:
        if bus.history(scan_id):
            async for event in bus.subscribe(scan_id):
                yield {"data": event.model_dump_json()}
            return
        for event in fixtures.canned_events(scan_id):  # fixture playback for the stub scan
            yield {"data": event.model_dump_json()}
            await asyncio.sleep(0.2)

    # RISKS N7: no proxy buffering, heartbeat every 15 s.
    return EventSourceResponse(stream(), ping=15, headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
