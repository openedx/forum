"""Tests for routing of the legacy forum HTTP API."""

import importlib
from typing import Any, Generator

import pytest
from django.test import Client, override_settings
from django.urls import clear_url_caches

import forum.urls

# A representative sample of the endpoints that must not be routed by default.
# ``replace_username`` is the sharpest of them: it renames the platform user,
# which is how a forum endpoint can escalate into an identity-provider problem.
SENSITIVE_PATHS = [
    ("post", "/api/v1/users/1/replace_username"),
    ("post", "/api/v2/users/1/replace_username"),
    ("post", "/api/v1/users/1/retire"),
    ("post", "/api/v1/users"),
    ("get", "/api/v1/threads/1"),
    ("delete", "/api/v1/threads/1"),
    ("delete", "/api/v2/threads/1"),
    ("delete", "/api/v1/users/1/posts"),
]


@pytest.fixture(autouse=True)
def restore_urlconf() -> Generator[None, None, None]:
    """Reload the URLconf after each test so module-level state does not leak."""
    yield
    clear_url_caches()
    importlib.reload(forum.urls)


def reload_urlpatterns() -> list[Any]:
    """Re-evaluate the URLconf under the currently active settings."""
    clear_url_caches()
    return importlib.reload(forum.urls).urlpatterns


def test_http_api_is_not_routed_by_default() -> None:
    """The legacy HTTP API must not be routed unless explicitly enabled."""
    with override_settings(FORUM_ENABLE_HTTP_API=False):
        assert reload_urlpatterns() == []


def test_http_api_is_routed_when_enabled() -> None:
    """Operators who opt in still get the endpoints."""
    with override_settings(FORUM_ENABLE_HTTP_API=True):
        assert reload_urlpatterns() != []


def test_http_api_fails_closed_when_setting_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A settings module that never defines the flag must not route the API."""
    monkeypatch.setattr(forum.urls, "settings", object())
    assert forum.urls.http_api_enabled() is False


@pytest.mark.parametrize(("method", "path"), SENSITIVE_PATHS)
def test_sensitive_endpoints_are_unreachable_by_default(
    client: Client, method: str, path: str
) -> None:
    """With the API unrouted, these endpoints must not resolve at all.

    Callers are additionally required to authenticate as a staff service
    account once the API *is* routed; see ``tests/test_permissions.py``.
    """
    with override_settings(FORUM_ENABLE_HTTP_API=False, ROOT_URLCONF="forum.urls"):
        reload_urlpatterns()
        response = getattr(client, method)(path)
        assert response.status_code == 404
