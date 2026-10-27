"""Persistence functions. Short sessions, one write per transaction (RISKS E8).

Readers return the API schemas from `app.models.schemas`; writers return ids.
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import literal_column
from sqlmodel import Session, SQLModel, col, delete, select

from app.core.db import get_engine
from app.core.ids import iso_z, new_finding_id, new_fix_id, new_scan_id
from app.core.security import redact
from app.models.schemas import (
    Analysis,
    Evidence,
    FindingDetail,
    FindingStatus,
    FindingSummary,
    FixInfo,
    IntegrationEvent,
    IntegrationInfo,
    LanguageInfo,
    Priority,
    Reachability,
    Scan,
    ScanStats,
    ScanStatus,
    TimelineItem,
)
from app.models.tables import FindingRow, FixRow, IntegrationEventRow, ScanRow

ACTIVE_STATUSES = ("queued", "running")


class FindingCreate(BaseModel):
    """Input for `add_finding` (stage 2 output plus later stages' fields, all optional)."""

    cve_id: str
    package: str
    installed_version: str
    ecosystem: str = "PyPI"
    analysis: Analysis = "deep"
    aliases: list[str] = Field(default_factory=list)
    fixed_version: str | None = None
    summary: str = ""
    cvss: float = 5.0
    kev: bool = False
    kev_date_added: str | None = None
    epss: float | None = None
    epss_percentile: float | None = None
    vulnerable_symbols: list[str] = Field(default_factory=list)
    reachability: Reachability = "unsure"
    confidence: float = 0.0
    evidence: list[Evidence] = Field(default_factory=list)
    ai_explanation: str = ""
    score: float = 0.0
    priority: Priority = "P4"
    status: FindingStatus = "open"


# update_finding accepts column names plus these list-valued aliases (serialised to *_json columns).
_JSON_FIELDS = {"aliases": "aliases_json", "vulnerable_symbols": "vulnerable_symbols_json",
                "evidence": "evidence_json", "timeline": "timeline_json"}
_FINDING_FIELDS = set(FindingRow.model_fields) - {"id", "scan_id"} - set(_JSON_FIELDS.values())
_FIX_FIELDS = set(FixRow.model_fields) - {"id", "scan_id"}
_SCAN_FIELDS = {"status", "current_stage", "auto_fix", "owner_email", "finished_at"}


def _dump(value: Any) -> str:
    return json.dumps([v.model_dump() if isinstance(v, BaseModel) else v for v in value])


def _session() -> Session:
    return Session(get_engine())


# --------------------------------------------------------------------------- scans

def create_scan(client_name: str, repo_url: str, branch: str = "main", auto_fix: bool = True,
                owner_email: str = "") -> str:
    scan_id = new_scan_id()
    with _session() as s:
        s.add(ScanRow(id=scan_id, client_name=client_name, repo_url=repo_url, branch=branch, auto_fix=auto_fix,
                      owner_email=owner_email, status="queued", current_stage="clone", started_at=iso_z()))
        s.commit()
    return scan_id


def update_scan_stage(scan_id: str, stage: str, status: ScanStatus | None = None,
                      languages: list[LanguageInfo] | None = None) -> None:
    """Move the scan to `stage`; completed/failed also stamp `finished_at`."""
    with _session() as s:
        row = _must(s, ScanRow, scan_id)
        row.current_stage = stage
        if status is not None:
            row.status = status
            if status in ("completed", "failed"):
                row.finished_at = iso_z()
        if languages is not None:
            row.languages_json = _dump(languages)
        s.add(row)
        s.commit()


def update_scan(scan_id: str, **changes: Any) -> None:
    unknown = set(changes) - _SCAN_FIELDS
    if unknown:
        raise ValueError(f"unknown scan fields: {sorted(unknown)}")
    with _session() as s:
        row = _must(s, ScanRow, scan_id)
        for k, v in changes.items():
            setattr(row, k, v)
        s.add(row)
        s.commit()


def find_active_scan(repo_url: str, branch: str) -> Scan | None:
    """Duplicate-scan guard for POST /api/scans (queued/running scan for the same repo + branch)."""
    with _session() as s:
        row = s.exec(select(ScanRow).where(ScanRow.repo_url == repo_url, ScanRow.branch == branch,
                                           col(ScanRow.status).in_(ACTIVE_STATUSES))
                     .order_by(literal_column("rowid").desc())).first()
        return _scan_schema(s, row) if row else None


def count_scans_since(since_iso: str) -> int:
    with _session() as s:
        return len(s.exec(select(ScanRow.id).where(col(ScanRow.started_at) >= since_iso)).all())


def get_scan(scan_id: str) -> Scan | None:
    with _session() as s:
        row = s.get(ScanRow, scan_id)
        return _scan_schema(s, row) if row else None


def list_scans(client_name: str | None = None, status: ScanStatus | None = None, limit: int = 100) -> list[Scan]:
    """Newest first."""
    stmt = select(ScanRow)
    if client_name:
        stmt = stmt.where(ScanRow.client_name == client_name)
    if status:
        stmt = stmt.where(ScanRow.status == status)
    stmt = stmt.order_by(col(ScanRow.started_at).desc(), literal_column("rowid").desc()).limit(limit)
    with _session() as s:
        return [_scan_schema(s, r) for r in s.exec(stmt).all()]


def _scan_schema(s: Session, row: ScanRow) -> Scan:
    findings = s.exec(select(FindingRow).where(FindingRow.scan_id == row.id)).all()
    reach = Counter(f.reachability for f in findings)
    prio = Counter(f.priority for f in findings)
    fix_ids = {f.fix_id for f in findings if f.fix_id}
    prs = 0
    if fix_ids:
        prs = len(s.exec(select(FixRow.id).where(col(FixRow.id).in_(fix_ids), col(FixRow.pr_url).is_not(None))).all())
    stats = ScanStats(
        total_alerts=len(findings), reachable=reach["reachable"], unsure=reach["unsure"],
        not_reachable=reach["not_reachable"], p1=prio["P1"], p2=prio["P2"],
        fixed=sum(1 for f in findings if f.status == "fixed"), prs_opened=prs,
    )
    return Scan(
        scan_id=row.id, client_name=row.client_name, repo_url=row.repo_url, branch=row.branch,
        status=row.status, current_stage=row.current_stage,  # type: ignore[arg-type]
        started_at=row.started_at, finished_at=row.finished_at,
        languages=[LanguageInfo(**x) for x in json.loads(row.languages_json)], stats=stats,
    )


def _refresh_scan_counts(s: Session, scan_id: str) -> None:
    row = s.get(ScanRow, scan_id)
    if row is None:
        return
    findings = s.exec(select(FindingRow).where(FindingRow.scan_id == scan_id)).all()
    row.total_alerts = len(findings)
    row.reachable_count = sum(1 for f in findings if f.reachability == "reachable")
    row.p1_count = sum(1 for f in findings if f.priority == "P1")
    s.add(row)


# ------------------------------------------------------------------------ findings

def add_finding(scan_id: str, data: FindingCreate) -> str:
    finding_id = new_finding_id()
    with _session() as s:
        _must(s, ScanRow, scan_id)
        s.add(FindingRow(
            id=finding_id, scan_id=scan_id, cve_id=data.cve_id, aliases_json=_dump(data.aliases),
            ecosystem=data.ecosystem, analysis=data.analysis, package=data.package,
            installed_version=data.installed_version, fixed_version=data.fixed_version, summary=data.summary,
            cvss=data.cvss, kev=data.kev, kev_date_added=data.kev_date_added, epss=data.epss,
            epss_percentile=data.epss_percentile, vulnerable_symbols_json=_dump(data.vulnerable_symbols),
            reachability=data.reachability, confidence=data.confidence, evidence_json=_dump(data.evidence),
            ai_explanation=data.ai_explanation, score=data.score, priority=data.priority, status=data.status,
            timeline_json=_dump([{"stage": "scan", "at": iso_z(), "message": "Detected via OSV"}]),
        ))
        s.flush()
        _refresh_scan_counts(s, scan_id)
        s.commit()
    return finding_id


def update_finding(finding_id: str, **changes: Any) -> None:
    """Set any finding column, or `evidence` / `vulnerable_symbols` / `aliases` / `timeline` as Python lists."""
    unknown = set(changes) - _FINDING_FIELDS - set(_JSON_FIELDS)
    if unknown:
        raise ValueError(f"unknown finding fields: {sorted(unknown)}")
    with _session() as s:
        row = _must(s, FindingRow, finding_id)
        for k, v in changes.items():
            if k in _JSON_FIELDS:
                setattr(row, _JSON_FIELDS[k], _dump(v))
            else:
                setattr(row, k, v)
        s.add(row)
        s.flush()
        _refresh_scan_counts(s, row.scan_id)
        s.commit()


def append_timeline(finding_id: str, stage: str, message: str) -> None:
    with _session() as s:
        row = _must(s, FindingRow, finding_id)
        row.timeline_json = _dump([*json.loads(row.timeline_json), {"stage": stage, "at": iso_z(), "message": message}])
        s.add(row)
        s.commit()


def get_finding(finding_id: str) -> FindingDetail | None:
    with _session() as s:
        row = s.get(FindingRow, finding_id)
        return _detail_schema(s, row) if row else None


def list_findings(scan_id: str | None = None, priority: Priority | None = None,
                  reachability: Reachability | None = None, status: FindingStatus | None = None) -> list[FindingSummary]:
    """Highest score first."""
    stmt = select(FindingRow)
    for column, value in ((FindingRow.scan_id, scan_id), (FindingRow.priority, priority),
                          (FindingRow.reachability, reachability), (FindingRow.status, status)):
        if value is not None:
            stmt = stmt.where(column == value)
    stmt = stmt.order_by(col(FindingRow.score).desc(), literal_column("rowid").asc())
    with _session() as s:
        return [_summary_schema(r) for r in s.exec(stmt).all()]


def _summary_schema(r: FindingRow) -> FindingSummary:
    return FindingSummary(
        finding_id=r.id, cve_id=r.cve_id, package=r.package, installed_version=r.installed_version,
        fixed_version=r.fixed_version, cvss=r.cvss, reachability=r.reachability, confidence=r.confidence,  # type: ignore[arg-type]
        score=r.score, priority=r.priority, status=r.status, kev=r.kev, epss=r.epss,  # type: ignore[arg-type]
        epss_percentile=r.epss_percentile, ecosystem=r.ecosystem, analysis=r.analysis,  # type: ignore[arg-type]
    )


def _detail_schema(s: Session, r: FindingRow) -> FindingDetail:
    fix_row = s.get(FixRow, r.fix_id) if r.fix_id else None
    fix = FixInfo(new_version=fix_row.new_version or "", attempts=fix_row.attempts, tests_passed=fix_row.tests_passed,
                  patch_diff=fix_row.patch_diff, pr_url=fix_row.pr_url, status=fix_row.status) if fix_row else None
    has_integration = r.jira_key or r.slack_sent or r.compliance_log_id
    integration = IntegrationInfo(jira_key=r.jira_key, jira_url=r.jira_url, slack_sent=r.slack_sent,
                                  compliance_log_id=r.compliance_log_id) if has_integration else None
    return FindingDetail(
        **_summary_schema(r).model_dump(),
        summary=r.summary, kev_date_added=r.kev_date_added,
        vulnerable_symbols=json.loads(r.vulnerable_symbols_json),
        evidence=[Evidence(**e) for e in json.loads(r.evidence_json)],
        ai_explanation=r.ai_explanation, fix=fix, integration=integration,
        timeline=[TimelineItem(**t) for t in json.loads(r.timeline_json)],
    )


# --------------------------------------------------------------------------- fixes

def add_fix(scan_id: str, package: str, new_version: str | None = None, patch_diff: str = "",
            tests_passed: bool = False, attempts: int = 0, pr_url: str | None = None,
            status: str = "needs_human", finding_ids: list[str] | None = None) -> str:
    """One row per package fix; `finding_ids` are linked to it in the same transaction."""
    fix_id = new_fix_id()
    with _session() as s:
        _must(s, ScanRow, scan_id)
        s.add(FixRow(id=fix_id, scan_id=scan_id, package=package, new_version=new_version, patch_diff=patch_diff,
                     tests_passed=tests_passed, attempts=attempts, pr_url=pr_url, status=status))
        for fid in finding_ids or []:
            row = _must(s, FindingRow, fid)
            row.fix_id = fix_id
            s.add(row)
        s.commit()
    return fix_id


def update_fix(fix_id: str, **changes: Any) -> None:
    unknown = set(changes) - _FIX_FIELDS
    if unknown:
        raise ValueError(f"unknown fix fields: {sorted(unknown)}")
    with _session() as s:
        row = _must(s, FixRow, fix_id)
        for k, v in changes.items():
            setattr(row, k, v)
        s.add(row)
        s.commit()


# ------------------------------------------------------------ integration events

def add_integration_event(process: str, endpoint: str, ok: bool, finding_id: str | None = None,
                          direction: str = "out", request: Any = None, response: Any = None,
                          status_code: int | None = None, summary: str = "") -> int:
    """Payloads are redacted (RISKS S4) before they are stored."""
    with _session() as s:
        row = IntegrationEventRow(
            finding_id=finding_id, process=process, direction=direction, endpoint=endpoint,
            request_json=redact(json.dumps(request)) if request is not None else "",
            response_json=redact(json.dumps(response)) if response is not None else "",
            status_code=status_code, ok=ok, summary=redact(summary), created_at=iso_z(),
        )
        s.add(row)
        s.commit()
        s.refresh(row)
        assert row.id is not None
        return row.id


def list_integration_events(limit: int = 50, finding_id: str | None = None) -> list[IntegrationEvent]:
    """Newest first."""
    stmt = select(IntegrationEventRow)
    if finding_id:
        stmt = stmt.where(IntegrationEventRow.finding_id == finding_id)
    stmt = stmt.order_by(col(IntegrationEventRow.id).desc()).limit(limit)
    with _session() as s:
        return [IntegrationEvent(id=r.id or 0, finding_id=r.finding_id, process=r.process,  # type: ignore[arg-type]
                                 endpoint=r.endpoint, status_code=r.status_code, ok=r.ok, summary=r.summary,
                                 created_at=r.created_at) for r in s.exec(stmt).all()]


# ---------------------------------------------------------------------------- misc

def clear_all() -> None:
    """POST /api/demo/reset: empty every table."""
    with _session() as s:
        for table in (IntegrationEventRow, FindingRow, FixRow, ScanRow):
            s.exec(delete(table))  # type: ignore[call-overload]
        s.commit()


def _must(s: Session, model: type[SQLModel], pk: str) -> Any:
    row = s.get(model, pk)
    if row is None:
        raise LookupError(f"{model.__name__} {pk} not found")
    return row
