"""Process-wide planner instance wired to the real providers and the Django cache."""

from __future__ import annotations

from django.conf import settings
from django.core.cache import cache

from providers.errors import ProviderUnavailable
from providers.openmeteo import OpenMeteoClient
from providers.tomtom import TomTomClient

from .planner import Planner

_planner: Planner | None = None


def get_planner() -> Planner:
    global _planner
    if _planner is None:
        if not settings.TOMTOM_API_KEY:
            raise ProviderUnavailable("TomTom API key is not configured on the server.", provider="TomTom")
        timeout = settings.PROVIDER_TIMEOUT_SECONDS
        _planner = Planner(
            tomtom=TomTomClient(settings.TOMTOM_API_KEY, base_url=settings.TOMTOM_BASE_URL, timeout=timeout),
            weather=OpenMeteoClient(base_url=settings.OPEN_METEO_BASE_URL, timeout=timeout),
            cache=cache,
        )
    return _planner


def reset_planner() -> None:
    """For tests and settings changes."""
    global _planner
    _planner = None
