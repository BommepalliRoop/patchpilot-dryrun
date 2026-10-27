"""Types passed between pipeline stages (docs/ARCHITECTURE.md "Pipeline stages").

Service modules import these; the HTTP layer uses `app.models.schemas`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.models.schemas import Analysis, Evidence, Priority, Reachability


class RawVuln(BaseModel):
    """One vulnerable dependency as reported by OSV (stage 2), enriched with threat intel."""

    cve_id: str  # best id available: CVE > GHSA > PYSEC (RISKS L4)
    aliases: list[str] = Field(default_factory=list)
    ecosystem: str  # OSV name: PyPI, npm, Maven, ...
    analysis: Analysis = "generic"
    package: str
    installed_version: str
    fixed_versions: list[str] = Field(default_factory=list)
    summary: str = ""
    details: str = ""
    references: list[str] = Field(default_factory=list)
    cvss: float = 5.0
    cvss_estimated: bool = False
    manifest: str = ""
    kev: bool = False
    kev_date_added: str | None = None
    epss: float | None = None
    epss_percentile: float | None = None
    threat_feed_unavailable: bool = False  # set by threat_intel when a feed was down (pipeline adds a timeline note)


class VulnSymbols(BaseModel):
    """Stage 3 output: which functions of the package are dangerous."""

    package: str
    import_names: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)  # fully-qualified, e.g. "yaml.load"
    safe_usage_notes: str = ""
    confidence: float = 0.5


class Verdict(BaseModel):
    """Stage 4 output."""

    reachable: Reachability
    confidence: float
    evidence: list[Evidence] = Field(default_factory=list)
    explanation: str = ""
    analysis: Analysis = "deep"


class FixResult(BaseModel):
    """Stage 6 output — one per package."""

    package: str
    new_version: str | None = None
    patch_diff: str = ""
    tests_passed: bool = False
    attempts: int = 0
    branch: str = ""
    work_dir: Path | None = None
    status: Literal["fixed", "fixed_untested", "needs_human"] = "needs_human"
    reason: str = ""  # e.g. no_tests, install_failed, no_fix_available, unsupported_manifest


Score = tuple[float, Priority]


class B2Response(BaseModel):
    """contracts/boomi/B2_finding_response.json"""

    ok: bool
    jira_key: str | None = None
    jira_url: str | None = None
    slack_sent: bool = False
    compliance_log_id: str | None = None
    processed_at: str | None = None
    error: str | None = None
    message: str | None = None


class B3Response(BaseModel):
    ok: bool
    slack_sent: bool = False
