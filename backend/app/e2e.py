"""End-to-end check (T17): time one scan from "Run scan" to Jira ticket + Slack alert, through the public API.

    python -m app.e2e                                   # local backend, DEMO_REPO_URL
    python -m app.e2e --base-url https://patchpilot-api.onrender.com --expect-live
    python -m app.e2e --budget 120 --api-key "$PATCHPILOT_API_KEY"

It does what the dashboard does: POST /api/scans, follow the SSE stream, and poll the scan's P1/P2 findings until
one has a Jira key and `slack_sent` from Boomi B2. Exit code 0 = the first ticket arrived within `--budget` seconds
(acceptance: under 2 minutes, live). `--expect-live` also fails when any `*_MODE` is still `mock` (RISKS O1: the
modes are switched back to `mock` only as the fallback).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import get_settings

POLL_S = 2.0
URGENT = ("P1", "P2")


@dataclass
class E2EResult:
    scan_id: str = ""
    status: str = ""
    modes: dict[str, str] = field(default_factory=dict)
    stage_times: dict[str, float] = field(default_factory=dict)
    ticket_s: float | None = None
    jira_key: str | None = None
    pr_url: str | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    def passed(self, budget: float) -> bool:
        return not self.problems and self.ticket_s is not None and self.ticket_s <= budget


async def run_e2e(base_url: str, *, repo_url: str, client_name: str = "Acme Retail", branch: str = "main",
                  api_key: str = "", budget: float = 120.0, expect_live: bool = False,
                  transport: httpx.AsyncBaseTransport | None = None, log: Any = print) -> E2EResult:
    res = E2EResult()
    headers = {"X-API-Key": api_key} if api_key else {}
    async with httpx.AsyncClient(base_url=base_url.rstrip("/"), headers=headers, timeout=30.0,
                                 transport=transport) as client:
        health = (await client.get("/api/health")).json()
        res.modes = {k: health.get(k, "?") for k in ("llm_mode", "github_mode", "boomi_mode")}
        log(f"health: {res.modes}")
        if expect_live:
            res.problems += [f"{k}={v} (expected live)" for k, v in res.modes.items() if v != "live"]

        t0 = time.monotonic()
        r = await client.post("/api/scans", json={"client_name": client_name, "repo_url": repo_url,
                                                  "branch": branch, "auto_fix": True})
        if r.status_code != 202:
            res.problems.append(f"POST /api/scans -> {r.status_code}: {r.text[:200]}")
            return res
        res.scan_id = r.json()["scan_id"]
        log(f"scan {res.scan_id} started")

        stream = asyncio.create_task(_follow(client, res, t0, log))
        deadline = t0 + max(budget * 3, 300)
        while time.monotonic() < deadline:
            if await _ticket(client, res, t0):
                log(f"Jira {res.jira_key} + Slack after {res.ticket_s:.1f}s")
                break
            if stream.done():
                await _ticket(client, res, t0)  # the last B2 may land just before `done`
                break
            await asyncio.sleep(POLL_S)
        try:
            await asyncio.wait_for(stream, timeout=max(5.0, deadline - time.monotonic()))
        except TimeoutError:
            res.problems.append("scan did not finish in time")

        scan = (await client.get(f"/api/scans/{res.scan_id}")).json()
        res.status, res.stats = scan.get("status", ""), scan.get("stats", {})
    if res.status != "completed":
        res.problems.append(f"scan status {res.status or 'unknown'}")
    if res.ticket_s is None:
        res.problems.append("no P1/P2 finding got a Jira ticket + Slack alert")
    elif res.ticket_s > budget:
        res.problems.append(f"Jira + Slack took {res.ticket_s:.1f}s (budget {budget:g}s)")
    return res


async def _follow(client: httpx.AsyncClient, res: E2EResult, t0: float, log: Any) -> None:
    """Print each stage once, with the elapsed time (what the live scan page animates)."""
    async with client.stream("GET", f"/api/scans/{res.scan_id}/events", timeout=None) as resp:
        async for line in resp.aiter_lines():
            if not line.startswith("data:"):
                continue
            event = json.loads(line[5:])
            stage = event.get("stage", "")
            if stage not in res.stage_times:
                res.stage_times[stage] = round(time.monotonic() - t0, 1)
                log(f"{res.stage_times[stage]:6.1f}s  {stage:<12} {event.get('message', '')[:90]}")
            if stage == "done":
                return


async def _ticket(client: httpx.AsyncClient, res: E2EResult, t0: float) -> bool:
    findings = (await client.get("/api/findings", params={"scan_id": res.scan_id})).json()
    for f in findings:
        if f.get("priority") not in URGENT:
            continue
        detail = (await client.get(f"/api/findings/{f['finding_id']}")).json()
        integration = detail.get("integration") or {}
        if integration.get("jira_key") and integration.get("slack_sent"):
            res.ticket_s = round(time.monotonic() - t0, 1)
            res.jira_key = integration["jira_key"]
            res.pr_url = (detail.get("fix") or {}).get("pr_url")
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    s = get_settings()
    parser = argparse.ArgumentParser(prog="python -m app.e2e", description=__doc__.split("\n")[0])
    parser.add_argument("--base-url", default=s.backend_url)
    parser.add_argument("--repo-url", default=s.demo_repo_url or "https://github.com/BommepalliRoop/demo-target")
    parser.add_argument("--client-name", default="Acme Retail")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--api-key", default="", help="only needed if the backend requires X-API-Key")
    parser.add_argument("--budget", type=float, default=120.0, help="seconds from POST to Jira + Slack")
    parser.add_argument("--expect-live", action="store_true", help="fail if any *_MODE is mock")
    args = parser.parse_args(argv)
    res = asyncio.run(run_e2e(args.base_url, repo_url=args.repo_url, client_name=args.client_name,
                              branch=args.branch, api_key=args.api_key, budget=args.budget,
                              expect_live=args.expect_live))
    print(f"stats: {res.stats}")
    if res.pr_url:
        print(f"PR: {res.pr_url}")
    if res.passed(args.budget):
        print(f"PASS: Jira {res.jira_key} + Slack in {res.ticket_s:.1f}s (budget {args.budget:g}s)")
        return 0
    for p in res.problems:
        print(f"FAIL: {p}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
