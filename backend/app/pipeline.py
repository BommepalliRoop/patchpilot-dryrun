"""Orchestrator (T03): runs the 8 stages in order and emits SSE progress events on `app.core.events.bus`."""
from __future__ import annotations


async def run_scan(scan_id: str) -> None:
    """clone -> scan -> symbols -> reachability -> risk -> fix -> pr -> notify, then `done`.

    Runs as a background task. A failing stage for one finding is recorded and the rest continue (RISKS E3);
    a failing whole-scan stage marks the scan `failed` (E4). Workdir is always cleaned up (E13).
    """
    raise NotImplementedError("T03")
