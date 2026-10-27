"""API schemas — field names, types and enums identical to docs/API_CONTRACTS.md Part A.

T00 ships the minimum the stub routers need. T01 owns this file from here on and may extend it.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ScanStatus = Literal["queued", "running", "completed", "failed"]
Reachability = Literal["reachable", "not_reachable", "unsure"]
Priority = Literal["P1", "P2", "P3", "P4"]
FindingStatus = Literal["open", "fixing", "fixed", "needs_human", "ignored"]
Analysis = Literal["deep", "generic"]
FixStatus = Literal["fixed", "needs_human"]

BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,100}$")  # RISKS S3


class ScanCreate(BaseModel):
    client_name: str = Field(min_length=1, max_length=200)
    repo_url: str
    branch: str = "main"
    auto_fix: bool = True
    owner_email: str = ""

    @field_validator("repo_url")
    @classmethod
    def _https_only(cls, v: str) -> str:
        if not v.startswith("https://") or any(c in v for c in " \t\r\n"):
            raise ValueError("must be an https:// URL")
        return v

    @field_validator("branch")
    @classmethod
    def _safe_branch(cls, v: str) -> str:
        if v.startswith("-") or not BRANCH_RE.match(v):
            raise ValueError("invalid branch name")
        return v


class ScanCreated(BaseModel):
    scan_id: str
    status: ScanStatus


class LanguageInfo(BaseModel):
    ecosystem: str
    manifests: list[str]
    analysis: Analysis


class ScanStats(BaseModel):
    total_alerts: int = 0
    reachable: int = 0
    unsure: int = 0
    not_reachable: int = 0
    p1: int = 0
    p2: int = 0
    fixed: int = 0
    prs_opened: int = 0


class Scan(BaseModel):
    scan_id: str
    client_name: str
    repo_url: str
    branch: str
    status: ScanStatus
    current_stage: str
    started_at: str | None = None
    finished_at: str | None = None
    languages: list[LanguageInfo] = Field(default_factory=list)
    stats: ScanStats = Field(default_factory=ScanStats)


class FindingSummary(BaseModel):
    finding_id: str
    cve_id: str
    package: str
    installed_version: str
    fixed_version: str | None = None
    cvss: float
    reachability: Reachability
    confidence: float
    score: float
    priority: Priority
    status: FindingStatus
    kev: bool = False
    epss: float | None = None
    epss_percentile: float | None = None
    ecosystem: str
    analysis: Analysis


class Evidence(BaseModel):
    file: str
    line: int
    in_route: bool
    code_snippet: str = ""
    start_line: int = 1


class FixInfo(BaseModel):
    new_version: str
    attempts: int
    tests_passed: bool
    patch_diff: str = ""
    pr_url: str | None = None
    status: str


class IntegrationInfo(BaseModel):
    jira_key: str | None = None
    jira_url: str | None = None
    slack_sent: bool = False
    compliance_log_id: str | None = None


class TimelineItem(BaseModel):
    stage: str
    at: str
    message: str


class FindingDetail(FindingSummary):
    summary: str = ""
    kev_date_added: str | None = None
    vulnerable_symbols: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    ai_explanation: str = ""
    fix: FixInfo | None = None
    integration: IntegrationInfo | None = None
    timeline: list[TimelineItem] = Field(default_factory=list)


class FixStarted(BaseModel):
    finding_id: str
    status: FindingStatus


class IntegrationEvent(BaseModel):
    id: int
    finding_id: str | None = None
    process: Literal["B1", "B2", "B3", "B4"]
    endpoint: str
    status_code: int | None = None
    ok: bool
    summary: str = ""
    created_at: str


class ComplianceItem(BaseModel):
    compliance_log_id: str
    cve_id: str
    package: str
    priority: Priority
    detected_at: str
    fixed_at: str | None = None
    time_to_fix_minutes: int | None = None
    jira_key: str | None = None
    pr_url: str | None = None
    status: str


class ComplianceReport(BaseModel):
    client_name: str
    from_: str = Field(alias="from")
    items: list[ComplianceItem]

    model_config = {"populate_by_name": True}


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    llm_mode: str
    boomi_mode: str
    github_mode: str


class Ok(BaseModel):
    ok: bool = True


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody
