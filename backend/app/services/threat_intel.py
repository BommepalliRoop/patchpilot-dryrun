"""Stage 2b — CISA KEV + FIRST EPSS enrichment (T02). Feed failures never fail the scan (RISKS N12)."""
from __future__ import annotations

from app.models.domain import RawVuln


async def enrich(vulns: list[RawVuln]) -> list[RawVuln]:
    """Set `kev`, `kev_date_added`, `epss`, `epss_percentile` on every vuln.

    `THREAT_INTEL=live|mock|off`. Feed down -> `kev=False`, `epss=None`.
    """
    raise NotImplementedError("T02")
