"""Application settings, read from environment variables and the repo-root `.env` (docs/CONFIG.md)."""
from __future__ import annotations

import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = Path(__file__).resolve().parents[2]  # backend/ locally, /srv/app in Docker (no backend/ dir there)

Mode = Literal["mock", "live"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # LLM (T04)
    llm_provider: Literal["anthropic", "openai"] = "anthropic"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str = ""
    llm_mode: Mode = "mock"

    # Boomi (T10)
    boomi_mode: Mode = "mock"
    boomi_base_url: str = ""
    boomi_user: str = ""
    boomi_token: str = ""
    boomi_b2_path: str = "/patchpilot/findings"
    boomi_b3_path: str = "/patchpilot/scan-summary"
    boomi_b4_path: str = "/patchpilot/compliance"

    # Git hosts (T09)
    github_mode: Mode = "mock"
    github_token: str = ""
    gitlab_token: str = ""

    # Scanning
    demo_repo_url: str = ""
    # comma-separated; kept as a string so pydantic-settings does not try to JSON-decode it
    allowed_repo_prefixes: str = "https://github.com/BommepalliRoop/"
    work_dir: str = ""
    threat_intel: Literal["live", "mock", "off"] = "live"
    scan_timeout_s: int = 600
    max_scans_per_hour: int = 20
    fix_python: str = ""  # interpreter for fix venvs (T08); blank = the backend's own Python
    fix_concurrency: int = Field(default=4, ge=1)  # package fixes in parallel; 1 on 512 MB hosts (each builds a venv)

    # Service
    demo_mode: bool = False
    patchpilot_api_key: str = ""
    backend_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"
    database_url: str = Field(default="", description="Override; default is backend/patchpilot.db")

    @property
    def allowed_repo_prefix_list(self) -> list[str]:
        return [p.strip() for p in self.allowed_repo_prefixes.split(",") if p.strip()]

    @property
    def work_path(self) -> Path:
        """Root for clones, venvs and caches. Never hardcode /tmp (devs are on Windows)."""
        return Path(self.work_dir) if self.work_dir else Path(tempfile.gettempdir()) / "patchpilot"

    @property
    def sqlite_url(self) -> str:
        return self.database_url or f"sqlite:///{(BACKEND_DIR / 'patchpilot.db').as_posix()}"

    @property
    def cors_origins(self) -> list[str]:
        """S12: only the deployed frontend and the local Vite dev server."""
        origins = {"http://localhost:5173"}
        if self.frontend_url:
            origins.add(self.frontend_url.rstrip("/"))
        return sorted(origins)

    @property
    def secret_values(self) -> list[str]:
        """Configured secrets; redact() masks these literally in every log line and error text."""
        return [v for v in (self.llm_api_key, self.github_token, self.gitlab_token,
                            self.boomi_token, self.patchpilot_api_key) if v]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Tests change env vars and call this."""
    get_settings.cache_clear()
