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
    if not 0 <= cvss <= 10:  # also rejects NaN
        raise ValueError(f"cvss must be within 0-10, got {cvss!r}")
    reach_w = {"reachable": 1.0, "unsure": 0.6}.get(reachability, 0.3)
    exposure_w = 1.5 if any(e.in_route for e in evidence) else 1.0
    if kev:
        threat_w = 1.3
    elif epss_percentile is not None and epss_percentile >= 0.9:
        threat_w = 1.1
    else:
        threat_w = 1.0
    value = round(min(10.0, cvss * reach_w * exposure_w * threat_w), 1)
    return value, _bucket(value)


def _bucket(value: float) -> Priority:
    if value >= 9:
        return "P1"
    if value >= 7:
        return "P2"
    if value >= 4:
        return "P3"
    return "P4"
