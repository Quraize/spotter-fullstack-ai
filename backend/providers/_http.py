"""Shared HTTP plumbing for provider clients."""

from __future__ import annotations

from typing import Any

import httpx

from .errors import ProviderUnavailable

USER_AGENT = "spotter-truck-routing/0.1"


def build_client(base_url: str, timeout: float, transport: httpx.BaseTransport | None) -> httpx.Client:
    return httpx.Client(base_url=base_url, timeout=timeout, transport=transport, headers={"User-Agent": USER_AGENT})


def get_json(client: httpx.Client, provider: str, path: str, params: dict[str, Any]) -> tuple[int, Any]:
    """
    GET and decode JSON. Transport-level failures become ProviderUnavailable;
    HTTP status handling is left to the caller because error bodies differ
    per provider.
    """
    try:
        response = client.get(path, params=params)
    except httpx.TimeoutException as exc:
        raise ProviderUnavailable(f"{provider} did not respond in time", provider=provider) from exc
    except httpx.TransportError as exc:
        raise ProviderUnavailable(f"{provider} is unreachable: {exc}", provider=provider) from exc
    try:
        payload = response.json()
    except ValueError:
        payload = None
    return response.status_code, payload
