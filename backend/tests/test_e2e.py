"""T17 end to end: the mock fallback works with the network off (RISKS O1), plus the integration bugs found in the
first full demo-target run.

The whole API runs in-process (httpx ASGITransport) and every non-loopback socket connect fails, so any hidden
network call (LLM, GitHub, Boomi, CISA, FIRST) breaks the test. Clone and OSV need the network by nature, so
they are replaced by a local fixture repo and the real demo-target advisories from the seed data; symbols,
reachability (real AST), risk, PR (mock), Boomi (mock) and the e2e checker run for real.
"""
from __future__ import annotations

import socket
from pathlib import Path

import httpx
import pytest

from app import e2e, seed
from app.core import subproc
from app.core.config import reset_settings_cache
from app.core.db import init_db
from app.models import repository as repo
from app.models.domain import FixResult, RawVuln
from app.services import cloner, fixer, scanner
from app.services.fixer import _pinning_manifest, _PyPI

DEMO = "https://github.com/BommepalliRoop/demo-target"

APP_PY = '''from flask import Flask, request
import yaml

app = Flask(__name__)


@app.route("/import", methods=["POST"])
def import_data():
    return yaml.load(request.data)
'''
JOBS_PY = '''import requests


def fetch_status(url):
    return requests.get(url, timeout=10).status_code
'''


@pytest.fixture
def network_off(monkeypatch):
    """Fail every connect that is not loopback / a unix socket; record the attempts."""
    attempts: list[object] = []
    real_connect = socket.socket.connect

    def guarded(self, address):  # noqa: ANN001, ANN202
        host = address[0] if isinstance(address, tuple) else None
        if host is not None and host not in ("127.0.0.1", "::1", "localhost"):
            attempts.append(address)
            raise OSError("network is off (test)")
        return real_connect(self, address)

    def no_dns(host, *args, **kwargs):  # noqa: ANN001, ANN202
        if host not in ("127.0.0.1", "::1", "localhost", None):
            attempts.append(host)
            raise socket.gaierror("network is off (test)")
        return real_getaddrinfo(host, *args, **kwargs)

    real_getaddrinfo = socket.getaddrinfo
    monkeypatch.setattr(socket.socket, "connect", guarded)
    monkeypatch.setattr(socket, "getaddrinfo", no_dns)
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(var, raising=False)  # a loopback proxy would tunnel past the guard
    with pytest.raises((OSError, httpx.HTTPError)):  # the guard itself works
        httpx.get("https://api.osv.dev/v1/query", timeout=2)
    assert attempts
    attempts.clear()
    return attempts


@pytest.fixture
def offline_stages(monkeypatch):
    """Local stand-ins for the two stages that need the internet by nature (git clone, OSV)."""
    fixed_packages: list[str] = []

    async def clone(repo_url: str, branch: str, scan_id: str) -> Path:
        dest = cloner.scan_dir(scan_id) / "repo"
        (dest / "demo_app").mkdir(parents=True)
        (dest / "requirements.txt").write_text("Flask==1.1.2\nPyYAML==5.3.1\nrequests==2.25.1\n", encoding="utf-8")
        (dest / "demo_app" / "routes.py").write_text(APP_PY, encoding="utf-8")
        (dest / "demo_app" / "jobs.py").write_text(JOBS_PY, encoding="utf-8")
        return dest

    async def scan(path: Path) -> list[RawVuln]:
        return [RawVuln(**{k: v for k, v in a.items() if k != "fixed_version"},
                        fixed_versions=[a["fixed_version"]] if a["fixed_version"] else [],
                        manifest="requirements.txt")
                for a in seed.advisories() if a["ecosystem"] == "PyPI"]

    async def fix_package(scan_id: str, repo_path: Path, package: str, vulns: list[RawVuln]) -> FixResult:
        fixed_packages.append(package)
        return FixResult(package=package, new_version="9.9.9", patch_diff="-x\n+y\n", tests_passed=True, attempts=0,
                         branch=f"patchpilot/{package}-9.9.9", status="fixed")

    monkeypatch.setattr(cloner, "clone", clone)
    monkeypatch.setattr(scanner, "scan", scan)
    monkeypatch.setattr(fixer, "fix_package", fix_package)
    return fixed_packages


async def test_mock_fallback_runs_end_to_end_with_network_off(app, network_off, offline_stages):
    init_db()
    seed.seed()  # the dashboard is not empty before the demo scan
    transport = httpx.ASGITransport(app=app)
    lines: list[str] = []
    res = await e2e.run_e2e("http://testserver", repo_url=DEMO, transport=transport, budget=120, log=lines.append)

    assert res.passed(120), res.problems
    assert res.modes == {"llm_mode": "mock", "github_mode": "mock", "boomi_mode": "mock"}
    assert res.status == "completed" and res.jira_key and res.pr_url and res.pr_url.startswith(DEMO + "/pull/")
    assert list(res.stage_times) == ["clone", "scan", "symbols", "reachability", "risk", "fix", "pr", "notify", "done"]
    assert res.stats["p1"] >= 1 and "pyyaml" in offline_stages
    assert network_off == []  # no hidden call to an LLM, GitHub, Boomi or a threat feed
    assert len(repo.list_scans()) == 3


async def test_expect_live_fails_while_any_mode_is_mock(app, network_off, offline_stages):
    init_db()
    res = await e2e.run_e2e("http://testserver", repo_url=DEMO, transport=httpx.ASGITransport(app=app),
                            expect_live=True, log=lambda _: None)
    assert not res.passed(120)
    assert sorted(res.problems) == ["boomi_mode=mock (expected live)", "github_mode=mock (expected live)",
                                    "llm_mode=mock (expected live)"]


async def test_checker_fails_when_the_budget_is_blown_or_the_scan_is_refused(app, network_off, offline_stages):
    init_db()
    transport = httpx.ASGITransport(app=app)
    res = await e2e.run_e2e("http://testserver", repo_url=DEMO, transport=transport, budget=0, log=lambda _: None)
    assert res.ticket_s is not None and not res.passed(0)
    assert any("budget 0s" in p for p in res.problems)

    res = await e2e.run_e2e("http://testserver", repo_url="https://evil.example/x", transport=transport,
                            log=lambda _: None)
    assert res.problems and "400" in res.problems[0] and not res.passed(120)


# ------------------------------------------------- integration bugs found in the first full demo-target run

def test_fixer_follows_dash_r_to_the_file_that_pins_the_package(tmp_path):
    """osv-scanner may report PyYAML from requirements-dev.txt (`-r requirements.txt`): bump requirements.txt."""
    (tmp_path / "requirements.txt").write_text("Flask==1.1.2\nPyYAML==5.3.1\n", encoding="utf-8")
    (tmp_path / "requirements-dev.txt").write_text("-r requirements.txt\npytest==7.4.4\n", encoding="utf-8")
    vuln = RawVuln(cve_id="CVE-2020-14343", ecosystem="PyPI", package="pyyaml", installed_version="5.3.1",
                   manifest="requirements-dev.txt")
    assert _PyPI("PyPI").locate(tmp_path, [vuln]) == "requirements.txt"
    assert _pinning_manifest(tmp_path, "requirements-dev.txt", "pytest") == "requirements-dev.txt"


def test_pinning_manifest_nested_includes_cycles_and_repo_escape(tmp_path):
    (tmp_path / "reqs").mkdir()
    (tmp_path / "reqs" / "base.txt").write_text("requests==2.25.1\n-r ../requirements-dev.txt\n", encoding="utf-8")
    (tmp_path / "requirements-dev.txt").write_text("--requirement=reqs/base.txt\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("-r ../../outside.txt\n", encoding="utf-8")
    (tmp_path.parent / "outside.txt").write_text("pyyaml==5.3.1\n", encoding="utf-8")
    assert _pinning_manifest(tmp_path, "requirements-dev.txt", "requests") == "reqs/base.txt"
    assert _pinning_manifest(tmp_path, "requirements-dev.txt", "flask") == "requirements-dev.txt"  # cycle ends
    assert _pinning_manifest(tmp_path, "requirements.txt", "pyyaml") == "requirements.txt"  # never leaves the repo


def test_clean_env_keeps_proxy_and_ca_settings_but_still_no_secrets(monkeypatch):
    """Venue / corporate networks: npm failed with SELF_SIGNED_CERT_IN_CHAIN because the CA bundle was dropped."""
    keep = {"HTTPS_PROXY": "http://proxy:3128", "https_proxy": "http://proxy:3128", "NO_PROXY": "localhost",
            "NODE_EXTRA_CA_CERTS": "/ca.pem", "REQUESTS_CA_BUNDLE": "/ca.pem", "GIT_SSL_CAINFO": "/ca.pem"}
    drop = {"LLM_API_KEY": "sk-secret-123456", "GITHUB_TOKEN": "ghp_" + "a" * 36, "BOOMI_TOKEN": "t0k3n",
            "PATCHPILOT_API_KEY": "k" * 32, "AWS_SECRET_ACCESS_KEY": "x"}
    for k, v in {**keep, **drop}.items():
        monkeypatch.setenv(k, v)
    reset_settings_cache()
    env = subproc.clean_env()
    assert {k: env.get(k) for k in keep} == keep
    assert not set(drop) & set(env)
