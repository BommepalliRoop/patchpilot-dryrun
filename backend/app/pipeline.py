"""Orchestrator (T03): runs the 8 stages in order and emits SSE progress events on `app.core.events.bus`.

Stages (docs/ARCHITECTURE.md "Pipeline stages"):
clone -> scan -> symbols -> reachability -> risk -> fix -> pr -> notify -> done.

- Whole-scan stages (clone, scan) that fail mark the scan `failed` (RISKS E4).
- Per-finding stages (symbols, reachability, risk) run with `asyncio.gather`, at most 4 at a time; a failure marks
  only that finding (`needs_human` + timeline reason) and the others continue (E3).
- Only reachable findings and `unsure` with confidence >= 0.5 go to fix / pr / notify. Fix + PR run once per
  package (L7); notify runs per finding. `auto_fix=false` skips fix + pr but still notifies (`finding.open`).
- A stage whose module still raises `NotImplementedError` (another lane not merged yet) gets a clearly logged
  stub result so the pipeline still completes.
- Boomi failures never fail the scan or the finding (N6). Overall timeout `SCAN_TIMEOUT_S` (E6). The workdir is
  always cleaned (E13).
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, TypeVar

from sqlmodel import Session

from app.core.config import get_settings
from app.core.db import get_engine
from app.core.events import ScanEvent, Stage, bus
from app.core.ids import iso_z, utcnow
from app.core.logging import log_context
from app.core.security import redact
from app.models import repository as repo
from app.models.domain import B2Response, FixResult, RawVuln, Verdict, VulnSymbols
from app.models.repository import FindingCreate
from app.models.schemas import Evidence, FindingDetail, Priority, ScanStats
from app.models.tables import FindingRow, ScanRow
from app.services import boomi_client, cloner, ecosystems, fixer, github_pr, reachability, risk, scanner, symbols, threat_intel

logger = logging.getLogger("patchpilot.pipeline")

STAGES: tuple[Stage, ...] = ("clone", "scan", "symbols", "reachability", "risk", "fix", "pr", "notify")
CONCURRENCY = 4
PROGRESS_EVENTS_PER_STAGE = 25  # keeps a whole scan well inside the 200-event replay buffer (RISKS N8)
UNSURE_THRESHOLD = 0.5
FIXED_STATUSES = ("fixed", "fixed_untested")

T = TypeVar("T")
R = TypeVar("R")


class StageFailed(Exception):
    """A whole-scan stage failed; the message is safe to show to users."""

    def __init__(self, stage: Stage, message: str) -> None:
        super().__init__(message)
        self.stage = stage


@dataclass
class _Item:
    """One finding as it moves through the per-finding stages."""

    finding_id: str
    vuln: RawVuln
    symbols: VulnSymbols | None = None
    verdict: Verdict | None = None
    priority: Priority = "P4"
    failed: bool = False


@dataclass
class _PackageFix:
    """Stages 6-7 result for one package (all its routed findings)."""

    items: list[_Item]
    fix: FixResult | None = None
    fix_id: str | None = None
    pr_url: str | None = None
    pr_error: str | None = None


@dataclass
class _Run:
    """Mutable state of one scan run (lives only as long as the run)."""

    scan_id: str
    repo_url: str
    branch: str
    client_name: str
    auto_fix: bool
    owner_email: str
    stage: Stage = "clone"
    work_id: str = ""  # WORK_DIR/<work_id> holds the clone; scan_id for scans, a unique id for manual fixes
    repo_path: Path | None = None
    items: list[_Item] = field(default_factory=list)
    stubbed: set[str] = field(default_factory=set)

    def emit(self, stage: Stage, status: str, message: str, fraction: float = 0.0,
             data: dict[str, Any] | None = None) -> None:
        bus.publish(ScanEvent(scan_id=self.scan_id, stage=stage, status=status, message=message,
                              progress=_progress(stage, fraction), data=data or {}))


def _progress(stage: Stage, fraction: float) -> float:
    if stage == "done":
        return 1.0
    i = STAGES.index(stage)
    return round(min(0.99, (i + max(0.0, min(1.0, fraction))) / len(STAGES)), 3)


def is_routed(reach: str, confidence: float) -> bool:
    """Stages 6-8 only see reachable findings and `unsure` ones with confidence >= 0.5."""
    return reach == "reachable" or (reach == "unsure" and confidence >= UNSURE_THRESHOLD)


async def _gather_limited(items: Sequence[T], fn: Callable[[T], Awaitable[R]], limit: int = CONCURRENCY) -> list[R]:
    sem = asyncio.Semaphore(limit)

    async def one(x: T) -> R:
        async with sem:
            return await fn(x)

    return list(await asyncio.gather(*(one(x) for x in items)))


async def _call(run: _Run, stage: str, owner: str, call: Callable[[], Awaitable[T]], stub: Callable[[], T]) -> T:
    """Call a stage module; a module that is not implemented yet gets a stub result (logged once per run)."""
    try:
        return await call()
    except NotImplementedError:
        if stage not in run.stubbed:
            run.stubbed.add(stage)
            logger.warning("STUB: stage %s is not implemented yet (%s); using a stub result", stage, owner)
        return stub()


def _safe(e: BaseException) -> str:
    text = str(e).strip() or type(e).__name__
    return redact(text)[:300]


# --------------------------------------------------------------------------- stubs (until T04-T10 land)

def _stub_symbols(vuln: RawVuln) -> VulnSymbols:
    return VulnSymbols(package=vuln.package, symbols=[], confidence=0.0,
                       safe_usage_notes="stub: symbol extraction not available")


def _stub_verdict(vuln: RawVuln) -> Verdict:
    return Verdict(reachable="unsure", confidence=0.0, analysis=vuln.analysis,
                   explanation="Reachability analysis not available yet (stub result).")


def _stub_score(cvss: float, reach: str, evidence: list[Evidence], kev: bool,
                epss_percentile: float | None) -> tuple[float, Priority]:
    """Same formula as docs/ARCHITECTURE.md "Risk score"; replaced by services/risk.py (T07)."""
    reach_w = {"reachable": 1.0, "unsure": 0.6}.get(reach, 0.3)
    exposure_w = 1.5 if any(e.in_route for e in evidence) else 1.0
    threat_w = 1.3 if kev else 1.1 if (epss_percentile or 0) >= 0.9 else 1.0
    value = round(min(10.0, max(0.0, cvss) * reach_w * exposure_w * threat_w), 1)
    prio: Priority = "P1" if value >= 9 else "P2" if value >= 7 else "P3" if value >= 4 else "P4"
    return value, prio


def _stub_fix(package: str) -> FixResult:
    return FixResult(package=package, status="needs_human", reason="fix engine not available yet (stub)")


# --------------------------------------------------------------------------- public entry points

async def run_scan(scan_id: str) -> None:
    """clone -> scan -> symbols -> reachability -> risk -> fix -> pr -> notify, then `done`.

    Runs as a background task and never raises. A failing stage for one finding is recorded and the rest continue
    (RISKS E3); a failing whole-scan stage marks the scan `failed` (E4). Workdir is always cleaned up (E13).
    """
    with log_context(scan_id=scan_id):
        run = _load_run(scan_id)
        if run is None:
            logger.error("run_scan: scan %s not found", scan_id)
            return
        run.work_id = scan_id
        timeout = get_settings().scan_timeout_s
        try:
            repo.update_scan_stage(scan_id, "clone", "running")
            await asyncio.wait_for(_run_stages(run), timeout)
        except TimeoutError:
            _fail(run, run.stage, f"Scan timed out after {timeout}s (timeout)")
        except StageFailed as e:
            _fail(run, e.stage, str(e))
        except Exception as e:  # noqa: BLE001 - background task: record, never crash the server
            logger.exception("scan crashed in stage %s", run.stage)
            _fail(run, run.stage, f"Internal error in stage {run.stage}: {_safe(e)}")
        else:
            repo.update_scan_stage(scan_id, "done", "completed")
            stats = _stats(scan_id)
            run.emit("done", "completed", "Scan complete", data={"stats": stats.model_dump()})
            logger.info("scan completed: %s", stats.model_dump())
        finally:
            _cleanup(run.work_id)


async def run_fix(finding_id: str) -> None:
    """`POST /api/findings/{id}/fix`: re-clone, fix the finding's package, open the PR and notify Boomi again.

    The finding must already be `fixing` (set by the route). Never raises.
    """
    finding = repo.get_finding(finding_id)
    scan_id = _scan_id_of(finding_id)
    if finding is None or scan_id is None:
        logger.error("run_fix: finding %s not found", finding_id)
        return
    with log_context(scan_id=scan_id, finding_id=finding_id):
        run = _load_run(scan_id)
        if run is None:
            return
        run.work_id = f"{scan_id}-fix-{secrets.token_hex(3)}"
        run.auto_fix = True
        targets = _manual_fix_targets(scan_id, finding)
        run.items = [_Item(finding_id=f.finding_id, vuln=_vuln_from_detail(f), priority=f.priority) for f in targets]
        try:
            await asyncio.wait_for(_manual_fix(run), get_settings().scan_timeout_s)
        except Exception as e:  # noqa: BLE001 - TimeoutError included: the finding is marked, nothing crashes
            reason = "timeout" if isinstance(e, TimeoutError) else _safe(e)
            logger.warning("manual fix failed: %s", reason)
            for it in run.items:
                current = repo.get_finding(it.finding_id)
                if current is not None and current.status == "fixing":
                    repo.update_finding(it.finding_id, status="needs_human")
                    repo.append_timeline(it.finding_id, "fix", f"Manual fix failed: {reason}")
        finally:
            _cleanup(run.work_id)


def mark_interrupted_scans() -> int:
    """RISKS E5: on startup, scans left `queued`/`running` by a restart become `failed`."""
    count = 0
    for status in ("queued", "running"):
        for scan in repo.list_scans(status=status, limit=1000):  # type: ignore[arg-type]
            repo.update_scan_stage(scan.scan_id, scan.current_stage, "failed")
            bus.publish(ScanEvent(scan_id=scan.scan_id, stage=scan.current_stage if scan.current_stage in STAGES  # type: ignore[arg-type]
                                  else "clone", status="failed", message="Scan interrupted by restart"))
            bus.publish(ScanEvent(scan_id=scan.scan_id, stage="done", status="failed",
                                  message="Scan interrupted by restart", progress=1.0))
            count += 1
    for finding in repo.list_findings(status="fixing"):
        repo.update_finding(finding.finding_id, status="needs_human")
        repo.append_timeline(finding.finding_id, "fix", "Fix interrupted by restart")
    if count:
        logger.warning("marked %d interrupted scan(s) as failed", count)
    return count


# --------------------------------------------------------------------------- the stages

async def _run_stages(run: _Run) -> None:
    await _stage_clone(run)
    await _stage_scan(run)
    await _stage_per_finding(run, "symbols", _symbols_one)
    await _stage_per_finding(run, "reachability", _reachability_one)
    await _stage_per_finding(run, "risk", _risk_one)
    routed = [it for it in run.items if not it.failed and it.verdict and is_routed(it.verdict.reachable,
                                                                                    it.verdict.confidence)]
    groups = _group_by_package(routed)
    if run.auto_fix:
        await _stage_fix(run, groups)
        await _stage_pr(run, groups)
    else:
        for stage in ("fix", "pr"):
            _enter(run, stage)  # type: ignore[arg-type]
            run.emit(stage, "skipped", "auto_fix is off: fix and pull request skipped")  # type: ignore[arg-type]
    await _stage_notify(run, routed, groups)


def _enter(run: _Run, stage: Stage) -> None:
    run.stage = stage
    repo.update_scan_stage(run.scan_id, stage)


async def _stage_clone(run: _Run) -> None:
    _enter(run, "clone")
    run.emit("clone", "running", f"Cloning {redact(run.repo_url)} ({run.branch})")
    try:
        run.repo_path = await cloner.clone(run.repo_url, run.branch, run.work_id)
    except Exception as e:  # noqa: BLE001 - CloneError and anything unexpected end the scan the same way
        raise StageFailed("clone", f"Clone failed: {_safe(e)}") from None
    run.emit("clone", "completed", "Repository cloned", 1.0)


async def _stage_scan(run: _Run) -> None:
    _enter(run, "scan")
    assert run.repo_path is not None
    run.emit("scan", "running", "Detecting languages and manifests")
    try:
        languages = ecosystems.detect(run.repo_path)
        repo.update_scan_stage(run.scan_id, "scan", languages=languages)
        names = ", ".join(lang.ecosystem for lang in languages) or "none"
        run.emit("scan", "running", f"Scanning dependencies with OSV ({names})", 0.2,
                 {"languages": [lang.model_dump() for lang in languages]})
        vulns = await scanner.scan(run.repo_path)
        run.emit("scan", "running", f"Checking {len(vulns)} advisories against CISA KEV and EPSS", 0.6)
        vulns = await threat_intel.enrich(vulns)
    except Exception as e:  # noqa: BLE001
        raise StageFailed("scan", f"Scan failed: {_safe(e)}") from None
    for v in vulns:
        fid = repo.add_finding(run.scan_id, FindingCreate(
            cve_id=v.cve_id, package=v.package, installed_version=v.installed_version, ecosystem=v.ecosystem,
            analysis=v.analysis, aliases=v.aliases, fixed_version=v.fixed_versions[0] if v.fixed_versions else None,
            summary=v.summary, cvss=v.cvss, kev=v.kev, kev_date_added=v.kev_date_added, epss=v.epss,
            epss_percentile=v.epss_percentile, reachability="unsure", confidence=0.0,
        ))
        if v.threat_feed_unavailable:
            repo.append_timeline(fid, "scan", "threat feed unavailable")
        if v.kev:
            repo.append_timeline(fid, "scan", f"Listed in CISA KEV (actively exploited) since {v.kev_date_added or '?'}")
        run.items.append(_Item(finding_id=fid, vuln=v))
    run.emit("scan", "completed", f"Found {len(vulns)} vulnerable dependencies", 1.0, {"total_alerts": len(vulns)})


async def _stage_per_finding(run: _Run, stage: Stage, fn: Callable[[_Run, _Item], Awaitable[None]]) -> None:
    _enter(run, stage)
    items = [it for it in run.items if not it.failed]
    run.emit(stage, "running", f"{stage.capitalize()}: {len(items)} findings")
    done = 0

    async def one(it: _Item) -> None:
        nonlocal done
        with log_context(finding_id=it.finding_id):
            try:
                await fn(run, it)
            except Exception as e:  # noqa: BLE001 - RISKS E3: mark this finding, continue the others
                it.failed = True
                reason = _safe(e)
                logger.warning("%s failed for %s: %s", stage, it.vuln.cve_id, reason)
                repo.update_finding(it.finding_id, status="needs_human")
                repo.append_timeline(it.finding_id, stage, f"{stage} failed: {reason}")
                run.emit(stage, "running", f"{stage} failed for {it.vuln.cve_id} in {it.vuln.package}: {reason}",
                         done / max(1, len(items)), {"finding_id": it.finding_id, "failed": True})
        done += 1

    await _gather_limited(items, one)
    failed = sum(1 for it in items if it.failed)
    suffix = f" ({failed} failed)" if failed else ""
    run.emit(stage, "completed", f"{stage.capitalize()} done for {len(items) - failed} findings{suffix}", 1.0)


async def _symbols_one(run: _Run, it: _Item) -> None:
    it.symbols = await _call(run, "symbols", "T05", lambda: symbols.extract(it.vuln), lambda: _stub_symbols(it.vuln))
    repo.update_finding(it.finding_id, vulnerable_symbols=it.symbols.symbols)
    if it.symbols.symbols:
        repo.append_timeline(it.finding_id, "symbols", f"Vulnerable functions: {', '.join(it.symbols.symbols[:5])}")
    if _report(run, it):
        run.emit("symbols", "running", f"{it.vuln.package}: {', '.join(it.symbols.symbols[:3]) or 'no symbols'}",
                 _fraction(run, it), {"finding_id": it.finding_id})


async def _reachability_one(run: _Run, it: _Item) -> None:
    assert run.repo_path is not None
    syms = it.symbols or _stub_symbols(it.vuln)
    if _report(run, it):
        run.emit("reachability", "running", f"Checking {', '.join(syms.symbols[:2]) or it.vuln.package} "
                 f"for {it.vuln.cve_id}", _fraction(run, it), {"finding_id": it.finding_id})
    v = await _call(run, "reachability", "T06", lambda: reachability.analyze(run.repo_path, it.vuln, syms),  # type: ignore[arg-type]
                    lambda: _stub_verdict(it.vuln))
    it.verdict = v
    repo.update_finding(it.finding_id, reachability=v.reachable, confidence=v.confidence, evidence=v.evidence,
                        ai_explanation=v.explanation)
    where = f" at {v.evidence[0].file}:{v.evidence[0].line}" if v.evidence else ""
    repo.append_timeline(it.finding_id, "reachability", f"{v.reachable} (confidence {v.confidence:.2f}){where}")


async def _risk_one(run: _Run, it: _Item) -> None:
    v = it.verdict or _stub_verdict(it.vuln)
    args = (it.vuln.cvss, v.reachable, v.evidence, it.vuln.kev, it.vuln.epss_percentile)

    async def call() -> tuple[float, Priority]:
        return risk.score(*args)

    value, prio = await _call(run, "risk", "T07", call, lambda: _stub_score(*args))
    it.priority = prio
    repo.update_finding(it.finding_id, score=value, priority=prio)
    repo.append_timeline(it.finding_id, "risk", f"Risk score {value} ({prio})")


def _report(run: _Run, it: _Item) -> bool:
    """Per-finding progress events for at most PROGRESS_EVENTS_PER_STAGE findings per stage (failures always)."""
    step = -(-len(run.items) // PROGRESS_EVENTS_PER_STAGE)
    return run.items.index(it) % max(1, step) == 0


def _fraction(run: _Run, it: _Item) -> float:
    try:
        return run.items.index(it) / max(1, len(run.items))
    except ValueError:
        return 0.0


def _group_by_package(items: list[_Item]) -> list[_PackageFix]:
    """RISKS L7: one fix + one PR per package."""
    groups: dict[tuple[str, str], list[_Item]] = {}
    for it in items:
        groups.setdefault((it.vuln.ecosystem, it.vuln.package), []).append(it)
    return [_PackageFix(items=g) for g in groups.values()]


async def _fix_group(run: _Run, g: _PackageFix) -> None:
    """Stage 6 for one package: run the fixer (or its stub) and store one fix row linked to every finding."""
    assert run.repo_path is not None
    package = g.items[0].vuln.package
    vulns = [it.vuln for it in g.items]
    repo_path = run.repo_path
    try:
        g.fix = await _call(run, "fix", "T08", lambda: fixer.fix_package(run.work_id, repo_path, package, vulns),
                            lambda: _stub_fix(package))
    except Exception as e:  # noqa: BLE001 - RISKS E3: this package needs a human, the others continue
        logger.warning("fix failed for %s: %s", package, _safe(e))
        g.fix = FixResult(package=package, status="needs_human", reason=f"fix failed: {_safe(e)}")
    fx = g.fix
    g.fix_id = repo.add_fix(run.scan_id, package, fx.new_version, fx.patch_diff, fx.tests_passed, fx.attempts,
                            None, fx.status, finding_ids=[it.finding_id for it in g.items])


async def _pr_group(run: _Run, g: _PackageFix) -> None:
    """Stage 7 for one package: open (or reuse) the PR. Only called for fixed / fixed_untested packages."""
    assert g.fix is not None and g.fix_id is not None
    fx = g.fix
    details = [d for d in (repo.get_finding(it.finding_id) for it in g.items) if d is not None]
    try:
        g.pr_url = await _call(run, "pr", "T09", lambda: github_pr.open_pr(run.repo_url, run.branch, fx, details),
                               lambda: None)
    except Exception as e:  # noqa: BLE001 - RISKS E3: the fix stays recorded, the findings need a human
        g.pr_error = _safe(e)
        logger.warning("PR failed for %s: %s", fx.package, g.pr_error)
    if g.pr_url:
        repo.update_fix(g.fix_id, pr_url=g.pr_url)


def _fix_message(fx: FixResult) -> str:
    if fx.status not in FIXED_STATUSES:
        return f"Automatic fix failed: {fx.reason or 'needs human review'}"
    tests = ", tests passed" if fx.tests_passed else ", tests not run" if fx.status == "fixed_untested" else ""
    return f"Upgraded {fx.package} to {fx.new_version}{tests}"


async def _stage_fix(run: _Run, groups: list[_PackageFix]) -> None:
    _enter(run, "fix")
    if not groups:
        run.emit("fix", "skipped", "No reachable findings to fix")
        return
    run.emit("fix", "running", f"Fixing {len(groups)} package(s)")
    done = 0

    async def one(g: _PackageFix) -> None:
        nonlocal done
        package = g.items[0].vuln.package
        ids = [it.finding_id for it in g.items]
        for fid in ids:
            repo.update_finding(fid, status="fixing")
        run.emit("fix", "running", f"Upgrading {package} ({len(ids)} CVE(s))", done / len(groups),
                 {"package": package, "finding_ids": ids})
        await _fix_group(run, g)
        assert g.fix is not None
        ok = g.fix.status in FIXED_STATUSES
        for fid in ids:
            repo.update_finding(fid, status="fixed" if ok else "needs_human")
            repo.append_timeline(fid, "fix", _fix_message(g.fix))
        done += 1
        run.emit("fix", "running", f"{package}: {g.fix.status}", done / len(groups),
                 {"package": package, "status": g.fix.status, "fix_id": g.fix_id})

    await _gather_limited(groups, one, get_settings().fix_concurrency)
    fixed = sum(1 for g in groups if g.fix and g.fix.status in FIXED_STATUSES)
    run.emit("fix", "completed", f"{fixed}/{len(groups)} package(s) fixed", 1.0)


async def _stage_pr(run: _Run, groups: list[_PackageFix]) -> None:
    _enter(run, "pr")
    todo = [g for g in groups if g.fix and g.fix.status in FIXED_STATUSES]
    if not todo:
        run.emit("pr", "skipped", "No fixes to open pull requests for")
        return
    run.emit("pr", "running", f"Opening {len(todo)} pull request(s)")
    done = 0

    async def one(g: _PackageFix) -> None:
        nonlocal done
        await _pr_group(run, g)
        for it in g.items:
            if g.pr_error:
                repo.update_finding(it.finding_id, status="needs_human")
                repo.append_timeline(it.finding_id, "pr", f"Pull request failed: {g.pr_error}")
            elif g.pr_url:
                repo.append_timeline(it.finding_id, "pr", f"Pull request opened: {g.pr_url}")
            else:
                repo.append_timeline(it.finding_id, "pr", "Pull request not opened (PR module not available yet)")
        done += 1
        package = g.items[0].vuln.package
        run.emit("pr", "running", f"{package}: {g.pr_url or g.pr_error or 'no pull request'}", done / len(todo),
                 {"package": package, "pr_url": g.pr_url})

    await _gather_limited(todo, one)
    opened = sum(1 for g in todo if g.pr_url)
    run.emit("pr", "completed", f"{opened} pull request(s) opened", 1.0)


async def _stage_notify(run: _Run, routed: list[_Item], groups: list[_PackageFix]) -> None:
    _enter(run, "notify")
    run.emit("notify", "running", f"Notifying Boomi about {len(routed)} finding(s)")
    by_finding = {it.finding_id: g for g in groups for it in g.items}

    async def one(it: _Item) -> None:
        with log_context(finding_id=it.finding_id):
            await _notify_one(run, it.finding_id, by_finding.get(it.finding_id))

    await _gather_limited(routed, one)
    await _send_summary(run)
    run.emit("notify", "completed", f"Boomi notified ({len(routed)} finding(s) + scan summary)", 1.0)


# --------------------------------------------------------------------------- Boomi (N6: never fails anything)

def build_b2_payload(run: _Run, detail: FindingDetail, group: _PackageFix | None) -> dict[str, Any]:
    """contracts/boomi/B2_finding_request.json."""
    fix = group.fix if group else None
    if not run.auto_fix or fix is None:
        event, fix_status = "finding.open", "not_attempted"
    elif fix.status in FIXED_STATUSES and not group.pr_error:  # type: ignore[union-attr]
        event, fix_status = "finding.fixed", fix.status
    else:
        event, fix_status = "finding.needs_human", "needs_human"
    return {
        "event": event, "scan_id": run.scan_id, "finding_id": detail.finding_id, "client_name": run.client_name,
        "repo_url": run.repo_url, "cve_id": detail.cve_id, "package": detail.package, "ecosystem": detail.ecosystem,
        "installed_version": detail.installed_version,
        "fixed_version": (fix.new_version if fix and fix.new_version else detail.fixed_version),
        "cvss": detail.cvss, "priority": detail.priority, "score": detail.score, "kev": detail.kev,
        "epss": detail.epss, "epss_percentile": detail.epss_percentile, "reachability": detail.reachability,
        "confidence": detail.confidence, "summary": detail.summary, "ai_explanation": detail.ai_explanation,
        "evidence": [{"file": e.file, "line": e.line, "in_route": e.in_route} for e in detail.evidence],
        "fix_status": fix_status, "tests_passed": bool(fix and fix.tests_passed and fix_status == "fixed"),
        "pr_url": group.pr_url if group else None, "owner_email": run.owner_email,
        "detected_at": detail.timeline[0].at if detail.timeline else iso_z(),
    }


async def _notify_one(run: _Run, finding_id: str, group: _PackageFix | None) -> None:
    detail = repo.get_finding(finding_id)
    if detail is None:
        return
    payload = build_b2_payload(run, detail, group)
    try:
        resp = await _call(run, "notify", "T10", lambda: boomi_client.notify_finding(payload), lambda: None)
    except Exception as e:  # noqa: BLE001 - RISKS N6
        reason = _safe(e)
        logger.warning("Boomi B2 failed: %s", reason)
        repo.add_integration_event("B2", get_settings().boomi_b2_path, False, finding_id=finding_id,
                                   request=payload, summary=f"B2 failed: {reason}")
        repo.append_timeline(finding_id, "notify", f"Boomi notification failed: {reason}")
        return
    if resp is None:
        repo.append_timeline(finding_id, "notify", "Boomi notification skipped (Boomi client not available yet)")
        return
    _apply_b2(finding_id, resp)


def _apply_b2(finding_id: str, resp: B2Response) -> None:
    if not resp.ok:
        repo.append_timeline(finding_id, "notify", f"Boomi notification failed: {resp.error or resp.message or 'error'}")
        return
    repo.update_finding(finding_id, jira_key=resp.jira_key, jira_url=resp.jira_url, slack_sent=resp.slack_sent,
                        compliance_log_id=resp.compliance_log_id)
    parts = [f"Jira {resp.jira_key} created" if resp.jira_key else "", "Slack sent" if resp.slack_sent else ""]
    repo.append_timeline(finding_id, "notify", "Boomi: " + (", ".join(p for p in parts if p) or "notified"))


async def _send_summary(run: _Run) -> None:
    """B3 scan summary (contracts/boomi/B3_scan_summary_request.json)."""
    s = get_settings()
    payload = {
        "event": "scan.completed", "scan_id": run.scan_id, "client_name": run.client_name, "repo_url": run.repo_url,
        "finished_at": iso_z(), "stats": _stats(run.scan_id).model_dump(),
        "dashboard_url": f"{s.frontend_url.rstrip('/')}/scans/{run.scan_id}",
    }
    try:
        await _call(run, "notify:B3", "T10", lambda: boomi_client.send_scan_summary(payload), lambda: None)
    except Exception as e:  # noqa: BLE001 - RISKS N6
        reason = _safe(e)
        logger.warning("Boomi B3 failed: %s", reason)
        repo.add_integration_event("B3", s.boomi_b3_path, False, request=payload, summary=f"B3 failed: {reason}")


# --------------------------------------------------------------------------- manual fix

async def _manual_fix(run: _Run) -> None:
    for it in run.items:
        repo.update_finding(it.finding_id, status="fixing")
    run.repo_path = await cloner.clone(run.repo_url, run.branch, run.work_id)
    for g in _group_by_package(run.items):
        await _fix_group(run, g)
        assert g.fix is not None
        if g.fix.status in FIXED_STATUSES:
            await _pr_group(run, g)
        good = g.fix.status in FIXED_STATUSES and not g.pr_error
        for it in g.items:
            repo.update_finding(it.finding_id, status="fixed" if good else "needs_human")
            repo.append_timeline(it.finding_id, "fix", f"Manual fix: {_fix_message(g.fix)}" if not g.pr_error
                                 else f"Manual fix: pull request failed: {g.pr_error}")
            await _notify_one(run, it.finding_id, g)  # same Idempotency-Key, new fix_status (BOOMI_FLOW section 3)


def _manual_fix_targets(scan_id: str, finding: FindingDetail) -> list[FindingDetail]:
    """The finding plus the other routed findings of the same package in this scan (one fix per package)."""
    out = [finding]
    for f in repo.list_findings(scan_id=scan_id):
        if (f.finding_id != finding.finding_id and f.package == finding.package and f.ecosystem == finding.ecosystem
                and f.status not in ("ignored", "fixed") and is_routed(f.reachability, f.confidence)):
            d = repo.get_finding(f.finding_id)
            if d is not None:
                out.append(d)
    return out


def _vuln_from_detail(d: FindingDetail) -> RawVuln:
    return RawVuln(cve_id=d.cve_id, ecosystem=d.ecosystem, analysis=d.analysis, package=d.package,
                   installed_version=d.installed_version, fixed_versions=[d.fixed_version] if d.fixed_version else [],
                   summary=d.summary, cvss=d.cvss, kev=d.kev, kev_date_added=d.kev_date_added, epss=d.epss,
                   epss_percentile=d.epss_percentile)


# --------------------------------------------------------------------------- helpers

def _load_run(scan_id: str) -> _Run | None:
    with Session(get_engine()) as s:
        row = s.get(ScanRow, scan_id)
        if row is None:
            return None
        return _Run(scan_id=row.id, repo_url=row.repo_url, branch=row.branch, client_name=row.client_name,
                    auto_fix=row.auto_fix, owner_email=row.owner_email)


def _scan_id_of(finding_id: str) -> str | None:
    with Session(get_engine()) as s:
        row = s.get(FindingRow, finding_id)
        return row.scan_id if row else None


def _stats(scan_id: str) -> ScanStats:
    scan = repo.get_scan(scan_id)
    return scan.stats if scan else ScanStats()


def _fail(run: _Run, stage: Stage, message: str) -> None:
    """RISKS E4/E6: scan `failed`, `current_stage` = failing stage, a `failed` event, then `done`."""
    logger.warning("scan failed in stage %s: %s", stage, message)
    try:
        repo.update_scan_stage(run.scan_id, stage, "failed")
    except Exception:  # noqa: BLE001 - the events below must still go out
        logger.exception("could not mark scan failed")
    run.emit(stage, "failed", message)
    bus.publish(ScanEvent(scan_id=run.scan_id, stage="done", status="failed", message=message, progress=1.0,
                          data={"failed_stage": stage}))


def _cleanup(work_id: str) -> None:
    if not work_id:
        return
    try:
        cloner.cleanup(work_id)
    except Exception:  # noqa: BLE001
        logger.exception("workdir cleanup failed")


def rate_window_start() -> str:
    """ISO timestamp one hour ago, for MAX_SCANS_PER_HOUR (RISKS S9)."""
    return iso_z(utcnow() - timedelta(hours=1))

