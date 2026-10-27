"""Integration activity + compliance proxy (stub: fixtures until T01 / T10)."""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.api import fixtures
from app.models.schemas import ComplianceReport, IntegrationEvent

router = APIRouter(prefix="/api", tags=["integrations"])


@router.get("/integrations/activity", response_model=list[IntegrationEvent])
async def integration_activity(limit: int = Query(default=50, ge=1, le=500)) -> list[IntegrationEvent]:
    return fixtures.INTEGRATION_EVENTS[:limit]


@router.get("/compliance", response_model=ComplianceReport, response_model_by_alias=True)
async def compliance(client_name: str | None = None, from_: str | None = Query(default=None, alias="from")) -> ComplianceReport:
    return fixtures.COMPLIANCE
