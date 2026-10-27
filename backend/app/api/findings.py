"""Finding routes (stub: fixtures until T01 reads the DB, T03 triggers the fix)."""
from __future__ import annotations

from fastapi import APIRouter

from app.api import fixtures
from app.core.errors import ApiError
from app.models.schemas import FindingDetail, FindingSummary, FixStarted, Priority, Reachability

router = APIRouter(prefix="/api/findings", tags=["findings"])


@router.get("", response_model=list[FindingSummary])
async def list_findings(
    scan_id: str | None = None,
    priority: Priority | None = None,
    reachability: Reachability | None = None,
) -> list[FindingSummary]:
    return [
        f for f in fixtures.FINDINGS
        if (priority is None or f.priority == priority) and (reachability is None or f.reachability == reachability)
    ]


@router.get("/{finding_id}", response_model=FindingDetail)
async def get_finding(finding_id: str) -> FindingDetail:
    if finding_id != fixtures.FINDING_DETAIL.finding_id:
        raise ApiError(404, "not_found", f"Finding {finding_id} not found")
    return fixtures.FINDING_DETAIL


@router.post("/{finding_id}/fix", status_code=202, response_model=FixStarted)
async def run_fix(finding_id: str) -> FixStarted:
    if not any(f.finding_id == finding_id for f in fixtures.FINDINGS):
        raise ApiError(404, "not_found", f"Finding {finding_id} not found")
    return FixStarted(finding_id=finding_id, status="fixing")
