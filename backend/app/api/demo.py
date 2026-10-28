"""Health and demo reset."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.security import require_api_key
from app.models.schemas import Health, Ok
from app.services import demo_reset as demo_reset_service

router = APIRouter(prefix="/api", tags=["demo"])


@router.get("/health", response_model=Health)
async def health() -> Health:
    s = get_settings()
    return Health(llm_mode=s.llm_mode, boomi_mode=s.boomi_mode, github_mode=s.github_mode)


def _demo_only(x_api_key: str | None = Header(default=None)) -> None:
    """RISKS S8: 404 unless DEMO_MODE=true, then the API key is required."""
    if not get_settings().demo_mode:
        raise ApiError(404, "not_found", "Not found")
    require_api_key(x_api_key)


@router.post("/demo/reset", response_model=Ok, dependencies=[Depends(_demo_only)])
async def demo_reset() -> Ok:
    """DB, SSE buffers, WORK_DIR and (GITHUB_MODE=live) the `patchpilot/*` PR branches (RISKS O3)."""
    await demo_reset_service.reset()
    return Ok()
