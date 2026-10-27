"""Seed the DB from the contracts/api example files."""
from __future__ import annotations

import json

from app.core.config import REPO_ROOT
from app.models import repository as repo
from app.models.schemas import Evidence, LanguageInfo


def contract(name: str) -> dict:
    return json.loads((REPO_ROOT / "contracts" / name).read_text(encoding="utf-8"))


def seed_contract_scan() -> tuple[str, str]:
    """One scan with the contract finding (fixed, with PR and Boomi result). Returns (scan_id, finding_id)."""
    scan = contract("api/scan.json")
    d = contract("api/finding_detail.json")
    scan_id = repo.create_scan(scan["client_name"], scan["repo_url"], scan["branch"])
    repo.update_scan_stage(scan_id, "done", "completed", [LanguageInfo(**x) for x in scan["languages"]])
    finding_id = repo.add_finding(scan_id, repo.FindingCreate(
        cve_id=d["cve_id"], package=d["package"], installed_version=d["installed_version"],
        fixed_version=d["fixed_version"], cvss=d["cvss"], reachability=d["reachability"],
        confidence=d["confidence"], score=d["score"], priority=d["priority"], status=d["status"],
        kev=d["kev"], epss=d["epss"], epss_percentile=d["epss_percentile"], ecosystem=d["ecosystem"],
        analysis=d["analysis"], summary=d["summary"], kev_date_added=d["kev_date_added"],
        vulnerable_symbols=d["vulnerable_symbols"], evidence=[Evidence(**e) for e in d["evidence"]],
        ai_explanation=d["ai_explanation"],
    ))
    fx = d["fix"]
    repo.add_fix(scan_id, d["package"], fx["new_version"], fx["patch_diff"], fx["tests_passed"], fx["attempts"],
                 fx["pr_url"], fx["status"], finding_ids=[finding_id])
    repo.update_finding(finding_id, timeline=d["timeline"], **d["integration"])
    return scan_id, finding_id


def seed_extra_findings(scan_id: str) -> None:
    repo.add_finding(scan_id, repo.FindingCreate(
        cve_id="CVE-2023-32681", package="requests", installed_version="2.25.1", fixed_version="2.31.0", cvss=6.1,
        reachability="not_reachable", confidence=0.9, score=1.8, priority="P4"))
    repo.add_finding(scan_id, repo.FindingCreate(
        cve_id="CVE-2024-22195", package="jinja2", installed_version="2.11.3", fixed_version="3.1.3", cvss=5.4,
        reachability="unsure", confidence=0.55, score=3.2, priority="P4"))
