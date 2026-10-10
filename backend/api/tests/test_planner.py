"""
The planner composes geocoding, routing, checkpoint sampling, weather, risk
classification, aggregation and recommendation into one JSON-ready result.
Providers are stubs; the Django cache is the real (locmem) one.

Fixture world: origin (40, -100) to destination (41, -100), about 69 miles.
Route A runs straight up the meridian in 1 h. Routes B and C detour west and
take 1.75 h and 2.25 h. A storm (50 mph wind) sits on the meridian at exactly
14:00 UTC, one hour after departure, so route A's later checkpoints become
No Travel with a 35,000 lb load while B and C stay calm.
"""

import math
from datetime import UTC, datetime, timedelta, timezone

import pytest
from django.core.cache import cache

from api.planner import Planner, PlanningError, PlanRequest
from providers.errors import GeocodeNotFound, ProviderQuotaExceeded
from providers.openmeteo import HourlyForecast
from providers.tomtom import GeocodeResult, RouteResult
from routing.sampling import EARTH_RADIUS_MILES, ProgressEntry, cumulative_miles

MILES_PER_DEG_LAT = 2 * math.pi * EARTH_RADIUS_MILES / 360
UTC = UTC
TZ = timezone(timedelta(hours=-5))
NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
DEPART = datetime(2026, 10, 11, 8, 0, tzinfo=TZ)  # 13:00 UTC
STORM_HOUR = DEPART + timedelta(hours=1)  # 14:00 UTC
ORIGIN = (40.0, -100.0)
DEST = (41.0, -100.0)
FORECAST_START = datetime(2026, 10, 10, 0, 0, tzinfo=UTC)


def leg(p, q, n=60):
    return [(p[0] + (q[0] - p[0]) * k / n, p[1] + (q[1] - p[1]) * k / n) for k in range(n + 1)]


def detour(lon_out):
    mid = (40.5, lon_out)
    return leg(ORIGIN, mid) + leg(mid, DEST)[1:]


def make_route(index, points, hours):
    miles = cumulative_miles(points)[-1]
    return RouteResult(
        provider_index=index,
        points=points,
        length_meters=miles * 1609.344,
        travel_seconds=hours * 3600,
        traffic_delay_seconds=0,
        departure_time="",
        arrival_time="",
        progress=[ProgressEntry(0, 0), ProgressEntry(len(points) - 1, hours * 3600)],
    )


ROUTE_A = make_route(0, leg(ORIGIN, DEST, 70), 1.0)
ROUTE_B = make_route(1, detour(-100.4), 1.75)
ROUTE_C = make_route(2, detour(-100.8), 2.25)
ROUTE_A_DUP = make_route(3, [(lat, lon + 0.001) for lat, lon in ROUTE_A.points], 1.05)


class StubTomTom:
    def __init__(self, routes, places=None):
        self._routes = routes
        self._places = places or {"Origin City": ORIGIN, "Destination City": DEST}
        self.geocode_calls = []
        self.route_calls = []

    def geocode(self, query, country="US"):
        self.geocode_calls.append(query)
        if query not in self._places:
            raise GeocodeNotFound(f"No location found for '{query}'", provider="stub")
        lat, lon = self._places[query]
        return GeocodeResult(query=query, name=f"{query}, US", lat=lat, lon=lon)

    def routes(self, origin, destination, depart_at, max_alternatives=2):
        self.route_calls.append(max_alternatives)
        return self._routes[: max_alternatives + 1]


def calm(lat, lon, ts):
    return 10.0


def storm_on_meridian(lat, lon, ts):
    if abs(lon - (-100.0)) < 1e-6 and ts == STORM_HOUR.timestamp():
        return 50.0
    return 10.0


class StubWeather:
    def __init__(self, wind_fn=calm):
        self.wind_fn = wind_fn
        self.calls = []

    def hourly(self, points, forecast_days):
        self.calls.append((list(points), forecast_days))
        t0 = int(FORECAST_START.timestamp())
        times = [t0 + 3600 * h for h in range(24 * forecast_days)]
        out = []
        for lat, lon in points:
            wind = [self.wind_fn(lat, lon, t) for t in times]
            out.append(
                HourlyForecast(
                    latitude=lat,
                    longitude=lon,
                    times=times,
                    wind_mph=wind,
                    gust_mph=[w + 5 for w in wind],
                    rain_in=[0.0] * len(times),
                    snow_in=[0.0] * len(times),
                )
            )
        return out


def request(**overrides):
    base = dict(
        origin="Origin City",
        destination="Destination City",
        departure_time=DEPART,
        load_weight_lb=35_000,
        sample_interval_miles=25,
    )
    base.update(overrides)
    return PlanRequest(**base)


def planner(tomtom=None, weather=None):
    return Planner(
        tomtom=tomtom or StubTomTom([ROUTE_A, ROUTE_B, ROUTE_C]),
        weather=weather or StubWeather(),
        cache=cache,
        now=lambda: NOW,
    )


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


# --- Shape ------------------------------------------------------------------


def test_plan_has_three_routes_with_checkpoints_summary_and_heatmap():
    plan = planner().plan(request())

    assert [r["id"] for r in plan["routes"]] == ["r1", "r2", "r3"]
    assert [r["provider_index"] for r in plan["routes"]] == [0, 1, 2]
    assert plan["inputs"]["origin"]["name"] == "Origin City, US"
    assert plan["inputs"]["destination"]["lat"] == 41.0
    assert plan["inputs"]["departure_time"] == "2026-10-11T08:00:00-05:00"
    assert plan["inputs"]["load_weight_lb"] == 35_000
    assert plan["inputs"]["sample_interval_miles"] == 25

    a = plan["routes"][0]
    assert a["distance_miles"] == pytest.approx(69.1, abs=0.1)
    assert a["duration_seconds"] == 3600
    assert a["arrival_time"] == "2026-10-11T09:00:00-05:00"
    assert [round(c["mile"], 1) for c in a["checkpoints"]] == [0, 25, 50, pytest.approx(69.1, abs=0.1)]
    assert a["geometry"][0] == [-100.0, 40.0]  # GeoJSON order [lon, lat]
    assert a["geometry"][-1] == [-100.0, 41.0]
    assert len(a["geometry"]) < len(ROUTE_A.points)
    assert a["bbox"] == [-100.0, 40.0, -100.0, 41.0]
    assert set(a["summary"]["miles_by_level"]) == {"low", "moderate", "high", "severe", "no_travel"}
    assert set(a["summary"]) >= {"miles_by_level", "average_risk", "worst_level", "worst_checkpoint_index", "no_travel"}

    cp = a["checkpoints"][1]
    assert set(cp) >= {
        "index", "mile", "lat", "lon", "eta", "wind_mph", "gust_mph", "rain_in_hr", "snow_in_hr",
        "wind_level", "rain_level", "snow_level", "level", "load_rule", "reason",
    }  # fmt: skip
    assert cp["level"] == "low"

    assert plan["recommendation"]["route_id"] == plan["recommended_route_id"]
    assert set(plan["recommendation"]) == {"route_id", "ranked_ids", "reason", "all_no_travel"}
    assert len(plan["heatmap"]["hours"]) == 49
    assert plan["heatmap"]["hours"][0] == "2026-10-11T08:00:00-05:00"
    assert plan["heatmap"]["hours"][48] == "2026-10-13T08:00:00-05:00"
    # The heatmap grid is the set of checkpoints across all routes (no extra weather lookups).
    assert plan["heatmap"]["interval_miles"] == 25
    unique_checkpoints = {(c["lat"], c["lon"]) for r in plan["routes"] for c in r["checkpoints"]}
    assert len(plan["heatmap"]["points"]) == len(unique_checkpoints)
    assert all(len(p["levels"]) == 49 for p in plan["heatmap"]["points"])
    assert plan["warnings"] == []


def test_checkpoint_etas_interpolate_provider_progress():
    plan = planner().plan(request())
    a = plan["routes"][0]
    total = ROUTE_A.length_meters / 1609.344
    expected = DEPART + timedelta(seconds=3600 * 25 / total)
    assert datetime.fromisoformat(a["checkpoints"][1]["eta"]) == pytest.approx(expected, abs=timedelta(seconds=2))
    etas = [datetime.fromisoformat(c["eta"]) for c in a["checkpoints"]]
    assert etas == sorted(etas)
    assert etas[-1] == DEPART + timedelta(hours=1)


def test_ranks_follow_recommendation_order():
    plan = planner().plan(request())
    ranked = plan["recommendation"]["ranked_ids"]
    assert sorted(plan["routes"], key=lambda r: r["rank"])[0]["id"] == ranked[0]
    assert {r["id"]: r["rank"] for r in plan["routes"]} == {rid: i + 1 for i, rid in enumerate(ranked)}


# --- Weather, risk and recommendation ----------------------------------------


def test_storm_makes_route_a_no_travel_and_recommends_route_b():
    plan = planner(weather=StubWeather(storm_on_meridian)).plan(request())

    a, b, c = plan["routes"]
    assert a["summary"]["no_travel"] is True
    assert a["summary"]["worst_level"] == "no_travel"
    stormy = [cp for cp in a["checkpoints"] if cp["level"] == "no_travel"]
    assert stormy and all(cp["wind_mph"] == 50.0 for cp in stormy)
    assert "30,000" in stormy[0]["reason"] and stormy[0]["load_rule"] is not None
    assert b["summary"]["no_travel"] is False and c["summary"]["no_travel"] is False

    assert plan["recommended_route_id"] == "r2"
    assert plan["recommendation"]["ranked_ids"] == ["r2", "r3", "r1"]
    assert "No Travel" in plan["recommendation"]["reason"]


def test_lighter_load_keeps_storm_at_severe():
    plan = planner(weather=StubWeather(storm_on_meridian)).plan(request(load_weight_lb=20_000))
    a = plan["routes"][0]
    assert a["summary"]["no_travel"] is False
    assert a["summary"]["worst_level"] == "severe"
    assert plan["recommended_route_id"] == "r2"  # fewest Severe miles


def test_heatmap_levels_change_with_the_hour():
    plan = planner(weather=StubWeather(storm_on_meridian)).plan(request())
    on_meridian = [p for p in plan["heatmap"]["points"] if p["lon"] == -100.0 and 40.2 < p["lat"] < 40.9]
    assert on_meridian
    point = on_meridian[0]
    assert point["levels"][0] == 0  # departure hour, calm
    assert point["levels"][1] == 4  # storm hour, No Travel with this load
    assert point["levels"][2] == 0


# --- Route count handling ---------------------------------------------------


def test_retries_with_more_alternatives_when_fewer_than_three_distinct():
    # Provider order: A, a near-duplicate of A, then B and C (indexes match positions).
    duplicate = make_route(1, ROUTE_A_DUP.points, 1.05)
    b = make_route(2, ROUTE_B.points, 1.75)
    c = make_route(3, ROUTE_C.points, 2.25)
    tomtom = StubTomTom([ROUTE_A, duplicate, b, c])
    plan = planner(tomtom=tomtom).plan(request())
    assert tomtom.route_calls == [2, 4]
    assert [r["provider_index"] for r in plan["routes"]] == [0, 2, 3]
    assert plan["warnings"] == []


def test_warns_when_provider_cannot_supply_three_routes():
    tomtom = StubTomTom([ROUTE_A, ROUTE_B])
    plan = planner(tomtom=tomtom).plan(request())
    assert tomtom.route_calls == [2, 4]
    assert len(plan["routes"]) == 2
    assert any("2" in w and "route" in w.lower() for w in plan["warnings"])


# --- Validation and errors --------------------------------------------------


def test_same_origin_and_destination_is_rejected():
    tomtom = StubTomTom([ROUTE_A], places={"Here": ORIGIN, "Also Here": (40.001, -100.001)})
    with pytest.raises(PlanningError):
        planner(tomtom=tomtom).plan(request(origin="Here", destination="Also Here"))


def test_geocode_failure_propagates():
    with pytest.raises(GeocodeNotFound):
        planner().plan(request(origin="Atlantis"))


# --- Caching and forecast window --------------------------------------------


def test_provider_results_are_cached_between_plans():
    tomtom = StubTomTom([ROUTE_A, ROUTE_B, ROUTE_C])
    weather = StubWeather()
    p = planner(tomtom=tomtom, weather=weather)
    p.plan(request())
    p.plan(request(load_weight_lb=10_000))  # different load, same trip: no new provider calls
    assert tomtom.geocode_calls == ["Origin City", "Destination City"]
    assert tomtom.route_calls == [2]
    assert len(weather.calls) == 1


def test_forecast_window_covers_departure_plus_48_hours():
    weather = StubWeather()
    planner(weather=weather).plan(request())
    # today is 2026-10-10 UTC; departure + 48 h ends on 2026-10-13 UTC -> 4 forecast days
    assert weather.calls[0][1] == 4


def test_weather_is_fetched_once_for_all_unique_checkpoints():
    weather = StubWeather()
    plan = planner(weather=weather).plan(request())
    assert len(weather.calls) == 1
    points = weather.calls[0][0]
    assert len(points) == len(set(points))
    # Shared origin/destination checkpoints are fetched once; every heatmap point has a forecast.
    assert len(points) == len(plan["heatmap"]["points"])
    assert len(points) < sum(len(r["checkpoints"]) for r in plan["routes"])


def test_changing_the_interval_only_fetches_weather_for_new_checkpoints():
    weather = StubWeather()
    p = planner(weather=weather)
    coarse = p.plan(request(sample_interval_miles=50))
    fine = p.plan(request(sample_interval_miles=25))
    assert len(weather.calls) == 2
    first, second = weather.calls[0][0], weather.calls[1][0]
    coarse_points = {(c["lat"], c["lon"]) for r in coarse["routes"] for c in r["checkpoints"]}
    fine_points = {(c["lat"], c["lon"]) for r in fine["routes"] for c in r["checkpoints"]}
    fetched_second = {(round(lat, 5), round(lon, 5)) for lat, lon in second}
    assert fetched_second == fine_points - coarse_points  # only the checkpoints that are new at 25 mi
    assert not set(second) & set(first)


# --- Phase 6 edge cases -----------------------------------------------------


class ShortWeather(StubWeather):
    """A provider whose forecast ends at the end of today, whatever was asked for."""

    def hourly(self, points, forecast_days):
        return super().hourly(points, 1)


def test_warns_with_the_forecast_end_when_etas_and_heatmap_hours_fall_after_it():
    plan = planner(weather=ShortWeather()).plan(request())
    checkpoints = sum(len(r["checkpoints"]) for r in plan["routes"])
    [warning] = [w for w in plan["warnings"] if w.startswith("Forecast data ends")]
    assert "2026-10-10 23:00 UTC" in warning
    assert f"{checkpoints} checkpoint ETA(s)" in warning
    assert "49 of 49 heatmap hours" in warning
    # Every checkpoint still gets a level: the last forecast hour is used.
    assert all(c["level"] for r in plan["routes"] for c in r["checkpoints"])


def test_warns_about_heatmap_hours_only_when_the_16_day_horizon_cuts_the_slider_window():
    weather = StubWeather()
    far = datetime(2026, 10, 24, 8, 0, tzinfo=TZ)  # 13:00 UTC, 14 days out: window ends 2026-10-25 23:00 UTC
    plan = planner(weather=weather).plan(request(departure_time=far))
    assert weather.calls[0][1] == 16
    [warning] = [w for w in plan["warnings"] if w.startswith("Forecast data ends")]
    assert "2026-10-25 23:00 UTC" in warning
    assert "14 of 49 heatmap hours" in warning
    assert "checkpoint" not in warning


def test_no_forecast_warning_when_everything_is_covered():
    plan = planner().plan(request())
    assert not [w for w in plan["warnings"] if "forecast" in w.lower()]


def test_trips_needing_too_many_weather_locations_are_rejected_before_fetching(monkeypatch):
    monkeypatch.setattr("api.planner.MAX_WEATHER_LOCATIONS", 5)
    weather = StubWeather()
    with pytest.raises(PlanningError) as info:
        planner(weather=weather).plan(request(sample_interval_miles=10))
    assert info.value.code == "too_many_checkpoints"
    assert info.value.http_status == 422
    assert "10-mile" in info.value.message
    assert "5" in info.value.message
    assert weather.calls == []


def test_coarser_sampling_stays_under_the_weather_location_cap(monkeypatch):
    # At 50 mi the three fixture routes share origin and destination and add 4 mid-route points: 6 cells.
    monkeypatch.setattr("api.planner.MAX_WEATHER_LOCATIONS", 6)
    plan = planner().plan(request(sample_interval_miles=50))
    assert len(plan["heatmap"]["points"]) == 6


def test_single_route_is_shown_ranked_first_with_a_warning():
    tomtom = StubTomTom([ROUTE_A])
    plan = planner(tomtom=tomtom).plan(request())
    assert tomtom.route_calls == [2, 4]
    assert [r["rank"] for r in plan["routes"]] == [1]
    assert plan["recommended_route_id"] == "r1"
    assert plan["recommendation"]["reason"] == "Only route available."
    assert any("only 1 distinct route" in w for w in plan["warnings"])


class FlakyWeather(StubWeather):
    """Fails with a rate limit on the call whose index is in `fail_on` (0-based), otherwise behaves normally."""

    def __init__(self, fail_on):
        super().__init__()
        self.fail_on = set(fail_on)

    def hourly(self, points, forecast_days):
        index = len(self.calls)
        if index in self.fail_on:
            self.calls.append((list(points), forecast_days))
            raise ProviderQuotaExceeded("Minutely API request limit exceeded", provider="Open-Meteo")
        return super().hourly(points, forecast_days)


def test_weather_is_fetched_and_cached_in_chunks_so_a_rate_limit_mid_plan_keeps_progress(monkeypatch):
    monkeypatch.setattr("api.planner.WEATHER_FETCH_CHUNK", 4)
    weather = FlakyWeather(fail_on=[1])  # second chunk hits the rate limit
    p = planner(weather=weather)
    with pytest.raises(ProviderQuotaExceeded):
        p.plan(request())
    assert len(weather.calls) == 2
    assert len(weather.calls[0][0]) == 4

    # A minute later the driver retries: the first chunk is served from cache, only the rest is fetched.
    weather.fail_on = set()
    plan = p.plan(request())
    fetched_after_retry = [pts for pts, _ in weather.calls[2:]]
    total = len(plan["heatmap"]["points"])
    assert sum(len(pts) for pts in fetched_after_retry) == total - 4
    assert all(len(pts) <= 4 for pts in fetched_after_retry)
