"""Production settings (gunicorn behind nginx)."""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import ALLOWED_HOSTS, BASE_DIR, SECRET_KEY

DEBUG = False

if SECRET_KEY == "dev-only-insecure-secret-key":
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set in production.")
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set in production.")
# The Docker healthcheck calls the API over loopback from inside the container.
ALLOWED_HOSTS = list(dict.fromkeys([*ALLOWED_HOSTS, "127.0.0.1", "localhost"]))

# File-based cache so every gunicorn worker shares cached provider responses.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": os.environ.get("DJANGO_CACHE_DIR", str(BASE_DIR / ".cache")),
        "OPTIONS": {"MAX_ENTRIES": 5000},
    }
}

# nginx terminates HTTP in front of gunicorn.
USE_X_FORWARDED_HOST = True
SECURE_CONTENT_TYPE_NOSNIFF = True
