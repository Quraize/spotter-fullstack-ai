"""
Route recommendation.

PDF preference order:
    1. Fewest Severe miles
    2. Fewest High miles
    3. Lowest average risk
    4. Shortest travel time

No Travel is the top of the PDF's risk scale, so routes are compared first on
No Travel miles, then on the four PDF criteria. A route that contains any
No Travel checkpoint is never recommended; if every route does, no route is
recommended and the ranking only indicates the least affected one.

Miles are compared at 0.1-mile precision and average risk at 0.01 so that
floating-point noise never decides between routes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .aggregate import RouteRiskSummary

MILES_DECIMALS = 1
RISK_DECIMALS = 2


@dataclass(frozen=True)
class RouteCandidate:
    route_id: str
    summary: RouteRiskSummary
    travel_seconds: float


@dataclass(frozen=True)
class Recommendation:
    route_id: str | None  # None when every route has No Travel conditions
    ranked_ids: list[str]  # best first
    reason: str
    all_no_travel: bool


def sort_key(candidate: RouteCandidate) -> tuple[float, float, float, float, float]:
    s = candidate.summary
    return (
        round(s.no_travel_miles, MILES_DECIMALS),
        round(s.severe_miles, MILES_DECIMALS),
        round(s.high_miles, MILES_DECIMALS),
        round(s.average_risk, RISK_DECIMALS),
        candidate.travel_seconds,
    )


def rank_routes(candidates: Sequence[RouteCandidate]) -> list[RouteCandidate]:
    """Best route first. Stable, so equal routes keep the provider's order."""
    return sorted(candidates, key=sort_key)


def recommend(candidates: Sequence[RouteCandidate]) -> Recommendation:
    if not candidates:
        raise ValueError("at least one route candidate is required")
    ranked = rank_routes(candidates)
    ranked_ids = [c.route_id for c in ranked]
    best = ranked[0]

    if all(c.summary.no_travel for c in ranked):
        reason = (
            "All routes cross No Travel conditions, so none is recommended. "
            f"Route {best.route_id} is least affected with "
            f"{best.summary.no_travel_miles:.1f} No Travel miles."
        )
        return Recommendation(route_id=None, ranked_ids=ranked_ids, reason=reason, all_no_travel=True)

    if len(ranked) == 1:
        return Recommendation(
            route_id=best.route_id, ranked_ids=ranked_ids, reason="Only route available.", all_no_travel=False
        )

    reason = _deciding_reason(best, ranked[1])
    excluded = sum(1 for c in ranked if c.summary.no_travel)
    if excluded:
        plural = "route" if excluded == 1 else "routes"
        reason += f" {excluded} {plural} not recommended because of No Travel conditions."
    return Recommendation(route_id=best.route_id, ranked_ids=ranked_ids, reason=reason, all_no_travel=False)


def _deciding_reason(best: RouteCandidate, runner_up: RouteCandidate) -> str:
    best_key, other_key = sort_key(best), sort_key(runner_up)
    labels = ("No Travel miles", "Severe miles", "High miles")
    for i, (mine, theirs) in enumerate(zip(best_key, other_key, strict=True)):
        if mine == theirs:
            continue
        if i < 3:
            return f"Fewest {labels[i]}: {mine:.1f} vs {theirs:.1f} on the next best route."
        if i == 3:
            return f"Lowest average risk: {mine:.2f} vs {theirs:.2f} on the next best route."
        return f"Shortest travel time: {_format_duration(mine)} vs {_format_duration(theirs)} on the next best route."
    return "Tied with the next best route on every criterion; listed first by the routing provider."


def _format_duration(seconds: float) -> str:
    minutes = round(seconds / 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"
