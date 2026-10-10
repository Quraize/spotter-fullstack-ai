"""
Errors raised by provider clients. Each carries a stable machine-readable
code and the HTTP status the API layer should respond with, so views never
need to know provider-specific failure shapes.
"""


class ProviderError(Exception):
    code = "provider_error"
    http_status = 502

    def __init__(self, message: str, *, provider: str):
        super().__init__(message)
        self.message = message
        self.provider = provider


class GeocodeNotFound(ProviderError):
    """The place name could not be resolved to coordinates."""

    code = "geocode_not_found"
    http_status = 422


class RouteNotFound(ProviderError):
    """The routing provider found no truck route between the two points."""

    code = "route_not_found"
    http_status = 422


class ProviderQuotaExceeded(ProviderError):
    """Rate limit or daily quota hit, or the API key was rejected."""

    code = "provider_quota_exceeded"
    http_status = 503


class ProviderUnavailable(ProviderError):
    """Timeout, connection failure or 5xx from the provider."""

    code = "provider_unavailable"
    http_status = 503


class ProviderBadRequest(ProviderError):
    """The provider rejected our request as malformed (a bug on our side)."""

    code = "provider_bad_request"
    http_status = 502
