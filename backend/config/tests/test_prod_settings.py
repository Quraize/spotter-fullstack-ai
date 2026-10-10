"""
The production settings are the deployment contract: they must refuse to start
without a real secret and host list, share the provider cache across gunicorn
workers, and always accept the loopback host the Docker healthcheck uses.
"""

import importlib
import sys

import pytest
from django.core.exceptions import ImproperlyConfigured

PROD_ENV = {
    "DJANGO_SECRET_KEY": "a-real-secret-for-tests",
    "DJANGO_ALLOWED_HOSTS": "203.0.113.10, example.internal",
    "TOMTOM_API_KEY": "key",
}


def load_prod(monkeypatch, **overrides):
    env = {**PROD_ENV, **overrides}
    for key in ("DJANGO_SECRET_KEY", "DJANGO_ALLOWED_HOSTS", "DJANGO_CACHE_DIR", "TOMTOM_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        if value is not None:
            monkeypatch.setenv(key, value)
    for name in ("config.settings.base", "config.settings.prod"):
        sys.modules.pop(name, None)
    importlib.import_module("config.settings.base")
    return importlib.import_module("config.settings.prod")


def test_prod_is_not_debug_and_uses_a_shared_file_cache(monkeypatch, tmp_path):
    prod = load_prod(monkeypatch, DJANGO_CACHE_DIR=str(tmp_path / "cache"))
    assert prod.DEBUG is False
    assert prod.CACHES["default"]["BACKEND"].endswith("FileBasedCache")
    assert prod.CACHES["default"]["LOCATION"] == str(tmp_path / "cache")
    assert prod.USE_X_FORWARDED_HOST is True


def test_allowed_hosts_are_trimmed_and_always_include_loopback(monkeypatch):
    prod = load_prod(monkeypatch)
    assert "203.0.113.10" in prod.ALLOWED_HOSTS
    assert "example.internal" in prod.ALLOWED_HOSTS  # the space after the comma must not survive
    assert " example.internal" not in prod.ALLOWED_HOSTS
    # The Docker healthcheck calls http://127.0.0.1:8000/api/health from inside the container.
    assert "127.0.0.1" in prod.ALLOWED_HOSTS
    assert "localhost" in prod.ALLOWED_HOSTS


def test_refuses_to_start_with_the_dev_secret(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
        load_prod(monkeypatch, DJANGO_SECRET_KEY=None)


def test_refuses_to_start_without_allowed_hosts(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="DJANGO_ALLOWED_HOSTS"):
        load_prod(monkeypatch, DJANGO_ALLOWED_HOSTS=None)


@pytest.fixture(autouse=True)
def restore_settings_modules():
    """Importing prod settings replaces modules in sys.modules; put the dev ones back for other tests."""
    yield
    for name in ("config.settings.base", "config.settings.prod"):
        sys.modules.pop(name, None)
    importlib.import_module("config.settings.base")
