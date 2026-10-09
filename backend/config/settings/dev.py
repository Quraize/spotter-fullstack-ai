"""Local development settings."""

from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# The Vite dev server proxies /api to Django, so CORS is only needed when the
# API is called directly from the Vite origin.
CORS_ALLOWED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

# Some developer machines sit behind a TLS-inspecting proxy whose root certificate
# is only in the OS store. truststore makes Python's SSL use that store.
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:  # pragma: no cover
    pass
