"""
POST /api/plan: request validation, error mapping and pass-through of the
planner result. The planner itself is faked here; see test_planner.py.
"""

from datetime import datetime, timedelta, timezone

import pytest
from rest_framework.test import APIClient

from api.planner import PlanningError, TooManyCheckpoints
from providers.errors import GeocodeNotFound, ProviderQuotaExceeded, ProviderUnavailable, RouteNotFound

TZ = timezone(timedelta(hours=-5))


def in_hours(hours):
    return (datetime.now(TZ) + timedelta(hours=hours)).replace(microsecond=0).isoformat()


def valid_body(**overrides):
    body = {
        "origin": "Chicago, IL",
        "destination": "Denver, CO",
        "departure_time": in_hours(2),
        "load_weight_lb": 42_000,
        "sample_interval_miles": 25,
    }
    body.update(overrides)
    return body


class FakePlanner:
    def __init__(self):
        self.requests = []
        self.result = {"routes": [], "recommended_route_id": None, "heatmap": {}, "warnings": []}
        self.error = None

    def plan(self, req):
        self.requests.append(req)
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def fake_planner(monkeypatch):
    fake = FakePlanner()
    monkeypatch.setattr("api.views.get_planner", lambda: fake)
    return fake


@pytest.fixture
def client():
    return APIClient()


def post(client, body):
    return client.post("/api/plan", body, format="json")


# --- Happy path -------------------------------------------------------------


def test_valid_request_is_passed_to_the_planner(client, fake_planner):
    body = valid_body()
    response = post(client, body)

    assert response.status_code == 200
    assert response.json() == fake_planner.result
    req = fake_planner.requests[0]
    assert req.origin == "Chicago, IL"
    assert req.destination == "Denver, CO"
    assert req.departure_time == datetime.fromisoformat(body["departure_time"])
    assert req.departure_time.utcoffset() == timedelta(hours=-5)
    assert req.load_weight_lb == 42_000
    assert req.sample_interval_miles == 25


def test_interval_accepts_numeric_strings(client, fake_planner):
    assert post(client, valid_body(sample_interval_miles="50")).status_code == 200
    assert fake_planner.requests[0].sample_interval_miles == 50


def test_whitespace_is_trimmed_from_place_names(client, fake_planner):
    post(client, valid_body(origin="  Chicago, IL  "))
    assert fake_planner.requests[0].origin == "Chicago, IL"


# --- Validation -------------------------------------------------------------


@pytest.mark.parametrize(
    "field", ["origin", "destination", "departure_time", "load_weight_lb", "sample_interval_miles"]
)
def test_missing_field_is_reported(client, fake_planner, field):
    body = valid_body()
    del body[field]
    response = post(client, body)
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert field in error["fields"]
    assert fake_planner.requests == []


@pytest.mark.parametrize(
    "departure_time, hint",
    [
        ("2026-10-11T08:00:00", "offset"),  # naive
        ("next tuesday", "ISO"),
        (in_hours(-3), "past"),
        (in_hours(24 * 20), "14 days"),
    ],
)
def test_departure_time_rules(client, fake_planner, departure_time, hint):
    response = post(client, valid_body(departure_time=departure_time))
    assert response.status_code == 400
    message = " ".join(response.json()["error"]["fields"]["departure_time"])
    assert hint.lower() in message.lower()


def test_departure_within_the_last_hour_is_allowed(client, fake_planner):
    assert post(client, valid_body(departure_time=in_hours(-0.5))).status_code == 200


@pytest.mark.parametrize("interval", [15, 0, "ten"])
def test_interval_must_be_10_25_or_50(client, fake_planner, interval):
    response = post(client, valid_body(sample_interval_miles=interval))
    assert response.status_code == 400
    assert "sample_interval_miles" in response.json()["error"]["fields"]


@pytest.mark.parametrize("load", [0, -5, 500_000, "heavy"])
def test_load_weight_must_be_a_sensible_positive_number(client, fake_planner, load):
    response = post(client, valid_body(load_weight_lb=load))
    assert response.status_code == 400
    assert "load_weight_lb" in response.json()["error"]["fields"]


def test_place_names_must_not_be_blank(client, fake_planner):
    response = post(client, valid_body(origin="   "))
    assert response.status_code == 400
    assert "origin" in response.json()["error"]["fields"]


# --- Error mapping ----------------------------------------------------------


@pytest.mark.parametrize(
    "error, status, code",
    [
        (GeocodeNotFound("No location found for 'Atlantis'", provider="TomTom"), 422, "geocode_not_found"),
        (RouteNotFound("No truck route found", provider="TomTom"), 422, "route_not_found"),
        (ProviderQuotaExceeded("quota", provider="TomTom"), 503, "provider_quota_exceeded"),
        (ProviderUnavailable("down", provider="Open-Meteo"), 503, "provider_unavailable"),
        (PlanningError("Origin and destination resolve to the same place."), 422, "invalid_trip"),
        (TooManyCheckpoints("Too many weather locations."), 422, "too_many_checkpoints"),
    ],
)
def test_planner_errors_become_structured_responses(client, fake_planner, error, status, code):
    fake_planner.error = error
    response = post(client, valid_body())
    assert response.status_code == status
    assert response.json()["error"] == {"code": code, "message": str(error)}


def test_missing_tomtom_key_is_reported_as_unavailable(client, settings):
    from api import services

    settings.TOMTOM_API_KEY = ""
    services.reset_planner()
    response = post(client, valid_body())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_unavailable"
    assert "TomTom" in response.json()["error"]["message"]


def test_get_is_not_allowed(client):
    assert client.get("/api/plan").status_code == 405
