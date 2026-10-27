"""Integration activity (DB) + compliance proxy (Boomi B4 via boomi_client)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.models import repository as repo
from app.models.schemas import ComplianceReport, IntegrationEvent
from app.services import boomi_client

router = APIRouter(prefix="/api", tags=["integrations"])


@router.get("/integrations/activity", response_model=list[IntegrationEvent])
async def integration_activity(limit: int = Query(default=50, ge=1, le=500)) -> list[IntegrationEvent]:
    return repo.list_integration_events(limit=limit)


@router.get("/compliance", response_model=ComplianceReport, response_model_by_alias=True)
async def compliance(client_name: str | None = None, from_: str | None = Query(default=None, alias="from")) -> ComplianceReport:
    try:
        return await boomi_client.get_compliance(client_name or "Acme Retail", from_)
    except boomi_client.BoomiError as e:  # RISKS N6: Boomi down -> clear 502, nothing else breaks
        raise HTTPException(status_code=502, detail=str(e)) from e
