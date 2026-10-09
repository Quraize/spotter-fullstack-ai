"""
Route-level aggregation of checkpoint risk levels.

Each stretch between two consecutive checkpoints is rated at the worse of its
two endpoints (conservative and easy to explain). The miles at each level are
the summed stretch lengths. Average risk is the distance-weighted mean of the
level values (Low 0 ... No Travel 4).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from .risk import Level


@dataclass(frozen=True)
class RouteRiskSummary:
    miles_by_level: dict[Level, float]  # every Level present, missing ones are 0.0
    total_miles: float
    average_risk: float  # 0.0 (all Low) to 4.0 (all No Travel)
    no_travel: bool  # any checkpoint classified No Travel
    worst_level: Level
    worst_checkpoint_index: int  # first checkpoint at worst_level

    @property
    def no_travel_miles(self) -> float:
        return self.miles_by_level[Level.NO_TRAVEL]

    @property
    def severe_miles(self) -> float:
        return self.miles_by_level[Level.SEVERE]

    @property
    def high_miles(self) -> float:
        return self.miles_by_level[Level.HIGH]


def summarize(checkpoint_miles: Sequence[float], levels: Sequence[Level]) -> RouteRiskSummary:
    """
    checkpoint_miles: distance of each checkpoint from the origin, non-decreasing.
    levels: the overall risk level at each checkpoint.
    """
    if not checkpoint_miles:
        raise ValueError("at least one checkpoint is required")
    if len(checkpoint_miles) != len(levels):
        raise ValueError("checkpoint_miles and levels must have the same length")
    for earlier, later in pairwise(checkpoint_miles):
        if later < earlier:
            raise ValueError("checkpoint_miles must be non-decreasing")

    miles_by_level = {level: 0.0 for level in Level}
    weighted_sum = 0.0
    for i in range(len(checkpoint_miles) - 1):
        length = checkpoint_miles[i + 1] - checkpoint_miles[i]
        stretch_level = max(levels[i], levels[i + 1])
        miles_by_level[stretch_level] += length
        weighted_sum += stretch_level.value * length

    total_miles = checkpoint_miles[-1] - checkpoint_miles[0]
    worst_level = max(levels)
    worst_index = next(i for i, level in enumerate(levels) if level is worst_level)
    average_risk = weighted_sum / total_miles if total_miles > 0 else float(worst_level.value)

    return RouteRiskSummary(
        miles_by_level=miles_by_level,
        total_miles=total_miles,
        average_risk=average_risk,
        no_travel=Level.NO_TRAVEL in levels,
        worst_level=worst_level,
        worst_checkpoint_index=worst_index,
    )
