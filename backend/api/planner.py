"""
The planning pipeline behind POST /api/plan:

    geocode -> truck routes (3 distinct) -> checkpoints every N miles ->
    ETA per checkpoint from the provider's timing -> one batched weather
    request for every checkpoint not already cached -> risk per checkpoint ->
    route summaries -> recommendation -> heatmap (every checkpoint, 0-48 h
    from departure)

Provider responses are cached (geocode 24 h, routes 1 h, weather 30 min per
~3 km cell) so repeated or slightly changed requests do not spend free-tier
quota. Providers are injected so the pipeline is unit-tested with stubs.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from providers.openmeteo import MAX_FORECAST_DAYS, HourlyForecast
from providers.tomtom import GeocodeResult, RouteResult
from routing.aggregate import RouteRiskSummary, summarize
from routing.recommend import RouteCandidate, recommend
from routing.risk import Level, assess
from routing.sampling import (
    LatLon,
    SampledPoint,
    cumulative_miles,
    haversine_miles,
    sample_along_route,
    seconds_at_mile,
    simplify_polyline,
    time_profile,
)
from routing.selection import select_distinct_routes

logger = logging.getLogger(__name__)

METERS_PER_MILE = 1609.344
MAX_ROUTES = 3
FIRST_TRY_ALTERNATIVES = 2  # 3 routes in ~4 s on a 1,000-mile trip
RETRY_ALTERNATIVES = 4  # only when fewer than 3 distinct routes came back
HEATMAP_HOURS = 48
GEOMETRY_TOLERANCE_DEG = 0.0005  # ~50 m, display only
MIN_TRIP_MILES = 0.5
GEOCODE_TTL_SECONDS = 24 * 3600
ROUTES_TTL_SECONDS = 3600
WEATHER_TTL_SECONDS = 1800
WEATHER_CELL_DEG = 0.05  # ~3 km; coarser than the forecast model's own grid is not
ROUTE_TIME_BUCKET = timedelta(minutes=15)
# Open-Meteo's free tier counts every location in a batch against its 600 calls/min, weighted by
# forecast length (14 days = 1.0, so 16 days = 1.14): 500 locations is at most ~570 weighted calls,
# under the limit for one plan. Deterministic (unique checkpoints, not uncached ones) so the same
# trip always gets the same answer. A cross-country trip at 10 mi needs ~1,000 and is refused.
MAX_WEATHER_LOCATIONS = 500
# Fetch and cache weather in chunks: if the provider rate-limits part-way through a plan, the chunks
# already fetched are kept, so a retry a minute later only asks for the rest.
WEATHER_FETCH_CHUNK = 200
FORECAST_SLACK = timedelta(minutes=30)  # a time within 30 min of the last forecast hour still counts as covered


class PlanningError(Exception):
    """The request is well-formed but cannot be planned (e.g. same origin and destination)."""

    code = "invalid_trip"
    http_status = 422

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class TooManyCheckpoints(PlanningError):
    """The trip would need more weather locations than the free weather API allows in one plan."""

    code = "too_many_checkpoints"


@dataclass(frozen=True)
class PlanRequest:
    origin: str
    destination: str
    departure_time: datetime  # timezone-aware
    load_weight_lb: float
    sample_interval_miles: int


class RoutingProvider(Protocol):
    def geocode(self, query: str, country: str = "US") -> GeocodeResult: ...

    def routes(
        self, origin: LatLon, destination: LatLon, depart_at: datetime, max_alternatives: int = 2
    ) -> list[RouteResult]: ...


class WeatherProvider(Protocol):
    def hourly(self, points: Sequence[LatLon], forecast_days: int) -> list[HourlyForecast]: ...


class Cache(Protocol):
    """The subset of Django's cache API the planner uses."""

    def get(self, key: str) -> Any: ...

    def set(self, key: str, value: Any, timeout: int) -> None: ...

    def get_many(self, keys: Sequence[str]) -> dict[str, Any]: ...

    def set_many(self, data: dict[str, Any], timeout: int) -> Any: ...


@dataclass(frozen=True)
class _PreparedRoute:
    route: RouteResult
    cumulative: list[float]
    checkpoints: list[SampledPoint]
    etas: list[datetime]


Cell = tuple[float, float]


def _cell(lat: float, lon: float) -> Cell:
    """Snap a position to the weather cache grid."""
    return (
        round(round(lat / WEATHER_CELL_DEG) * WEATHER_CELL_DEG, 2),
        round(round(lon / WEATHER_CELL_DEG) * WEATHER_CELL_DEG, 2),
    )


class Planner:
    def __init__(
        self,
        *,
        tomtom: RoutingProvider,
        weather: WeatherProvider,
        cache: Cache,
        now: Callable[[], datetime] | None = None,
    ):
        self._tomtom = tomtom
        self._weather = weather
        self._cache = cache
        self._now = now or (lambda: datetime.now(UTC))

    # --- Entry point --------------------------------------------------------

    def plan(self, req: PlanRequest) -> dict[str, Any]:
        self._validate(req)
        started = time.perf_counter()

        origin = self._geocode(req.origin)
        destination = self._geocode(req.destination)
        if haversine_miles(origin.lat, origin.lon, destination.lat, destination.lon) < MIN_TRIP_MILES:
            raise PlanningError("Origin and destination resolve to the same place.")

        routes, warnings = self._select_routes(origin, destination, req.departure_time)
        prepared = [self._prepare(route, req) for route in routes]
        forecast_days = self._forecast_days(req.departure_time, prepared)
        forecasts = self._forecasts(prepared, forecast_days, req.sample_interval_miles)

        route_payloads: list[dict[str, Any]] = []
        candidates: list[RouteCandidate] = []
        uncovered = 0
        for i, p in enumerate(prepared):
            route_id = f"r{i + 1}"
            checkpoints, levels, missed = self._assess_checkpoints(p, forecasts, req.load_weight_lb)
            uncovered += missed
            summary = summarize([c.mile for c in p.checkpoints], levels)
            candidates.append(RouteCandidate(route_id=route_id, summary=summary, travel_seconds=p.route.travel_seconds))
            route_payloads.append(self._route_payload(route_id, i, p, req, checkpoints, summary))

        recommendation = recommend(candidates)
        rank_of = {route_id: rank + 1 for rank, route_id in enumerate(recommendation.ranked_ids)}
        for payload in route_payloads:
            payload["rank"] = rank_of[payload["id"]]

        heatmap = self._heatmap(prepared, forecasts, req)
        forecast_warning = self._forecast_warning(forecasts, req.departure_time, uncovered)
        if forecast_warning:
            warnings.append(forecast_warning)
        logger.info(
            "plan %s -> %s: %d routes, %d forecast days, %.2fs",
            origin.name,
            destination.name,
            len(routes),
            forecast_days,
            time.perf_counter() - started,
        )
        return {
            "inputs": {
                "origin": _place_payload(origin),
                "destination": _place_payload(destination),
                "departure_time": req.departure_time.isoformat(),
                "load_weight_lb": req.load_weight_lb,
                "sample_interval_miles": req.sample_interval_miles,
            },
            "routes": route_payloads,
            "recommended_route_id": recommendation.route_id,
            "recommendation": {
                "route_id": recommendation.route_id,
                "ranked_ids": recommendation.ranked_ids,
                "reason": recommendation.reason,
                "all_no_travel": recommendation.all_no_travel,
            },
            "heatmap": heatmap,
            "warnings": warnings,
        }

    # --- Steps ----------------------------------------------------------------

    @staticmethod
    def _validate(req: PlanRequest) -> None:
        if req.departure_time.tzinfo is None or req.departure_time.utcoffset() is None:
            raise ValueError("departure_time must be timezone-aware")
        if req.load_weight_lb <= 0:
            raise ValueError("load_weight_lb must be positive")
        if req.sample_interval_miles <= 0:
            raise ValueError("sample_interval_miles must be positive")

    def _geocode(self, query: str) -> GeocodeResult:
        normalized = " ".join(query.split()).lower()
        key = f"geocode:v1:us:{hashlib.sha1(normalized.encode()).hexdigest()}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        result = self._tomtom.geocode(query)
        self._cache.set(key, result, GEOCODE_TTL_SECONDS)
        return result

    def _routes(
        self, origin: GeocodeResult, destination: GeocodeResult, depart: datetime, max_alt: int
    ) -> list[RouteResult]:
        utc = depart.astimezone(UTC)
        bucket = utc - timedelta(
            minutes=utc.minute % (ROUTE_TIME_BUCKET.seconds // 60), seconds=utc.second, microseconds=utc.microsecond
        )
        key = (
            f"routes:v1:{origin.lat:.4f},{origin.lon:.4f}:{destination.lat:.4f},{destination.lon:.4f}"
            f":{bucket.isoformat()}:{max_alt}"
        )
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        routes = self._tomtom.routes((origin.lat, origin.lon), (destination.lat, destination.lon), depart, max_alt)
        self._cache.set(key, routes, ROUTES_TTL_SECONDS)
        return routes

    def _select_routes(
        self, origin: GeocodeResult, destination: GeocodeResult, depart: datetime
    ) -> tuple[list[RouteResult], list[str]]:
        routes = self._routes(origin, destination, depart, FIRST_TRY_ALTERNATIVES)
        distinct = select_distinct_routes([r.points for r in routes], MAX_ROUTES)
        if len(distinct) < MAX_ROUTES:
            routes = self._routes(origin, destination, depart, RETRY_ALTERNATIVES)
            distinct = select_distinct_routes([r.points for r in routes], MAX_ROUTES)

        warnings: list[str] = []
        chosen = distinct
        if len(distinct) < MAX_ROUTES:
            # Last resort: show near-duplicate alternatives rather than fewer options, and say so.
            chosen = select_distinct_routes([r.points for r in routes], MAX_ROUTES, fill=True)
            noun = "route" if len(distinct) == 1 else "routes"
            message = f"The routing provider returned only {len(distinct)} distinct {noun} for this trip"
            if len(chosen) > len(distinct):
                message += f"; {len(chosen) - len(distinct)} similar alternative(s) shown as well"
            warnings.append(message + ".")
        return [routes[i] for i in chosen], warnings

    @staticmethod
    def _prepare(route: RouteResult, req: PlanRequest) -> _PreparedRoute:
        cumulative = cumulative_miles(route.points)
        checkpoints = sample_along_route(route.points, req.sample_interval_miles, cumulative)
        if len(route.progress) >= 2:
            profile = time_profile(route.progress, cumulative)
        else:  # provider gave no timing points: assume constant speed
            profile = [(0.0, 0.0), (cumulative[-1], route.travel_seconds)]
        etas = [
            (req.departure_time + timedelta(seconds=seconds_at_mile(profile, c.mile))).replace(microsecond=0)
            for c in checkpoints
        ]
        return _PreparedRoute(route=route, cumulative=cumulative, checkpoints=checkpoints, etas=etas)

    def _forecast_days(self, departure: datetime, prepared: Sequence[_PreparedRoute]) -> int:
        latest = departure + timedelta(hours=HEATMAP_HOURS)
        for p in prepared:
            latest = max(latest, p.etas[-1])
        today = self._now().astimezone(UTC).date()
        days = (latest.astimezone(UTC).date() - today).days + 1
        return max(1, min(MAX_FORECAST_DAYS, days))

    def _forecasts(
        self, prepared: Sequence[_PreparedRoute], forecast_days: int, interval_miles: int
    ) -> dict[Cell, HourlyForecast]:
        """One forecast per weather cell touched by any checkpoint; only uncached cells are fetched."""
        positions: dict[Cell, LatLon] = {}
        for p in prepared:
            for s in p.checkpoints:
                positions.setdefault(_cell(s.lat, s.lon), (s.lat, s.lon))
        if len(positions) > MAX_WEATHER_LOCATIONS:
            raise TooManyCheckpoints(
                f"This trip needs weather for {len(positions)} locations at {interval_miles}-mile sampling, "
                f"more than the {MAX_WEATHER_LOCATIONS} the weather service allows per plan. "
                "Choose a larger sampling interval."
            )
        cache_keys = {cell: f"weather:v2:{cell[0]:.2f}:{cell[1]:.2f}:{forecast_days}" for cell in positions}

        cached = self._cache.get_many(list(cache_keys.values()))
        forecasts: dict[Cell, HourlyForecast] = {cell: cached[key] for cell, key in cache_keys.items() if key in cached}
        missing = [cell for cell in positions if cell not in forecasts]
        for start in range(0, len(missing), WEATHER_FETCH_CHUNK):
            chunk = missing[start : start + WEATHER_FETCH_CHUNK]
            fetched = self._weather.hourly([positions[cell] for cell in chunk], forecast_days)
            new_entries = dict(zip(chunk, fetched, strict=True))
            forecasts.update(new_entries)
            self._cache.set_many({cache_keys[cell]: f for cell, f in new_entries.items()}, WEATHER_TTL_SECONDS)
        return forecasts

    @staticmethod
    def _forecast_warning(
        forecasts: dict[Cell, HourlyForecast], departure: datetime, uncovered_checkpoints: int
    ) -> str | None:
        """Say when the forecast ends if checkpoint ETAs or slider hours fall outside it (the nearest hour is used)."""
        end = datetime.fromtimestamp(min(f.times[-1] for f in forecasts.values()), UTC)
        hours = [departure + timedelta(hours=h) for h in range(HEATMAP_HOURS + 1)]
        uncovered_hours = sum(1 for when in hours if when > end + FORECAST_SLACK)
        if not uncovered_checkpoints and not uncovered_hours:
            return None
        parts = []
        if uncovered_checkpoints:
            parts.append(f"{uncovered_checkpoints} checkpoint ETA(s)")
        if uncovered_hours:
            parts.append(f"{uncovered_hours} of {len(hours)} heatmap hours")
        return (
            f"Forecast data ends {end:%Y-%m-%d %H:%M} UTC; {' and '.join(parts)} are outside the forecast "
            "window and use the nearest available forecast hour."
        )

    @staticmethod
    def _assess_checkpoints(
        p: _PreparedRoute, forecasts: dict[Cell, HourlyForecast], load_lb: float
    ) -> tuple[list[dict[str, Any]], list[Level], int]:
        payloads: list[dict[str, Any]] = []
        levels: list[Level] = []
        uncovered = 0
        for c, eta in zip(p.checkpoints, p.etas, strict=True):
            forecast = forecasts[_cell(c.lat, c.lon)]
            if not forecast.covers(eta):
                uncovered += 1
            sample = forecast.sample_at(eta)
            a = assess(sample, load_lb)
            levels.append(a.level)
            payloads.append(
                {
                    "index": c.index,
                    "mile": round(c.mile, 2),
                    "lat": round(c.lat, 5),
                    "lon": round(c.lon, 5),
                    "eta": eta.isoformat(),
                    "wind_mph": sample.wind_mph,
                    "gust_mph": sample.gust_mph,
                    "rain_in_hr": sample.rain_in_hr,
                    "snow_in_hr": sample.snow_in_hr,
                    "wind_level": a.wind_level.key,
                    "rain_level": a.rain_level.key,
                    "snow_level": a.snow_level.key,
                    "level": a.level.key,
                    "load_rule": a.load_rule,
                    "reason": a.reason,
                }
            )
        return payloads, levels, uncovered

    @staticmethod
    def _route_payload(
        route_id: str,
        index: int,
        p: _PreparedRoute,
        req: PlanRequest,
        checkpoints: list[dict[str, Any]],
        summary: RouteRiskSummary,
    ) -> dict[str, Any]:
        route = p.route
        lats = [lat for lat, _ in route.points]
        lons = [lon for _, lon in route.points]
        arrival = req.departure_time + timedelta(seconds=round(route.travel_seconds))
        return {
            "id": route_id,
            "name": f"Route {index + 1}",
            "provider_index": route.provider_index,
            "distance_miles": round(route.length_meters / METERS_PER_MILE, 1),
            "duration_seconds": round(route.travel_seconds),
            "traffic_delay_seconds": round(route.traffic_delay_seconds),
            "departure_time": req.departure_time.isoformat(),
            "arrival_time": arrival.isoformat(),
            "geometry": [
                [round(lon, 5), round(lat, 5)] for lat, lon in simplify_polyline(route.points, GEOMETRY_TOLERANCE_DEG)
            ],
            "bbox": [round(min(lons), 5), round(min(lats), 5), round(max(lons), 5), round(max(lats), 5)],
            "checkpoints": checkpoints,
            "summary": {
                "miles_by_level": {level.key: round(miles, 2) for level, miles in summary.miles_by_level.items()},
                "total_miles": round(summary.total_miles, 2),
                "average_risk": round(summary.average_risk, 3),
                "worst_level": summary.worst_level.key,
                "worst_checkpoint_index": summary.worst_checkpoint_index,
                "no_travel": summary.no_travel,
            },
        }

    @staticmethod
    def _heatmap(
        prepared: Sequence[_PreparedRoute], forecasts: dict[Cell, HourlyForecast], req: PlanRequest
    ) -> dict[str, Any]:
        """Risk level at every unique checkpoint for each hour from departure to departure + 48 h."""
        hours = [req.departure_time + timedelta(hours=h) for h in range(HEATMAP_HOURS + 1)]
        points: list[dict[str, Any]] = []
        seen: set[Cell] = set()
        for p in prepared:
            for s in p.checkpoints:
                cell = _cell(s.lat, s.lon)
                if cell in seen:
                    continue
                seen.add(cell)
                forecast = forecasts[cell]
                levels = [assess(forecast.sample_at(when), req.load_weight_lb).level.value for when in hours]
                points.append({"lat": round(s.lat, 5), "lon": round(s.lon, 5), "levels": levels})
        return {
            "interval_miles": req.sample_interval_miles,
            "hours": [when.isoformat() for when in hours],
            "points": points,
        }


def _place_payload(place: GeocodeResult) -> dict[str, Any]:
    return {"query": place.query, "name": place.name, "lat": place.lat, "lon": place.lon}
