from rest_framework.test import APIClient


def test_health_returns_ok():
    response = APIClient().get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "spotter-routing-api"
    assert isinstance(body["tomtom_key_configured"], bool)
