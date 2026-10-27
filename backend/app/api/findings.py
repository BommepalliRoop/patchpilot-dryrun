"""Finding routes (reads come from the DB; POST .../fix runs the fix in the background)."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

from app import pipeline
from app.core.errors import ApiError
from app.models import repository as repo
from app.models.schemas import FindingDetail, FindingSummary, FixStarted, Priority, Reachability

router = APIRouter(prefix="/api/findings", tags=["findings"])


@router.get("", response_model=list[FindingSummary])
async def list_findings(
    scan_id: str | None = None,
    priority: Priority | None = None,
    reachability: Reachability | None = None,
) -> list[FindingSummary]:
    return repo.list_findings(scan_id=scan_id, priority=priority, reachability=reachability)


@router.get("/{finding_id}", response_model=FindingDetail)
async def get_finding(finding_id: str) -> FindingDetail:
    finding = repo.get_finding(finding_id)
    if finding is None:
        raise ApiError(404, "not_found", f"Finding {finding_id} not found")
    return finding


@router.post("/{finding_id}/fix", status_code=202, response_model=FixStarted)
async def run_fix(finding_id: str, background: BackgroundTasks) -> FixStarted:
    finding = repo.get_finding(finding_id)
    if finding is None:
        raise ApiError(404, "not_found", f"Finding {finding_id} not found")
    if finding.status == "fixing":
        raise ApiError(409, "conflict", f"Finding {finding_id} is already being fixed")
    repo.update_finding(finding_id, status="fixing")
    repo.append_timeline(finding_id, "fix", "Manual fix requested")
    background.add_task(pipeline.run_fix, finding_id)
    return FixStarted(finding_id=finding_id, status="fixing")
