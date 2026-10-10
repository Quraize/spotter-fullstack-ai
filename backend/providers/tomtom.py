"""
TomTom Routing API (truck mode, alternatives, per-point progress data) and
Geocoding API. Called only from the backend so the key never reaches the browser.

Routing docs: https://docs.tomtom.com/routing-api/documentation/tomtom-maps/calculate-route
Geocoding docs: https://docs.tomtom.com/geocoding-api/
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from routing.sampling import LatLon, ProgressEntry

from ._http import build_client, get_json
from .errors import (
    GeocodeNotFound,
    ProviderBadRequest,
    ProviderQuotaExceeded,
    ProviderUnavailable,
    RouteNotFound,
)

PROVIDER = "TomTom"
DEFAULT_BASE_URL = "https://api.tomtom.com"


@dataclass(frozen=True)
class GeocodeResult:
    query: str
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class RouteResult:
    provider_index: int  # 0 is TomTom's primary (fastest) route
    points: list[LatLon]
    length_meters: float
    travel_seconds: float
    traffic_delay_seconds: float
    departure_time: str  # ISO 8601 as returned by TomTom
    arrival_time: str
    progress: list[ProgressEntry]  # travel time at selected point indices


def _coord(point: LatLon) -> str:
    return f"{round(point[0], 6)!r},{round(point[1], 6)!r}"


class TomTomClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ):
        if not api_key:
            raise ValueError("TomTom API key is not configured")
        self._key = api_key
        self._http = build_client(base_url, timeout, transport)

    # --- Geocoding ----------------------------------------------------------

    def geocode(self, query: str, country: str = "US") -> GeocodeResult:
        path = f"/search/2/geocode/{quote(query, safe='')}.json"
        status, payload = get_json(self._http, PROVIDER, path, {"key": self._key, "countrySet": country, "limit": 1})
        self._raise_for_status(status, payload, what="geocoding")
        results = (payload or {}).get("results") or []
        if not results:
            raise GeocodeNotFound(f"No location found for '{query}'", provider=PROVIDER)
        first = results[0]
        return GeocodeResult(
            query=query,
            name=first["address"]["freeformAddress"],
            lat=float(first["position"]["lat"]),
            lon=float(first["position"]["lon"]),
        )

    # --- Routing ------------------------------------------------------------

    def routes(
        self,
        origin: LatLon,
        destination: LatLon,
        depart_at: datetime,
        max_alternatives: int = 2,
    ) -> list[RouteResult]:
        """Truck routes, primary first. Fewer than max_alternatives + 1 may be returned."""
        if depart_at.tzinfo is None or depart_at.utcoffset() is None:
            raise ValueError("depart_at must be timezone-aware")
        path = f"/routing/1/calculateRoute/{_coord(origin)}:{_coord(destination)}/json"
        params: dict[str, Any] = {
            "key": self._key,
            "travelMode": "truck",
            "routeType": "fastest",
            "traffic": "true",
            "maxAlternatives": max_alternatives,
            "departAt": depart_at.replace(microsecond=0).isoformat(),
            # Must be repeated, not comma-joined (verified against the live API).
            "extendedRouteRepresentation": ["distance", "travelTime"],
        }
        status, payload = get_json(self._http, PROVIDER, path, params)
        if status == 400:
            error = (payload or {}).get("detailedError") or {}
            if error.get("code") == "NO_ROUTE_FOUND":
                raise RouteNotFound("No truck route found between these locations", provider=PROVIDER)
            raise ProviderBadRequest(
                f"TomTom rejected the routing request: {error.get('message', 'bad input')}", provider=PROVIDER
            )
        self._raise_for_status(status, payload, what="routing")
        raw_routes = (payload or {}).get("routes") or []
        if not raw_routes:
            raise RouteNotFound("No truck route found between these locations", provider=PROVIDER)
        return [self._parse_route(i, raw) for i, raw in enumerate(raw_routes)]

    # --- Helpers ------------------------------------------------------------

    @staticmethod
    def _raise_for_status(status: int, payload: Any, *, what: str) -> None:
        if status < 400:
            return
        message = ((payload or {}).get("detailedError") or {}).get("message") or f"HTTP {status}"
        if status in (403, 429):
            raise ProviderQuotaExceeded(
                f"TomTom {what} quota exceeded or API key rejected ({message})", provider=PROVIDER
            )
        if status >= 500:
            raise ProviderUnavailable(f"TomTom {what} is unavailable ({message})", provider=PROVIDER)
        raise ProviderBadRequest(f"TomTom {what} request failed ({message})", provider=PROVIDER)

    @staticmethod
    def _parse_route(index: int, raw: dict[str, Any]) -> RouteResult:
        points = [(float(p["latitude"]), float(p["longitude"])) for leg in raw["legs"] for p in leg["points"]]
        summary = raw["summary"]
        progress = [
            ProgressEntry(point_index=int(p["pointIndex"]), seconds=float(p["travelTimeInSeconds"]))
            for p in raw.get("progress", [])
            if "travelTimeInSeconds" in p
        ]
        return RouteResult(
            provider_index=index,
            points=points,
            length_meters=float(summary["lengthInMeters"]),
            travel_seconds=float(summary["travelTimeInSeconds"]),
            traffic_delay_seconds=float(summary.get("trafficDelayInSeconds", 0)),
            departure_time=summary.get("departureTime", ""),
            arrival_time=summary.get("arrivalTime", ""),
            progress=progress,
        )
