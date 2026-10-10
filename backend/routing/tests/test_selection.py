"""
Choosing up to three genuinely different routes from a provider's alternatives.
Overlap is the share of a route's ~1 km grid cells that another route also
passes through.
"""

import pytest

from routing.selection import path_overlap, select_distinct_routes


def meridian(lon, lat0=40.0, lat1=41.0, n=100):
    return [(lat0 + (lat1 - lat0) * k / n, lon) for k in range(n + 1)]


A = meridian(-100.0)
B = meridian(-100.5)
C = meridian(-101.0)
A_SHIFTED = [(lat, lon + 0.002) for lat, lon in A]  # same road within grid precision


def test_overlap_of_identical_paths_is_one():
    assert path_overlap(A, A) == pytest.approx(1.0)
    assert path_overlap(A, A_SHIFTED) == pytest.approx(1.0)


def test_overlap_of_disjoint_paths_is_zero():
    assert path_overlap(A, B) == 0.0


def test_overlap_is_measured_relative_to_the_first_path():
    half_of_a = A[: len(A) // 2]
    assert path_overlap(half_of_a, A) == pytest.approx(1.0)
    assert 0.4 < path_overlap(A, half_of_a) < 0.6


def test_keeps_provider_order_and_drops_near_duplicates():
    assert select_distinct_routes([A, A_SHIFTED, B, C], max_routes=3) == [0, 2, 3]


def test_returns_all_when_fewer_than_max_and_distinct():
    assert select_distinct_routes([A, B], max_routes=3) == [0, 1]


def test_without_fill_only_distinct_routes_are_returned():
    assert select_distinct_routes([A, A_SHIFTED, A], max_routes=3) == [0]
    assert select_distinct_routes([A, A_SHIFTED, B], max_routes=3) == [0, 2]


def test_fill_adds_back_least_overlapping_duplicates_when_short():
    assert select_distinct_routes([A, A_SHIFTED, A], max_routes=3, fill=True) == [0, 1, 2]
    assert select_distinct_routes([A, A_SHIFTED, A, B], max_routes=3, fill=True) == [0, 1, 3]


def test_empty_input():
    assert select_distinct_routes([], max_routes=3) == []
