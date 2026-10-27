"""Stage 5 — risk score (T07). Pure function; formula in docs/ARCHITECTURE.md "Risk score"."""
from __future__ import annotations

from app.models.schemas import Evidence, Priority, Reachability


def score(
    cvss: float,
    reachability: Reachability,
    evidence: list[Evidence],
    kev: bool,
    epss_percentile: float | None,
) -> tuple[float, Priority]:
    """`min(10, cvss * reach_w * exposure_w * threat_w)` and its P1-P4 bucket.

    Raises ValueError if `cvss` is outside 0-10.
    """
    raise NotImplementedError("T07")
