"""
Geometry along a route: distances, checkpoints every N miles, travel-time
interpolation from the routing provider's progress data, and display
simplification.

Fixture: a straight north-south line of points along one meridian. Along a
meridian the great-circle distance is exactly R * delta_lat, so with
MILES_PER_DEG_LAT derived from the same Earth radius each step is exactly one
mile and the expected positions are known in closed form.
"""

import pytest

from routing.sampling import (
    EARTH_RADIUS_MILES,
    ProgressEntry,
    cumulative_miles,
    haversine_miles,
    sample_along_route,
    seconds_at_mile,
    simplify_polyline,
    time_profile,
)

MILES_PER_DEG_LAT = 2 * 3.141592653589793 * EARTH_RADIUS_MILES / 360
BASE_LAT, LON = 40.0, -100.0


def line(total_miles, step_miles=1):
    """Points from BASE_LAT northwards, one every `step_miles`, ending at total_miles."""
    n = int(total_miles / step_miles)
    return [(BASE_LAT + k * step_miles / MILES_PER_DEG_LAT, LON) for k in range(n + 1)]


def lat_at(mile):
    return BASE_LAT + mile / MILES_PER_DEG_LAT


# --- Distances --------------------------------------------------------------


def test_haversine_known_distance_new_york_to_los_angeles():
    miles = haversine_miles(40.7128, -74.0060, 34.0522, -118.2437)
    assert miles == pytest.approx(2445, rel=0.01)


def test_haversine_zero_for_same_point():
    assert haversine_miles(40, -100, 40, -100) == 0


def test_cumulative_miles_along_fixture_line():
    cum = cumulative_miles(line(100))
    assert len(cum) == 101
    assert cum[0] == 0
    for k in (1, 50, 100):
        assert cum[k] == pytest.approx(k, abs=1e-6)


def test_cumulative_requires_at_least_two_points():
    with pytest.raises(ValueError):
        cumulative_miles([(40, -100)])


# --- Checkpoint sampling ----------------------------------------------------


@pytest.mark.parametrize(
    "interval, expected_miles",
    [
        (10, [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]),
        (25, [0, 25, 50, 75, 100]),
        (50, [0, 50, 100]),
        (30, [0, 30, 60, 90, 100]),  # destination is always the last checkpoint
    ],
)
def test_sample_miles(interval, expected_miles):
    samples = sample_along_route(line(100), interval)
    assert [round(s.mile, 6) for s in samples] == expected_miles


def test_sample_positions_are_interpolated_along_the_line():
    samples = sample_along_route(line(100, step_miles=10), 25)
    for s in samples:
        assert s.lat == pytest.approx(lat_at(s.mile), abs=1e-9)
        assert s.lon == LON


def test_sample_vertex_index_and_fraction_mid_segment():
    samples = sample_along_route(line(10), 2.5)
    s = samples[1]
    assert s.mile == pytest.approx(2.5)
    assert s.vertex_index == 2
    assert s.vertex_fraction == pytest.approx(0.5, abs=1e-6)


def test_sample_indices_are_sequential():
    samples = sample_along_route(line(100), 25)
    assert [s.index for s in samples] == [0, 1, 2, 3, 4]


def test_sample_route_shorter_than_interval():
    samples = sample_along_route(line(7), 10)
    assert [round(s.mile, 6) for s in samples] == [0, 7]


def test_sample_destination_not_duplicated_when_total_is_a_multiple():
    samples = sample_along_route(line(50), 25)
    assert [round(s.mile, 6) for s in samples] == [0, 25, 50]


def test_sample_zero_length_route_gives_single_checkpoint():
    samples = sample_along_route([(40, -100), (40, -100)], 10)
    assert len(samples) == 1
    assert samples[0].mile == 0


def test_sample_accepts_precomputed_cumulative():
    pts = line(100)
    cum = cumulative_miles(pts)
    assert sample_along_route(pts, 50, cumulative=cum) == sample_along_route(pts, 50)


@pytest.mark.parametrize("interval", [0, -5])
def test_sample_rejects_non_positive_interval(interval):
    with pytest.raises(ValueError):
        sample_along_route(line(10), interval)


def test_sample_rejects_single_point():
    with pytest.raises(ValueError):
        sample_along_route([(40, -100)], 10)


# --- Travel-time profile ----------------------------------------------------


def test_time_profile_maps_progress_point_indices_to_miles():
    cum = cumulative_miles(line(100))
    profile = time_profile([ProgressEntry(0, 0), ProgressEntry(50, 3600), ProgressEntry(100, 7200)], cum)
    assert [(round(m, 6), s) for m, s in profile] == [(0, 0), (50, 3600), (100, 7200)]


def test_seconds_at_mile_interpolates_linearly_within_a_span():
    cum = cumulative_miles(line(100))
    profile = time_profile([ProgressEntry(0, 0), ProgressEntry(50, 1800), ProgressEntry(100, 7200)], cum)
    assert seconds_at_mile(profile, 25) == pytest.approx(900)
    assert seconds_at_mile(profile, 50) == pytest.approx(1800)
    assert seconds_at_mile(profile, 75) == pytest.approx(4500)


def test_seconds_at_mile_clamps_outside_the_profile():
    cum = cumulative_miles(line(100))
    profile = time_profile([ProgressEntry(0, 0), ProgressEntry(100, 7200)], cum)
    assert seconds_at_mile(profile, -1) == 0
    assert seconds_at_mile(profile, 100) == 7200
    assert seconds_at_mile(profile, 250) == 7200


def test_time_profile_sorts_entries_by_point_index():
    cum = cumulative_miles(line(100))
    profile = time_profile([ProgressEntry(100, 7200), ProgressEntry(0, 0)], cum)
    assert [round(m) for m, _ in profile] == [0, 100]


def test_time_profile_rejects_decreasing_time():
    cum = cumulative_miles(line(100))
    with pytest.raises(ValueError):
        time_profile([ProgressEntry(0, 0), ProgressEntry(50, 5000), ProgressEntry(100, 4000)], cum)


def test_time_profile_rejects_out_of_range_point_index():
    cum = cumulative_miles(line(100))
    with pytest.raises(ValueError):
        time_profile([ProgressEntry(0, 0), ProgressEntry(500, 7200)], cum)


def test_time_profile_requires_two_entries():
    cum = cumulative_miles(line(100))
    with pytest.raises(ValueError):
        time_profile([ProgressEntry(0, 0)], cum)


# --- Display simplification -------------------------------------------------


def test_simplify_collinear_points_reduce_to_endpoints():
    pts = line(100)
    assert simplify_polyline(pts, tolerance_deg=1e-5) == [pts[0], pts[-1]]


def test_simplify_keeps_points_that_deviate_more_than_tolerance():
    pts = [(40.0, -100.0), (40.5, -100.0), (41.0, -100.2), (41.5, -100.0), (42.0, -100.0)]
    out = simplify_polyline(pts, tolerance_deg=0.01)
    assert out[0] == pts[0] and out[-1] == pts[-1]
    assert (41.0, -100.2) in out


def test_simplify_preserves_endpoints_and_short_inputs():
    assert simplify_polyline([(40, -100)], 0.01) == [(40, -100)]
    assert simplify_polyline([(40, -100), (41, -100)], 0.01) == [(40, -100), (41, -100)]
