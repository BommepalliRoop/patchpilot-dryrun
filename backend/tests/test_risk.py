"""T07 — risk scorer. Formula: docs/ARCHITECTURE.md "Risk score"."""
from __future__ import annotations

import math

import pytest

from app.models.schemas import Evidence
from app.services import risk


def _ev(in_route: bool) -> list[Evidence]:
    return [Evidence(file="app.py", line=10, in_route=in_route)]


NO_EVIDENCE: list[Evidence] = []


@pytest.mark.parametrize(
    ("cvss", "expected_score", "expected_priority"),
    [
        (9.0, 9.0, "P1"),   # P1 lower boundary
        (8.9, 8.9, "P2"),   # just below P1
        (7.0, 7.0, "P2"),   # P2 lower boundary
        (6.9, 6.9, "P3"),   # just below P2
        (4.0, 4.0, "P3"),   # P3 lower boundary
        (3.9, 3.9, "P4"),   # just below P3
        (0.0, 0.0, "P4"),
        (10.0, 10.0, "P1"),
    ],
)
def test_priority_boundaries(cvss: float, expected_score: float, expected_priority: str) -> None:
    assert risk.score(cvss, "reachable", NO_EVIDENCE, False, None) == (expected_score, expected_priority)


@pytest.mark.parametrize(
    ("reachability", "cvss", "expected"),
    [
        ("reachable", 10.0, (10.0, "P1")),
        ("unsure", 10.0, (6.0, "P3")),        # 10 x 0.6
        ("not_reachable", 10.0, (3.0, "P4")),  # 10 x 0.3
    ],
)
def test_reachability_weight(reachability: str, cvss: float, expected: tuple[float, str]) -> None:
    assert risk.score(cvss, reachability, NO_EVIDENCE, False, None) == expected


def test_in_route_exposure_boost() -> None:
    # 6.0 x 1.5 = 9.0 -> P1 only because of the route exposure
    assert risk.score(6.0, "reachable", _ev(in_route=True), False, None) == (9.0, "P1")
    assert risk.score(6.0, "reachable", _ev(in_route=False), False, None) == (6.0, "P3")


def test_kev_boost() -> None:
    assert risk.score(5.0, "reachable", NO_EVIDENCE, True, None) == (6.5, "P3")  # 5 x 1.3
    assert risk.score(5.0, "reachable", NO_EVIDENCE, False, None) == (5.0, "P3")


@pytest.mark.parametrize(
    ("epss_percentile", "expected_score"),
    [
        (0.95, 5.5),   # >= 0.9 -> 5 x 1.1
        (0.9, 5.5),    # exact boundary is inclusive
        (0.89, 5.0),   # just below
        (0.0, 5.0),
        (None, 5.0),   # missing EPSS -> no boost
    ],
)
def test_epss_boost(epss_percentile: float | None, expected_score: float) -> None:
    assert risk.score(5.0, "reachable", NO_EVIDENCE, False, epss_percentile) == (expected_score, "P3")


def test_kev_takes_precedence_over_epss() -> None:
    # KEV weight 1.3 applies, not 1.3 x 1.1
    assert risk.score(5.0, "reachable", NO_EVIDENCE, True, 0.99) == (6.5, "P3")


def test_not_reachable_plus_kev_stays_p4() -> None:
    # max 10 x 0.3 x 1.3 = 3.9 -> P4 even when actively exploited
    assert risk.score(10.0, "not_reachable", NO_EVIDENCE, True, 0.99) == (3.9, "P4")


def test_score_capped_at_ten() -> None:
    # 9.5 x 1.5 x 1.3 = 18.525 -> capped at 10
    assert risk.score(9.5, "reachable", _ev(in_route=True), True, None) == (10.0, "P1")


@pytest.mark.parametrize("cvss", [-0.1, 10.1, math.nan])
def test_cvss_out_of_range_rejected(cvss: float) -> None:
    with pytest.raises(ValueError):
        risk.score(cvss, "reachable", NO_EVIDENCE, False, None)
