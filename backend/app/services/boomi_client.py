"""Stage 8 — Boomi B2/B3/B4 client (T10). A Boomi failure is logged and never fails the scan (RISKS N6)."""
from __future__ import annotations

from typing import Any

from app.models.domain import B2Response, B3Response
from app.models.schemas import ComplianceReport


async def notify_finding(payload: dict[str, Any]) -> B2Response:
    """B2: POST `/patchpilot/findings` (payload shape: contracts/boomi/B2_finding_request.json).

    Sends `Idempotency-Key: <finding_id>` (RISKS N5); 15 s timeout, one retry on 5xx.
    """
    raise NotImplementedError("T10")


async def send_scan_summary(payload: dict[str, Any]) -> B3Response:
    """B3: POST `/patchpilot/scan-summary` (contracts/boomi/B3_scan_summary_request.json), key `<scan_id>`."""
    raise NotImplementedError("T10")


async def get_compliance(client_name: str, from_date: str | None = None) -> ComplianceReport:
    """B4: GET `/patchpilot/compliance?client_name=...&from=...` (contracts/boomi/B4_compliance_response.json)."""
    raise NotImplementedError("T10")
