"""
TomTom client: request construction, response parsing and error mapping.
All HTTP goes through httpx.MockTransport, so nothing touches the network.
"""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from providers.errors import (
    GeocodeNotFound,
    ProviderBadRequest,
    ProviderQuotaExceeded,
    ProviderUnavailable,
    RouteNotFound,
)
from providers.tomtom import TomTomClient
from routing.sampling import ProgressEntry

DEPART = datetime(2026, 10, 11, 8, 0, tzinfo=timezone(timedelta(hours=-5)))
ORIGIN = (41.8832, -87.6324)
DEST = (39.7385, -104.9849)

GEOCODE_BODY = {
    "summary": {"query": "chicago, il", "numResults": 1},
    "results": [
        {
            "type": "Geography",
            "position": {"lat": 41.8832, "lon": -87.6324},
            "address": {"freeformAddress": "Chicago, IL", "country": "United States"},
        }
    ],
}


def route_body(n_routes=2):
    def one(offset):
        return {
            "summary": {
                "lengthInMeters": 160934 + offset,
                "travelTimeInSeconds": 7200 + offset,
                "trafficDelayInSeconds": 120,
                "departureTime": "2026-10-11T08:00:00-05:00",
                "arrivalTime": "2026-10-11T10:00:00-05:00",
            },
            "legs": [
                {
                    "points": [
                        {"latitude": 41.0, "longitude": -87.0},
                        {"latitude": 41.5, "longitude": -87.0},
                        {"latitude": 42.0, "longitude": -87.0},
                    ]
                }
            ],
            "progress": [
                {"pointIndex": 0, "travelTimeInSeconds": 0, "distanceInMeters": 0},
                {"pointIndex": 2, "travelTimeInSeconds": 7200 + offset, "distanceInMeters": 160934 + offset},
            ],
            "sections": [],
        }

    return {"formatVersion": "0.0.12", "routes": [one(i * 1000) for i in range(n_routes)]}


def client_with(handler):
    return TomTomClient("test-key", transport=httpx.MockTransport(handler))


def respond(status, body=None):
    def handler(request):
        return httpx.Response(status, json=body if body is not None else {})

    return handler


# --- Construction -----------------------------------------------------------


def test_missing_api_key_is_rejected():
    with pytest.raises(ValueError):
        TomTomClient("")


# --- Geocoding --------------------------------------------------------------


def test_geocode_parses_first_result_and_sends_expected_params():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["params"] = request.url.params
        return httpx.Response(200, json=GEOCODE_BODY)

    result = client_with(handler).geocode("Chicago, IL")

    assert (result.name, result.lat, result.lon) == ("Chicago, IL", 41.8832, -87.6324)
    assert result.query == "Chicago, IL"
    assert "/search/2/geocode/Chicago%2C%20IL.json" in seen["url"]
    assert seen["params"]["key"] == "test-key"
    assert seen["params"]["countrySet"] == "US"
    assert seen["params"]["limit"] == "1"


def test_geocode_with_no_results_raises_geocode_not_found():
    body = {"summary": {"numResults": 0}, "results": []}
    with pytest.raises(GeocodeNotFound) as excinfo:
        client_with(respond(200, body)).geocode("Nowhereville ZZ")
    assert "Nowhereville ZZ" in str(excinfo.value)
    assert "US only" in str(excinfo.value)  # the driver should learn why a real foreign city is "not found"


@pytest.mark.parametrize(
    "status, exc",
    [
        (403, ProviderQuotaExceeded),
        (429, ProviderQuotaExceeded),
        (500, ProviderUnavailable),
        (503, ProviderUnavailable),
    ],
)
def test_geocode_http_errors_map_to_provider_errors(status, exc):
    with pytest.raises(exc):
        client_with(respond(status, {"detailedError": {"message": "nope"}})).geocode("Chicago, IL")


@pytest.mark.parametrize("error", [httpx.ReadTimeout, httpx.ConnectError])
def test_geocode_transport_errors_map_to_unavailable(error):
    def handler(request):
        raise error("boom", request=request)

    with pytest.raises(ProviderUnavailable):
        client_with(handler).geocode("Chicago, IL")


# --- Routing ----------------------------------------------------------------


def test_routes_sends_truck_request_with_alternatives_and_progress_data():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["params"] = request.url.params
        return httpx.Response(200, json=route_body())

    client_with(handler).routes(ORIGIN, DEST, DEPART, max_alternatives=2)

    assert "/routing/1/calculateRoute/41.8832,-87.6324:39.7385,-104.9849/json" in seen["url"]
    p = seen["params"]
    assert p["key"] == "test-key"
    assert p["travelMode"] == "truck"
    assert p["routeType"] == "fastest"
    assert p["traffic"] == "true"
    assert p["maxAlternatives"] == "2"
    assert p["departAt"] == "2026-10-11T08:00:00-05:00"
    assert p.get_list("extendedRouteRepresentation") == ["distance", "travelTime"]


def test_routes_parses_each_route():
    routes = client_with(respond(200, route_body(2))).routes(ORIGIN, DEST, DEPART)

    assert [r.provider_index for r in routes] == [0, 1]
    first = routes[0]
    assert first.points == [(41.0, -87.0), (41.5, -87.0), (42.0, -87.0)]
    assert first.length_meters == 160934
    assert first.travel_seconds == 7200
    assert first.traffic_delay_seconds == 120
    assert first.departure_time == "2026-10-11T08:00:00-05:00"
    assert first.arrival_time == "2026-10-11T10:00:00-05:00"
    assert first.progress == [ProgressEntry(0, 0), ProgressEntry(2, 7200)]
    assert routes[1].travel_seconds == 8200


def test_routes_requires_timezone_aware_departure():
    with pytest.raises(ValueError):
        client_with(respond(200, route_body())).routes(ORIGIN, DEST, datetime(2026, 10, 11, 8, 0))


def test_routes_no_route_found_maps_to_route_not_found():
    body = {"detailedError": {"code": "NO_ROUTE_FOUND", "message": "No route found"}}
    with pytest.raises(RouteNotFound):
        client_with(respond(400, body)).routes(ORIGIN, DEST, DEPART)


def test_routes_other_bad_input_maps_to_provider_bad_request():
    body = {"detailedError": {"code": "BAD_INPUT", "message": "Invalid extendedRouteRepresentation"}}
    with pytest.raises(ProviderBadRequest) as excinfo:
        client_with(respond(400, body)).routes(ORIGIN, DEST, DEPART)
    assert "Invalid extendedRouteRepresentation" in str(excinfo.value)


def test_routes_empty_list_maps_to_route_not_found():
    with pytest.raises(RouteNotFound):
        client_with(respond(200, {"routes": []})).routes(ORIGIN, DEST, DEPART)


def test_routes_quota_and_server_errors():
    with pytest.raises(ProviderQuotaExceeded):
        client_with(respond(403)).routes(ORIGIN, DEST, DEPART)
    with pytest.raises(ProviderUnavailable):
        client_with(respond(502)).routes(ORIGIN, DEST, DEPART)
