"""T16 deployment hardening: S2 (no .env in the image), S12 (CORS on the deployed origin), N10 (no sleeping host)."""
from __future__ import annotations

import json

from app.core.config import REPO_ROOT, reset_settings_cache

DOCKERFILE = (REPO_ROOT / "backend" / "Dockerfile").read_text()
DOCKERIGNORE = (REPO_ROOT / ".dockerignore").read_text().splitlines()


def test_dockerfile_has_required_tooling():
    assert "FROM python:3.11-slim" in DOCKERFILE
    assert "git" in DOCKERFILE and "osv-scanner" in DOCKERFILE
    assert "node:20" in DOCKERFILE and "npm" in DOCKERFILE
    assert "ARG OSV_SCANNER_VERSION=" in DOCKERFILE and "sha256sum -c" in DOCKERFILE


def test_dockerfile_runs_non_root_with_healthcheck():
    assert "USER patchpilot" in DOCKERFILE
    assert DOCKERFILE.index("USER patchpilot") < DOCKERFILE.index("CMD [")
    assert "HEALTHCHECK" in DOCKERFILE and "/api/health" in DOCKERFILE


def test_s2_no_env_file_in_image():
    """RISKS S2: the build context excludes .env files and the Dockerfile never copies one."""
    assert ".env" in DOCKERIGNORE and ".env.*" in DOCKERIGNORE
    assert "**/.env" in DOCKERIGNORE
    for line in DOCKERFILE.splitlines():
        if line.strip().upper().startswith(("COPY", "ADD")):
            assert ".env" not in line
    # the only thing copied from the repo is backend/ (no root-wide COPY . .)
    assert "COPY . " not in DOCKERFILE
    assert "backend/patchpilot.db*" in DOCKERIGNORE


def test_db_and_workdir_outside_app_folder():
    assert "DATABASE_URL=sqlite:////data/" in DOCKERFILE
    assert "WORK_DIR=/tmp/patchpilot" in DOCKERFILE


def test_s12_cors_for_deployed_frontend(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://patchpilot.vercel.app/")
    reset_settings_cache()
    from fastapi.testclient import TestClient

    from app.main import create_app

    c = TestClient(create_app())  # no `with`: skip lifespan so logging setup does not leak into other tests
    ok = c.options(
        "/api/scans",
        headers={
            "Origin": "https://patchpilot.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-api-key",
        },
    )
    assert ok.headers.get("access-control-allow-origin") == "https://patchpilot.vercel.app"
    bad = c.options(
        "/api/scans",
        headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in bad.headers


def test_n10_hosts_do_not_sleep():
    railway = json.loads((REPO_ROOT / "railway.json").read_text())
    assert railway["deploy"]["healthcheckPath"] == "/api/health"
    render = (REPO_ROOT / "render.yaml").read_text()
    assert "plan: free" in render or "plan: starter" in render  # free sleeps (warm-up script); starter for the event
    assert "healthCheckPath: /api/health" in render


def test_n10_warmup_scripts_exist():
    assert "/api/health" in (REPO_ROOT / "scripts" / "warmup.ps1").read_text()
    assert "/api/health" in (REPO_ROOT / "scripts" / "warmup.sh").read_text()


def test_vercel_spa_rewrite_and_no_secret_vars():
    v = json.loads((REPO_ROOT / "frontend" / "vercel.json").read_text())
    assert v["rewrites"][0]["destination"] == "/index.html"
    names = [ln.split("=")[0] for ln in (REPO_ROOT / "frontend" / ".env.example").read_text().splitlines() if "=" in ln]
    assert names and all(n.startswith("VITE_") and not any(w in n for w in ("KEY", "TOKEN", "SECRET")) for n in names)
