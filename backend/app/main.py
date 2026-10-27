"""PatchPilot FastAPI app. Run: `cd backend && uvicorn app.main:app --reload --port 8000`."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import pipeline
from app.api import demo, findings, integrations, scans
from app.core.config import get_settings
from app.core.db import init_db
from app.core.errors import install_exception_handlers
from app.core.logging import setup_logging

logger = logging.getLogger("patchpilot")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    init_db()
    pipeline.mark_interrupted_scans()  # RISKS E5
    s = get_settings()
    logger.info("PatchPilot started llm=%s boomi=%s github=%s", s.llm_mode, s.boomi_mode, s.github_mode)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="PatchPilot", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,  # RISKS S12: FRONTEND_URL + localhost:5173 only
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key"],
    )
    install_exception_handlers(app)
    for module in (scans, findings, integrations, demo):
        app.include_router(module.router)
    return app


app = create_app()
