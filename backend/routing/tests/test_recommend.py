"""
Route recommendation order from the PDF:

    1. Fewest Severe miles
    2. Fewest High miles
    3. Lowest average risk
    4. Shortest travel time

No Travel sits above Severe in the PDF's scale, so routes are first ordered by
fewest No Travel miles, and a route containing any No Travel checkpoint is
never recommended. Miles are compared at 0.1-mile precision and average risk
at 0.01 so that floating-point noise does not decide between routes.
"""

import pytest

from routing.aggregate import RouteRiskSummary
from routing.recommend import RouteCandidate, rank_routes, recommend
from routing.risk import Level


def summary(no_travel=0.0, severe=0.0, high=0.0, moderate=0.0, low=0.0) -> RouteRiskSummary:
    miles = {
        Level.NO_TRAVEL: no_travel,
        Level.SEVERE: severe,
        Level.HIGH: high,
        Level.MODERATE: moderate,
        Level.LOW: low,
    }
    total = sum(miles.values())
    avg = sum(lvl.value * m for lvl, m in miles.items()) / total if total else 0.0
    worst = max((lvl for lvl, m in miles.items() if m > 0), default=Level.LOW)
    return RouteRiskSummary(
        miles_by_level=miles,
        total_miles=total,
        average_risk=avg,
        no_travel=no_travel > 0,
        worst_level=worst,
        worst_checkpoint_index=0,
    )


def cand(route_id, travel_seconds=36_000, **miles) -> RouteCandidate:
    return RouteCandidate(route_id=route_id, summary=summary(**miles), travel_seconds=travel_seconds)


def test_fewest_severe_miles_wins_even_if_much_slower():
    a = cand("a", travel_seconds=50_000, high=100, low=900)
    b = cand("b", travel_seconds=20_000, severe=5, low=995)
    assert [c.route_id for c in rank_routes([b, a])] == ["a", "b"]


def test_tie_on_severe_then_fewest_high_miles():
    a = cand("a", severe=10, high=20, low=970)
    b = cand("b", severe=10, high=5, low=985)
    assert [c.route_id for c in rank_routes([a, b])] == ["b", "a"]


def test_tie_on_severe_and_high_then_lowest_average_risk():
    a = cand("a", severe=10, high=10, moderate=50)  # avg 1.43
    b = cand("b", severe=10, high=10, low=50)  # avg 0.71
    assert [c.route_id for c in rank_routes([a, b])] == ["b", "a"]


def test_tie_on_all_risk_then_shortest_travel_time():
    a = cand("a", travel_seconds=36_000, low=100)
    b = cand("b", travel_seconds=30_000, low=100)
    assert [c.route_id for c in rank_routes([a, b])] == ["b", "a"]


def test_route_with_no_travel_miles_ranks_last_even_with_zero_severe_miles():
    a = cand("a", travel_seconds=10_000, no_travel=1, low=999)
    b = cand("b", travel_seconds=60_000, severe=50, low=950)
    assert [c.route_id for c in rank_routes([a, b])] == ["b", "a"]


def test_near_tie_in_severe_miles_falls_through_to_high_miles():
    a = cand("a", severe=10.04, high=0, low=990)
    b = cand("b", severe=10.0, high=20, low=970)
    assert [c.route_id for c in rank_routes([a, b])] == ["a", "b"]


def test_ranking_is_stable_for_identical_routes():
    a = cand("a", low=100)
    b = cand("b", low=100)
    assert [c.route_id for c in rank_routes([a, b])] == ["a", "b"]
    assert [c.route_id for c in rank_routes([b, a])] == ["b", "a"]


def test_recommend_returns_best_route_and_ranking():
    a = cand("a", severe=5, low=995)
    b = cand("b", high=20, low=980)
    rec = recommend([a, b])
    assert rec.route_id == "b"
    assert rec.ranked_ids == ["b", "a"]
    assert rec.all_no_travel is False


def test_recommend_reason_names_the_deciding_criterion():
    assert "Severe" in recommend([cand("a", severe=5, low=995), cand("b", low=1000)]).reason
    assert "High" in recommend([cand("a", high=5, low=995), cand("b", low=1000)]).reason
    assert "average risk" in recommend([cand("a", moderate=100), cand("b", low=100)]).reason
    assert "travel time" in recommend([cand("a", 40_000, low=100), cand("b", 30_000, low=100)]).reason


def test_recommend_single_route():
    rec = recommend([cand("only", low=100)])
    assert rec.route_id == "only"
    assert "only" in rec.reason.lower()


def test_recommend_none_when_every_route_has_no_travel_conditions():
    a = cand("a", no_travel=30, low=970)
    b = cand("b", no_travel=5, low=995)
    rec = recommend([a, b])
    assert rec.route_id is None
    assert rec.all_no_travel is True
    assert rec.ranked_ids == ["b", "a"]
    assert "No Travel" in rec.reason


def test_recommend_skips_no_travel_routes_when_a_safe_route_exists():
    a = cand("a", no_travel=1, low=999)
    b = cand("b", severe=50, low=950)
    rec = recommend([a, b])
    assert rec.route_id == "b"
    assert "No Travel" in rec.reason


def test_recommend_rejects_empty_input():
    with pytest.raises(ValueError):
        recommend([])
