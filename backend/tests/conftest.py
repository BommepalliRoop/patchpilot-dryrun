from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import reset_settings_cache
from app.core.db import init_db, reset_engine
from app.core.events import bus

# Pinned so a developer's real .env can never change test behaviour.
TEST_ENV = {
    "LLM_MODE": "mock",
    "BOOMI_MODE": "mock",
    "GITHUB_MODE": "mock",
    "THREAT_INTEL": "mock",
    "DEMO_MODE": "false",
    "PATCHPILOT_API_KEY": "test-api-key-0123456789abcdef",
    "FRONTEND_URL": "https://patchpilot.example.app",
    "LLM_API_KEY": "",
    "GITHUB_TOKEN": "",
    "BOOMI_TOKEN": "",
}


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    for key, value in TEST_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("WORK_DIR", str(tmp_path / "work"))
    reset_settings_cache()
    reset_engine()
    bus.clear()
    yield
    reset_engine()
    reset_settings_cache()
    bus.clear()


@pytest.fixture
def app():
    from app.main import create_app

    return create_app()


@pytest.fixture
def client(app):
    init_db()  # TestClient used without `with` skips the lifespan
    # raise_server_exceptions=False: we test the 500 envelope that real clients see.
    return TestClient(app, raise_server_exceptions=False)
