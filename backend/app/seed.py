"""Demo seed (T17): `python -m app.seed` adds 2 historical scans so the dashboard is never empty.

    python -m app.seed               add the 2 scans (always adds; run once after a reset)
    python -m app.seed --reset       full demo reset first (DB, WORK_DIR, patchpilot/* PR branches — RISKS O3)
    python -m app.seed --if-empty    only seed when there are no scans yet (safe in a start script)

The seeded scans are what B1's daily 9:00 IST run would have left behind:
1. two days ago, Globex Logistics `clean-service`: 0 alerts, "no action needed".
2. yesterday, Acme Retail `demo-target`: the 40 real OSV advisories of its pins (`seed_data/`), 1 reachable P1
   (PyYAML `yaml.load` in `POST /import`) fixed by upgrade + AI patch, `requests` unsure and fixed, the rest noise;
   one B2 call per routed finding (Jira + Slack + compliance log) and a B3 summary.

It only writes the local SQLite DB: no network, no LLM, works with every `*_MODE=mock` (RISKS O1). PR and Jira
links of seeded findings are placeholders (`example.atlassian.net`, mock-style PR numbers), like mock mode.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from packaging.version import Version
from sqlmodel import Session

from app.core.db import get_engine, init_db
from app.core.ids import iso_z, utcnow
from app.models import repository as repo
from app.models.repository import FindingCreate
from app.models.schemas import Evidence, LanguageInfo, Reachability
from app.models.tables import IntegrationEventRow, ScanRow
from app.services import demo_reset, risk

DATA_FILE = Path(__file__).parent / "seed_data" / "demo_target_advisories.json"
DEMO_REPO = "https://github.com/BommepalliRoop/demo-target"
CLEAN_REPO = "https://github.com/BommepalliRoop/clean-service"
JIRA_BROWSE = "https://example.atlassian.net/browse/"
OWNER_EMAIL = "owner@easystepin.com"
B1_UTC = (3, 30)  # B1 runs daily at 9:00 IST = 03:30 UTC

IMPORTER_SNIPPET = '''import yaml


def parse_import_payload(raw: str) -> dict:
    """Parse a YAML import payload sent by a client."""
    data = yaml.load(raw)
    if not isinstance(data, dict):
        raise ValueError("import payload must be a mapping")
    return data'''

JOBS_SNIPPET = '''import threading

import requests


def fetch_status(url: str) -> int:
    """Fetch a URL in a background job and return the HTTP status code."""
    response = requests.get(url, timeout=10)
    return response.status_code'''

PYYAML_DIFF = """diff --git a/demo_app/importer.py b/demo_app/importer.py
--- a/demo_app/importer.py
+++ b/demo_app/importer.py
@@ -3,7 +3,7 @@ import yaml

 def parse_import_payload(raw: str) -> dict:
     \"\"\"Parse a YAML import payload sent by a client.\"\"\"
-    data = yaml.load(raw)
+    data = yaml.load(raw, Loader=yaml.SafeLoader)
     if not isinstance(data, dict):
         raise ValueError("import payload must be a mapping")
     return data
diff --git a/requirements.txt b/requirements.txt
--- a/requirements.txt
+++ b/requirements.txt
@@ -4,6 +4,6 @@ Jinja2==2.11.2
 MarkupSafe==1.1.1
 itsdangerous==1.1.0
 click==7.1.2
-PyYAML==5.3.1
+PyYAML==6.0.3
 requests==2.25.1
 urllib3==1.26.4
"""


@dataclass
class _Reach:
    reachability: Reachability
    confidence: float
    explanation: str
    symbols: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)


# package -> verdict; every other package is "not called directly by application code" (RISKS L9)
VERDICTS: dict[str, _Reach] = {
    "pyyaml": _Reach(
        "reachable", 0.93,
        "User-supplied YAML from POST /import reaches yaml.load without SafeLoader, so a crafted payload can "
        "construct arbitrary Python objects.",
        ["yaml.load", "yaml.full_load", "yaml.unsafe_load"],
        [Evidence(file="demo_app/importer.py", line=6, in_route=True, code_snippet=IMPORTER_SNIPPET, start_line=1)]),
    "requests": _Reach(
        "unsure", 0.6,
        "requests.get is called from a background job; the URL comes from configuration, so the AI could not prove "
        "an attacker controls it.",
        ["requests.get", "requests.Session.request"],
        [Evidence(file="demo_app/jobs.py", line=8, in_route=False, code_snippet=JOBS_SNIPPET, start_line=1)]),
    "lodash": _Reach(
        "unsure", 0.4,
        "_.template appears only in the offline report tool tools/report.js, not in the web app (text + AI analysis).",
        ["_.template", "lodash.template"]),
}
NOISE = _Reach("not_reachable", 0.9, "The vulnerable function is not called directly by application code.")


@dataclass
class SeedResult:
    scan_ids: list[str]
    findings: int
    fixes: int


def _at(base: datetime, seconds: float) -> str:
    return iso_z(base + timedelta(seconds=seconds))


def _b1_time(days_ago: int) -> datetime:
    day = utcnow() - timedelta(days=days_ago)
    return day.replace(hour=B1_UTC[0], minute=B1_UTC[1], second=0, microsecond=0)


def advisories() -> list[dict[str, Any]]:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))["advisories"]


def _backdate_scan(scan_id: str, started: str, finished: str) -> None:
    with Session(get_engine()) as s:
        row = s.get(ScanRow, scan_id)
        assert row is not None
        row.started_at, row.finished_at = started, finished
        s.add(row)
        s.commit()


def _event(at: str, process: str, endpoint: str, summary: str, *, finding_id: str | None = None,
           direction: str = "out", status_code: int = 200, request: Any = None, response: Any = None) -> None:
    event_id = repo.add_integration_event(process, endpoint, True, finding_id=finding_id, direction=direction,
                                          request=request, response=response, status_code=status_code,
                                          summary=summary)
    with Session(get_engine()) as s:
        row = s.get(IntegrationEventRow, event_id)
        assert row is not None
        row.created_at = at
        s.add(row)
        s.commit()


def _b1(at: str, client_name: str, repo_url: str, auto_fix: bool) -> None:
    _event(at, "B1", "/api/scans", f"Scheduled scan for {client_name}", direction="in", status_code=202,
           request={"client_name": client_name, "repo_url": repo_url, "branch": "main", "auto_fix": auto_fix,
                    "owner_email": OWNER_EMAIL})


def seed_clean_scan() -> str:
    """Two days ago: Globex Logistics, clean repo, nothing to do."""
    t0 = _b1_time(2)
    scan_id = repo.create_scan("Globex Logistics", CLEAN_REPO, "main", True, OWNER_EMAIL)
    repo.update_scan_stage(scan_id, "done", "completed",
                           [LanguageInfo(ecosystem="PyPI", manifests=["requirements.txt"], analysis="deep")])
    _backdate_scan(scan_id, _at(t0, 0), _at(t0, 21))
    _b1(_at(t0, 0), "Globex Logistics", CLEAN_REPO, True)
    _event(_at(t0, 21), "B3", "/patchpilot/scan-summary", "Slack summary sent: scan clean, no action needed",
           request={"scan_id": scan_id, "client_name": "Globex Logistics", "total_alerts": 0}, response={"ok": True})
    return scan_id


def _timeline(t0: datetime, verdict: _Reach, score: float, priority: str) -> Iterator[dict[str, str]]:
    yield {"stage": "scan", "at": _at(t0, 9), "message": "Detected via OSV"}
    if verdict.symbols:
        yield {"stage": "symbols", "at": _at(t0, 14), "message": f"Vulnerable functions: {', '.join(verdict.symbols)}"}
    where = f" at {verdict.evidence[0].file}:{verdict.evidence[0].line}" if verdict.evidence else ""
    yield {"stage": "reachability", "at": _at(t0, 31),
           "message": f"{verdict.reachability} (confidence {verdict.confidence:.2f}){where}"}
    yield {"stage": "risk", "at": _at(t0, 33), "message": f"Risk score {score} ({priority})"}


def seed_demo_scan() -> tuple[str, int, int]:
    """Yesterday: Acme Retail demo-target. Returns (scan_id, findings, fixes)."""
    t0 = _b1_time(1)
    scan_id = repo.create_scan("Acme Retail", DEMO_REPO, "main", True, OWNER_EMAIL)
    repo.update_scan_stage(scan_id, "done", "completed", [
        LanguageInfo(ecosystem="PyPI", manifests=["requirements.txt"], analysis="deep"),
        LanguageInfo(ecosystem="npm", manifests=["package-lock.json"], analysis="generic"),
    ])
    _b1(_at(t0, 0), "Acme Retail", DEMO_REPO, True)

    routed: dict[str, list[tuple[str, dict[str, Any], float, str]]] = {}
    count = 0
    for adv in advisories():
        verdict = VERDICTS.get(adv["package"], NOISE)
        score, priority = risk.score(adv["cvss"], verdict.reachability, verdict.evidence, adv["kev"],
                                     adv["epss_percentile"])
        explanation = verdict.explanation
        finding_id = repo.add_finding(scan_id, FindingCreate(
            **adv, vulnerable_symbols=verdict.symbols, reachability=verdict.reachability,
            confidence=verdict.confidence, evidence=verdict.evidence, ai_explanation=explanation,
            score=score, priority=priority, status="open"))
        repo.update_finding(finding_id, timeline=list(_timeline(t0, verdict, score, priority)))
        count += 1
        if verdict.reachability == "reachable" or (verdict.reachability == "unsure" and verdict.confidence >= 0.5):
            routed.setdefault(adv["package"], []).append((finding_id, adv, score, priority))

    jira = 90
    fixes = 0
    for pr_number, (package, items) in enumerate(sorted(routed.items()), start=1):
        new_version = "6.0.3" if package == "pyyaml" else max((a["fixed_version"] for _, a, _, _ in items),
                                                               key=Version)
        attempts = 1 if package == "pyyaml" else 0
        diff = PYYAML_DIFF if package == "pyyaml" else _requirements_diff(package, items[0][1], new_version)
        pr_url = f"{DEMO_REPO}/pull/{pr_number}"
        repo.add_fix(scan_id, package, new_version, diff, True, attempts, pr_url, "fixed",
                     finding_ids=[fid for fid, _, _, _ in items])
        fixes += 1
        for finding_id, adv, score, priority in items:
            jira += 1
            key = f"SEC-{jira}"
            fix_msg = f"Upgraded to {new_version}" + (" + AI patch (1 attempt)" if attempts else "") + ", tests passed"
            for stage, offset, message in (("fix", 74, fix_msg), ("pr", 88, f"Pull request opened: {pr_url}"),
                                           ("notify", 99, f"Boomi: Jira {key} created, Slack sent")):
                repo.append_timeline(finding_id, stage, message)
                _retime_last(finding_id, _at(t0, offset))
            repo.update_finding(finding_id, status="fixed", jira_key=key, jira_url=JIRA_BROWSE + key,
                                slack_sent=True, compliance_log_id=f"log_{finding_id}")
            _event(_at(t0, 99), "B2", "/patchpilot/findings", f"Jira {key} created, Slack sent", finding_id=finding_id,
                   request={"event": "finding.fixed", "finding_id": finding_id, "cve_id": adv["cve_id"],
                            "priority": priority, "score": score, "fix_status": "fixed", "pr_url": pr_url},
                   response={"ok": True, "jira_key": key, "slack_sent": True,
                             "compliance_log_id": f"log_{finding_id}"})

    stats = repo.get_scan(scan_id).stats  # type: ignore[union-attr]
    _event(_at(t0, 102), "B3", "/patchpilot/scan-summary",
           f"Slack summary sent: {stats.total_alerts} alerts, {stats.reachable} reachable, {stats.p1} P1, "
           f"{stats.prs_opened} PRs", request={"scan_id": scan_id, "client_name": "Acme Retail", **stats.model_dump()},
           response={"ok": True, "slack_sent": True})
    _backdate_scan(scan_id, _at(t0, 0), _at(t0, 102))
    return scan_id, count, fixes


def _retime_last(finding_id: str, at: str) -> None:
    """append_timeline stamps 'now'; seeded history needs the historical time."""
    detail = repo.get_finding(finding_id)
    assert detail is not None
    items = [t.model_dump() for t in detail.timeline]
    items[-1]["at"] = at
    repo.update_finding(finding_id, timeline=items)


def _requirements_diff(package: str, adv: dict[str, Any], new_version: str) -> str:
    return (f"diff --git a/requirements.txt b/requirements.txt\n--- a/requirements.txt\n+++ b/requirements.txt\n"
            f"@@ -8,2 +8,2 @@\n-{package}=={adv['installed_version']}\n+{package}=={new_version}\n urllib3==1.26.4\n")


def seed() -> SeedResult:
    """Add the 2 historical scans (oldest first, so the demo scan is the newest)."""
    init_db()
    clean_id = seed_clean_scan()
    demo_id, findings, fixes = seed_demo_scan()
    return SeedResult(scan_ids=[clean_id, demo_id], findings=findings, fixes=fixes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.seed", description="Seed 2 historical demo scans (T17).")
    parser.add_argument("--reset", action="store_true",
                        help="demo reset first: DB, WORK_DIR and patchpilot/* PR branches (GITHUB_MODE=live)")
    parser.add_argument("--if-empty", action="store_true", help="do nothing when scans already exist")
    args = parser.parse_args(argv)
    init_db()
    if args.reset:
        report = asyncio.run(demo_reset.reset())
        print(f"reset: {report.work_dirs_removed} work dir(s), {len(report.prs_closed)} PR(s) closed, "
              f"{len(report.branches_deleted)} branch(es) deleted")
        for err in report.errors:
            print(f"reset warning: {err}", file=sys.stderr)
    if args.if_empty and repo.list_scans(limit=1):
        print("seed: scans already exist, nothing to do")
        return 0
    result = seed()
    print(f"seed: {len(result.scan_ids)} scans ({', '.join(result.scan_ids)}), {result.findings} findings, "
          f"{result.fixes} fixes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
