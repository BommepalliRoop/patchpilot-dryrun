"""Static fixture data for the T00 stub routers (mirrors contracts/ examples).

T01 replaces the reads with real DB queries; T03 replaces the scan stub. Nothing here is used in production paths.
"""
from __future__ import annotations

from app.core.events import ScanEvent
from app.models.schemas import (
    ComplianceItem,
    ComplianceReport,
    Evidence,
    FindingDetail,
    FindingSummary,
    FixInfo,
    IntegrationEvent,
    IntegrationInfo,
    LanguageInfo,
    Scan,
    ScanStats,
    TimelineItem,
)

SCAN_ID = "scn_01"

SCANS: list[Scan] = [
    Scan(
        scan_id=SCAN_ID,
        client_name="Acme Retail",
        repo_url="https://github.com/BommepalliRoop/demo-target",
        branch="main",
        status="completed",
        current_stage="done",
        started_at="2026-10-28T05:10:00Z",
        finished_at="2026-10-28T05:11:42Z",
        languages=[LanguageInfo(ecosystem="PyPI", manifests=["requirements.txt"], analysis="deep")],
        stats=ScanStats(total_alerts=12, reachable=2, unsure=1, not_reachable=9, p1=1, p2=1, fixed=2, prs_opened=2),
    )
]

_PYYAML = dict(
    cve_id="CVE-2020-14343", package="pyyaml", installed_version="5.3.1", fixed_version="5.4.1", cvss=9.8,
    reachability="reachable", confidence=0.93, score=10.0, priority="P1", status="fixed",
    kev=False, epss=0.0598, epss_percentile=0.9326, ecosystem="PyPI", analysis="deep",
)

FINDINGS: list[FindingSummary] = [
    FindingSummary(finding_id="fnd_07", **_PYYAML),
    FindingSummary(
        finding_id="fnd_08", cve_id="CVE-2023-32681", package="requests", installed_version="2.25.1",
        fixed_version="2.31.0", cvss=6.1, reachability="not_reachable", confidence=0.9, score=1.8, priority="P4",
        status="open", kev=False, epss=0.0021, epss_percentile=0.58, ecosystem="PyPI", analysis="deep",
    ),
    FindingSummary(
        finding_id="fnd_09", cve_id="CVE-2024-22195", package="jinja2", installed_version="2.11.3",
        fixed_version="3.1.3", cvss=5.4, reachability="unsure", confidence=0.55, score=3.2, priority="P4",
        status="open", kev=False, epss=0.0035, epss_percentile=0.67, ecosystem="PyPI", analysis="deep",
    ),
]

FINDING_DETAIL = FindingDetail(
    **_PYYAML,
    finding_id="fnd_07",
    summary="Arbitrary code execution via full_load / FullLoader",
    kev_date_added=None,
    vulnerable_symbols=["yaml.load", "yaml.full_load"],
    evidence=[Evidence(
        file="app/routes.py", line=42, in_route=True, start_line=27,
        code_snippet="@app.route('/import', methods=['POST'])\ndef import_config():\n"
                     "    data = yaml.load(request.data, Loader=yaml.FullLoader)\n    return jsonify(data)\n",
    )],
    ai_explanation="User-supplied YAML from POST /import reaches yaml.load without SafeLoader.",
    fix=FixInfo(new_version="5.4.1", attempts=1, tests_passed=True,
                patch_diff="--- a/requirements.txt\n+++ b/requirements.txt\n@@ -1 +1 @@\n-PyYAML==5.3.1\n+PyYAML==5.4.1\n",
                pr_url="https://github.com/BommepalliRoop/demo-target/pull/3", status="fixed"),
    integration=IntegrationInfo(jira_key="SEC-101", jira_url="https://example.atlassian.net/browse/SEC-101",
                                slack_sent=True, compliance_log_id="log_fnd_07"),
    timeline=[TimelineItem(stage="scan", at="2026-10-28T05:10:05Z", message="Detected via OSV")],
)

INTEGRATION_EVENTS: list[IntegrationEvent] = [
    IntegrationEvent(id=1, finding_id="fnd_07", process="B2", endpoint="/patchpilot/findings", status_code=200,
                     ok=True, summary="Jira SEC-101 created, Slack sent", created_at="2026-10-28T05:11:40Z"),
]

COMPLIANCE = ComplianceReport(
    client_name="Acme Retail",
    **{"from": "2026-10-01"},
    items=[ComplianceItem(
        compliance_log_id="log_fnd_07", cve_id="CVE-2020-14343", package="pyyaml", priority="P1",
        detected_at="2026-10-28T05:10:05Z", fixed_at="2026-10-28T05:11:40Z", time_to_fix_minutes=2,
        jira_key="SEC-101", pr_url="https://github.com/BommepalliRoop/demo-target/pull/3", status="fixed",
    )],
)

_STAGES = ["clone", "scan", "symbols", "reachability", "risk", "fix", "pr", "notify"]


def canned_events(scan_id: str) -> list[ScanEvent]:
    """A short, realistic event stream so the live view can be built before T03 exists."""
    events = [
        ScanEvent(scan_id=scan_id, stage=stage, status="running",  # type: ignore[arg-type]
                  message=f"Stage {stage} (fixture)", progress=round((i + 1) / (len(_STAGES) + 1), 2))
        for i, stage in enumerate(_STAGES)
    ]
    events.append(ScanEvent(scan_id=scan_id, stage="done", status="completed", message="Scan complete", progress=1.0))
    return events
