"""
Open-Meteo hourly forecasts for many locations in one request, in the PDF's
units: wind in mph, rain and snowfall in inches per hour (preceding-hour sums).

Docs: https://open-meteo.com/en/docs
No API key. Free tier: 600 calls/min, 10,000/day, non-commercial.
"""

from __future__ import annotations

import bisect
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from routing.risk import WeatherSample
from routing.sampling import LatLon

from ._http import build_client, get_json
from .errors import ProviderBadRequest, ProviderQuotaExceeded, ProviderUnavailable

logger = logging.getLogger(__name__)

PROVIDER = "Open-Meteo"
DEFAULT_BASE_URL = "https://api.open-meteo.com"
HOURLY_VARIABLES = ("wind_speed_10m", "wind_gusts_10m", "rain", "snowfall")
MAX_FORECAST_DAYS = 16
HALF_HOUR_SECONDS = 1800


@dataclass(frozen=True)
class HourlyForecast:
    latitude: float
    longitude: float
    times: list[int]  # unix seconds, UTC, hourly
    wind_mph: list[float]
    gust_mph: list[float]
    rain_in: list[float]  # inches in the preceding hour
    snow_in: list[float]  # inches in the preceding hour

    def nearest_index(self, when: datetime) -> int:
        ts = when.timestamp()
        i = bisect.bisect_left(self.times, ts)
        candidates = [j for j in (i - 1, i) if 0 <= j < len(self.times)]
        return min(candidates, key=lambda j: abs(self.times[j] - ts))

    def covers(self, when: datetime) -> bool:
        """True when `when` is within half an hour of a forecast hour in the window."""
        ts = when.timestamp()
        return self.times[0] - HALF_HOUR_SECONDS <= ts <= self.times[-1] + HALF_HOUR_SECONDS

    def sample_at(self, when: datetime) -> WeatherSample:
        """Weather at the forecast hour nearest to `when` (clamped to the window)."""
        i = self.nearest_index(when)
        return WeatherSample(
            wind_mph=self.wind_mph[i],
            rain_in_hr=self.rain_in[i],
            snow_in_hr=self.snow_in[i],
            gust_mph=self.gust_mph[i],
        )


class OpenMeteoClient:
    # 300 locations per request worked in testing; stay comfortably below that.
    MAX_LOCATIONS_PER_REQUEST = 200

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self._http = build_client(base_url, timeout, transport)

    def hourly(self, points: Sequence[LatLon], forecast_days: int) -> list[HourlyForecast]:
        """One HourlyForecast per input point, in input order. Starts at 00:00 UTC today."""
        if not points:
            raise ValueError("at least one point is required")
        if not 1 <= forecast_days <= MAX_FORECAST_DAYS:
            raise ValueError(f"forecast_days must be between 1 and {MAX_FORECAST_DAYS}")
        forecasts: list[HourlyForecast] = []
        size = self.MAX_LOCATIONS_PER_REQUEST
        for start in range(0, len(points), size):
            forecasts.extend(self._fetch(points[start : start + size], forecast_days))
        return forecasts

    def _fetch(self, points: Sequence[LatLon], forecast_days: int) -> list[HourlyForecast]:
        params = {
            "latitude": ",".join(f"{lat:.4f}" for lat, _ in points),
            "longitude": ",".join(f"{lon:.4f}" for _, lon in points),
            "hourly": ",".join(HOURLY_VARIABLES),
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timeformat": "unixtime",
            "timezone": "UTC",
            "forecast_days": forecast_days,
        }
        status, payload = get_json(self._http, PROVIDER, "/v1/forecast", params)
        self._raise_for_status(status, payload)
        items = payload if isinstance(payload, list) else [payload]
        if len(items) != len(points):
            raise ProviderBadRequest(
                f"Open-Meteo returned {len(items)} locations for {len(points)} requested", provider=PROVIDER
            )
        return [self._parse(item) for item in items]

    @staticmethod
    def _raise_for_status(status: int, payload: Any) -> None:
        if status < 400:
            return
        reason = (payload or {}).get("reason") if isinstance(payload, dict) else None
        reason = reason or f"HTTP {status}"
        if status == 429:
            raise ProviderQuotaExceeded(f"Open-Meteo rate limit exceeded ({reason})", provider=PROVIDER)
        if status >= 500:
            raise ProviderUnavailable(f"Open-Meteo is unavailable ({reason})", provider=PROVIDER)
        raise ProviderBadRequest(f"Open-Meteo rejected the request ({reason})", provider=PROVIDER)

    @staticmethod
    def _parse(item: dict[str, Any]) -> HourlyForecast:
        hourly = item["hourly"]
        nulls = 0

        def floats(name: str) -> list[float]:
            nonlocal nulls
            out = []
            for v in hourly[name]:
                if v is None:
                    nulls += 1
                    out.append(0.0)
                else:
                    out.append(float(v))
            return out

        forecast = HourlyForecast(
            latitude=float(item["latitude"]),
            longitude=float(item["longitude"]),
            times=[int(t) for t in hourly["time"]],
            wind_mph=floats("wind_speed_10m"),
            gust_mph=floats("wind_gusts_10m"),
            rain_in=floats("rain"),
            snow_in=floats("snowfall"),
        )
        if nulls:
            logger.warning(
                "Open-Meteo returned %d null values at (%.4f, %.4f); treated as 0",
                nulls,
                forecast.latitude,
                forecast.longitude,
            )
        return forecast
