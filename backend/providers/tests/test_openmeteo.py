"""
Open-Meteo client: batched hourly forecasts in the PDF's units, nearest-hour
lookup, chunking of large batches, and error mapping. No network.
"""

from datetime import UTC, datetime

import httpx
import pytest

from providers.errors import ProviderBadRequest, ProviderQuotaExceeded, ProviderUnavailable
from providers.openmeteo import OpenMeteoClient

T0 = 1_791_504_000  # an hour boundary, unix seconds UTC


def body(lat=41.88, lon=-87.63):
    return {
        "latitude": lat,
        "longitude": lon,
        "hourly_units": {"wind_speed_10m": "mp/h", "rain": "inch", "snowfall": "inch"},
        "hourly": {
            "time": [T0, T0 + 3600, T0 + 7200],
            "wind_speed_10m": [5.5, 30.2, 60.0],
            "wind_gusts_10m": [8.0, 40.0, 75.0],
            "rain": [0.0, 0.3, None],
            "snowfall": [0.0, 0.0, 1.5],
        },
    }


def client_with(handler):
    return OpenMeteoClient(transport=httpx.MockTransport(handler))


def respond(status, payload):
    def handler(request):
        return httpx.Response(status, json=payload)

    return handler


def at(unix):
    return datetime.fromtimestamp(unix, tz=UTC)


# --- Request construction ---------------------------------------------------


def test_hourly_sends_batched_coordinates_in_pdf_units():
    seen = {}

    def handler(request):
        seen["params"] = request.url.params
        return httpx.Response(200, json=[body(41.8832, -87.6324), body(39.7385, -104.9849)])

    forecasts = client_with(handler).hourly([(41.8832, -87.6324), (39.7385, -104.9849)], forecast_days=3)

    p = seen["params"]
    assert p["latitude"] == "41.8832,39.7385"
    assert p["longitude"] == "-87.6324,-104.9849"
    assert p["hourly"] == "wind_speed_10m,wind_gusts_10m,rain,snowfall"
    assert p["wind_speed_unit"] == "mph"
    assert p["precipitation_unit"] == "inch"
    assert p["timeformat"] == "unixtime"
    assert p["timezone"] == "UTC"
    assert p["forecast_days"] == "3"
    assert len(forecasts) == 2


def test_coordinates_are_rounded_to_four_decimals():
    seen = {}

    def handler(request):
        seen["params"] = request.url.params
        return httpx.Response(200, json=body())

    client_with(handler).hourly([(41.88321234, -87.63245678)], forecast_days=1)
    assert seen["params"]["latitude"] == "41.8832"
    assert seen["params"]["longitude"] == "-87.6325"


def test_single_location_object_response_is_normalized_to_a_list():
    forecasts = client_with(respond(200, body())).hourly([(41.88, -87.63)], forecast_days=1)
    assert len(forecasts) == 1
    assert forecasts[0].wind_mph == [5.5, 30.2, 60.0]


def test_null_values_are_treated_as_zero():
    forecasts = client_with(respond(200, body())).hourly([(41.88, -87.63)], forecast_days=1)
    assert forecasts[0].rain_in[2] == 0.0


def test_large_batches_are_chunked_and_order_preserved():
    calls = []

    def handler(request):
        lats = request.url.params["latitude"].split(",")
        calls.append(len(lats))
        return httpx.Response(200, json=[body(float(lat), -100.0) for lat in lats])

    n = OpenMeteoClient.MAX_LOCATIONS_PER_REQUEST * 2 + 50
    points = [(30.0 + i * 0.01, -100.0) for i in range(n)]
    forecasts = client_with(handler).hourly(points, forecast_days=2)

    assert calls == [OpenMeteoClient.MAX_LOCATIONS_PER_REQUEST, OpenMeteoClient.MAX_LOCATIONS_PER_REQUEST, 50]
    assert len(forecasts) == n
    assert forecasts[0].latitude == pytest.approx(30.0)
    assert forecasts[-1].latitude == pytest.approx(30.0 + (n - 1) * 0.01)


@pytest.mark.parametrize("forecast_days", [0, 17])
def test_forecast_days_must_be_within_open_meteo_limits(forecast_days):
    with pytest.raises(ValueError):
        client_with(respond(200, body())).hourly([(41.88, -87.63)], forecast_days=forecast_days)


def test_empty_point_list_is_rejected():
    with pytest.raises(ValueError):
        client_with(respond(200, body())).hourly([], forecast_days=1)


# --- Nearest-hour lookup ----------------------------------------------------


def test_sample_at_picks_the_nearest_forecast_hour():
    forecast = client_with(respond(200, body())).hourly([(41.88, -87.63)], forecast_days=1)[0]

    sample = forecast.sample_at(at(T0 + 3600 + 1700))  # 28 min past hour 1 -> hour 1
    assert (sample.wind_mph, sample.gust_mph, sample.rain_in_hr, sample.snow_in_hr) == (30.2, 40.0, 0.3, 0.0)

    sample = forecast.sample_at(at(T0 + 3600 + 1801))  # 30 min + 1 s -> hour 2
    assert sample.wind_mph == 60.0


def test_sample_at_clamps_outside_the_forecast_window():
    forecast = client_with(respond(200, body())).hourly([(41.88, -87.63)], forecast_days=1)[0]
    assert forecast.sample_at(at(T0 - 90_000)).wind_mph == 5.5
    assert forecast.sample_at(at(T0 + 90_000)).wind_mph == 60.0


def test_covers_reports_whether_a_time_is_inside_the_window():
    forecast = client_with(respond(200, body())).hourly([(41.88, -87.63)], forecast_days=1)[0]
    assert forecast.covers(at(T0 + 100))
    assert forecast.covers(at(T0 + 7200 + 1799))
    assert not forecast.covers(at(T0 + 7200 + 1801))
    assert not forecast.covers(at(T0 - 1801))


# --- Errors -----------------------------------------------------------------


def test_bad_request_includes_open_meteo_reason():
    with pytest.raises(ProviderBadRequest) as excinfo:
        client_with(respond(400, {"error": True, "reason": "Latitude must be in range"})).hourly(
            [(41.88, -87.63)], forecast_days=1
        )
    assert "Latitude must be in range" in str(excinfo.value)


def test_quota_and_server_errors():
    with pytest.raises(ProviderQuotaExceeded):
        client_with(respond(429, {"error": True, "reason": "Minutely API request limit exceeded"})).hourly(
            [(41.88, -87.63)], forecast_days=1
        )
    with pytest.raises(ProviderUnavailable):
        client_with(respond(503, {})).hourly([(41.88, -87.63)], forecast_days=1)


def test_transport_error_maps_to_unavailable():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderUnavailable):
        client_with(handler).hourly([(41.88, -87.63)], forecast_days=1)
