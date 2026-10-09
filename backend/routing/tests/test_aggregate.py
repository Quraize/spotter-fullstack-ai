"""
Route-level aggregation of checkpoint risk.

Each stretch between two consecutive checkpoints is rated at the worse of its
two endpoints. "Severe miles" is the total length of stretches rated Severe,
and so on for every level. Average risk is the distance-weighted mean of the
level values (Low 0 ... No Travel 4).
"""

import pytest

from routing.aggregate import summarize
from routing.risk import Level

L, M, H, S, N = Level.LOW, Level.MODERATE, Level.HIGH, Level.SEVERE, Level.NO_TRAVEL


def test_stretch_is_rated_at_the_worse_endpoint():
    s = summarize([0, 10, 20, 30], [L, H, L, L])
    # stretches: 0–10 max(L,H)=H, 10–20 max(H,L)=H, 20–30 max(L,L)=L
    assert s.miles_by_level[H] == pytest.approx(20)
    assert s.miles_by_level[L] == pytest.approx(10)
    assert s.total_miles == pytest.approx(30)
    assert s.average_risk == pytest.approx((2 * 20 + 0 * 10) / 30)


def test_every_level_has_an_entry():
    s = summarize([0, 10], [L, L])
    assert set(s.miles_by_level) == set(Level)
    assert s.miles_by_level[N] == 0
    assert s.miles_by_level[S] == 0


def test_uneven_spacing_uses_actual_stretch_lengths():
    s = summarize([0, 25, 50, 63], [S, L, L, M])
    # stretches: 0–25 S (25 mi), 25–50 L (25 mi), 50–63 M (13 mi)
    assert s.miles_by_level[S] == pytest.approx(25)
    assert s.miles_by_level[L] == pytest.approx(25)
    assert s.miles_by_level[M] == pytest.approx(13)
    assert s.total_miles == pytest.approx(63)
    assert s.average_risk == pytest.approx((3 * 25 + 0 * 25 + 1 * 13) / 63)


def test_convenience_mile_properties_and_no_travel_flag():
    s = summarize([0, 10, 20, 30, 40], [N, S, H, L, L])
    # stretches: N 10, S 10, H 10, L 10
    assert s.no_travel_miles == pytest.approx(10)
    assert s.severe_miles == pytest.approx(10)
    assert s.high_miles == pytest.approx(10)
    assert s.no_travel is True


def test_no_travel_flag_is_false_without_no_travel_checkpoints():
    s = summarize([0, 10, 20], [S, S, H])
    assert s.no_travel is False
    assert s.no_travel_miles == 0


def test_worst_level_and_first_checkpoint_at_that_level():
    s = summarize([0, 10, 20, 30], [L, H, M, H])
    assert s.worst_level is H
    assert s.worst_checkpoint_index == 1


def test_single_checkpoint_route():
    s = summarize([0], [M])
    assert s.total_miles == 0
    assert all(m == 0 for m in s.miles_by_level.values())
    assert s.average_risk == pytest.approx(M.value)
    assert s.worst_level is M
    assert s.worst_checkpoint_index == 0
    assert s.no_travel is False


def test_average_risk_counts_no_travel_as_four():
    s = summarize([0, 10], [N, N])
    assert s.average_risk == pytest.approx(4.0)


@pytest.mark.parametrize(
    "miles, levels",
    [
        ([], []),
        ([0, 10], [L]),
        ([0, 10, 5], [L, L, L]),  # miles must be non-decreasing
    ],
)
def test_rejects_invalid_input(miles, levels):
    with pytest.raises(ValueError):
        summarize(miles, levels)
