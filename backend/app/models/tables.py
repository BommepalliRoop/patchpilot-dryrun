"""SQLModel tables (docs/ARCHITECTURE.md "Data model"). Timestamps are stored as ISO-8601 `Z` strings (L10)."""
from __future__ import annotations

from sqlmodel import Field, SQLModel


class ScanRow(SQLModel, table=True):
    __tablename__ = "scans"

    id: str = Field(primary_key=True)
    client_name: str
    repo_url: str = Field(index=True)
    branch: str = "main"
    auto_fix: bool = True
    owner_email: str = ""
    languages_json: str = "[]"
    status: str = "queued"
    current_stage: str = "clone"
    started_at: str | None = None
    finished_at: str | None = None
    total_alerts: int = 0
    reachable_count: int = 0
    p1_count: int = 0


class FixRow(SQLModel, table=True):
    """One row per package fix; findings point to it via fix_id."""

    __tablename__ = "fixes"

    id: str = Field(primary_key=True)
    scan_id: str = Field(index=True)
    package: str
    new_version: str | None = None
    patch_diff: str = ""
    tests_passed: bool = False
    attempts: int = 0
    pr_url: str | None = None
    status: str = "needs_human"


class FindingRow(SQLModel, table=True):
    __tablename__ = "findings"

    id: str = Field(primary_key=True)
    scan_id: str = Field(index=True)
    cve_id: str
    aliases_json: str = "[]"
    ecosystem: str = "PyPI"
    analysis: str = "deep"
    package: str
    installed_version: str
    fixed_version: str | None = None
    summary: str = ""
    cvss: float = 5.0
    kev: bool = False
    kev_date_added: str | None = None
    epss: float | None = None
    epss_percentile: float | None = None
    vulnerable_symbols_json: str = "[]"
    reachability: str = "unsure"
    confidence: float = 0.0
    evidence_json: str = "[]"
    ai_explanation: str = ""
    score: float = 0.0
    priority: str = "P4"
    status: str = "open"
    fix_id: str | None = None
    jira_key: str | None = None
    jira_url: str | None = None
    slack_sent: bool = False
    compliance_log_id: str | None = None
    timeline_json: str = "[]"


class SymbolCacheRow(SQLModel, table=True):
    """T05: extracted vulnerable symbols, cached per advisory so a re-scan costs no LLM call."""

    __tablename__ = "symbol_cache"

    key: str = Field(primary_key=True)  # "<cve_id>|<ecosystem>|<normalised package>"
    result_json: str
    created_at: str


class IntegrationEventRow(SQLModel, table=True):
    __tablename__ = "integration_events"

    id: int | None = Field(default=None, primary_key=True)
    finding_id: str | None = Field(default=None, index=True)
    process: str  # B1..B4
    direction: str = "out"  # out = PatchPilot -> Boomi, in = Boomi -> PatchPilot
    endpoint: str
    request_json: str = ""
    response_json: str = ""
    status_code: int | None = None
    ok: bool = False
    summary: str = ""
    created_at: str
