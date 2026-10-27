"""E8 SQLite settings, event bus replay (N8), config helpers, service stub signatures."""
from __future__ import annotations

import asyncio
import importlib
import inspect

import pytest
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.core.db import get_engine, init_db
from app.core.events import REPLAY_SIZE, ScanEvent, bus


def test_sqlite_wal_and_busy_timeout():
    init_db()
    with get_engine().connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA busy_timeout")).scalar() == 5000


def test_work_dir_defaults_to_system_temp(monkeypatch):
    monkeypatch.delenv("WORK_DIR")
    import tempfile
    from pathlib import Path

    assert Settings(_env_file=None).work_path == Path(tempfile.gettempdir()) / "patchpilot"


def test_allowed_prefixes_split(monkeypatch):
    monkeypatch.setenv("ALLOWED_REPO_PREFIXES", "https://github.com/a/, https://gitlab.com/b/")
    assert Settings(_env_file=None).allowed_repo_prefix_list == ["https://github.com/a/", "https://gitlab.com/b/"]


def test_cors_origins_from_settings():
    assert get_settings().cors_origins == ["http://localhost:5173", "https://patchpilot.example.app"]


def _ev(stage: str, i: int = 0) -> ScanEvent:
    return ScanEvent(scan_id="scn_1", stage=stage, message=f"m{i}", progress=0.1)  # type: ignore[arg-type]


async def test_late_subscriber_gets_replay_then_live_until_done():
    bus.publish(_ev("clone"))
    got: list[ScanEvent] = []

    async def reader() -> None:
        async for e in bus.subscribe("scn_1"):
            got.append(e)

    task = asyncio.create_task(reader())
    await asyncio.sleep(0.05)
    bus.publish(_ev("scan"))
    bus.publish(_ev("done"))
    await asyncio.wait_for(task, 2)
    assert [e.stage for e in got] == ["clone", "scan", "done"]


async def test_subscribe_after_done_replays_and_ends():
    bus.publish(_ev("scan"))
    bus.publish(_ev("done"))
    got = [e.stage async for e in bus.subscribe("scn_1")]
    assert got == ["scan", "done"]


def test_replay_buffer_keeps_last_200():
    for i in range(REPLAY_SIZE + 50):
        bus.publish(_ev("scan", i))
    history = bus.history("scn_1")
    assert len(history) == REPLAY_SIZE and history[0].message == "m50"


def test_event_json_shape_matches_contract():
    assert set(_ev("scan").model_dump()) == {"scan_id", "stage", "status", "message", "progress", "data"}


SIGNATURES = {
    "app.services.cloner": [("clone", ["repo_url", "branch", "scan_id"]), ("cleanup", ["scan_id"])],
    "app.services.ecosystems": [("detect", ["repo_path"])],
    "app.services.scanner": [("scan", ["path"])],
    "app.services.threat_intel": [("enrich", ["vulns"])],
    "app.services.symbols": [("extract", ["vuln"])],
    "app.services.reachability": [("analyze", ["repo_path", "vuln", "symbols"])],
    "app.services.risk": [("score", ["cvss", "reachability", "evidence", "kev", "epss_percentile"])],
    "app.services.fixer": [("fix_package", ["scan_id", "repo_path", "package", "vulns"])],
    "app.services.github_pr": [("open_pr", ["repo_url", "branch", "fix", "findings"])],
    "app.services.boomi_client": [("notify_finding", ["payload"]), ("send_scan_summary", ["payload"]),
                                  ("get_compliance", ["client_name", "from_date"])],
    "app.services.llm": [("complete_json", ["prompt_name", "variables", "schema"])],
    "app.pipeline": [("run_scan", ["scan_id"])],
}


# Modules whose task has landed: signatures stay frozen, but they no longer raise NotImplementedError.
IMPLEMENTED = {"app.services.cloner", "app.services.ecosystems", "app.services.scanner", "app.services.threat_intel",
               "app.services.llm", "app.services.symbols", "app.services.reachability",
               "app.services.risk", "app.services.boomi_client", "app.services.fixer", "app.services.github_pr",
               "app.pipeline"}


@pytest.mark.parametrize("module_name", SIGNATURES)
async def test_service_stubs_have_signatures_and_raise_not_implemented(module_name):
    module = importlib.import_module(module_name)
    for func_name, params in SIGNATURES[module_name]:
        func = getattr(module, func_name)
        assert list(inspect.signature(func).parameters) == params
        assert func.__doc__, f"{module_name}.{func_name} needs a docstring"
        if module_name in IMPLEMENTED:
            continue
        args = [None] * len(params)
        with pytest.raises(NotImplementedError):
            result = func(*args)
            if inspect.isawaitable(result):
                await result
