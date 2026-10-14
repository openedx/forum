"""Tests that the forum HTTP API is reachable only by a trusted service."""

import importlib
from typing import Any, Generator, cast

import pytest
from django.contrib.auth.models import (  # pylint: disable=E5142
    AnonymousUser,
    User,
)
from django.test import Client, override_settings
from django.urls import URLPattern, URLResolver, clear_url_caches
from rest_framework.request import Request
from rest_framework.views import APIView

import forum.urls
from forum.permissions import IsForumServiceUser
from forum.views.base import ForumAPIView

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def restore_urlconf() -> Generator[None, None, None]:
    """Reload the URLconf after each test so module-level state does not leak."""
    yield
    clear_url_caches()
    importlib.reload(forum.urls)


def routed_views() -> list[tuple[str, Any]]:
    """Return (route, view class) for every endpoint the URLconf exposes."""
    with override_settings(FORUM_ENABLE_HTTP_API=True):
        clear_url_caches()
        patterns = importlib.reload(forum.urls).urlpatterns

    found: list[tuple[str, Any]] = []

    def walk(entries: Any, prefix: str) -> None:
        for entry in entries:
            if isinstance(entry, URLResolver):
                walk(entry.url_patterns, prefix + str(entry.pattern))
            elif isinstance(entry, URLPattern):
                view = getattr(entry.callback, "view_class", None)
                if view is not None:
                    found.append((prefix + str(entry.pattern), view))

    walk(patterns, "")
    return found


def test_urlconf_exposes_views() -> None:
    """Guard the guard: the checks below are meaningless on an empty URLconf."""
    assert len(routed_views()) > 0


@pytest.mark.parametrize(("route", "view"), routed_views(), ids=str)
def test_every_routed_view_requires_a_service_caller(route: str, view: Any) -> None:
    """No endpoint may widen access beyond the base class permission."""
    assert issubclass(view, ForumAPIView), f"{route} does not use ForumAPIView"
    assert view.permission_classes == (
        IsForumServiceUser,
    ), f"{route} overrides permission_classes to {view.permission_classes}"


def test_anonymous_caller_is_rejected() -> None:
    """An anonymous request must not be allowed through."""
    assert allows(AnonymousUser()) is False


def test_ordinary_learner_is_rejected() -> None:
    """A signed-in learner is not a trusted service, even though they are real."""
    assert allows(User.objects.create(username="learner", is_staff=False)) is False


def test_staff_service_account_is_allowed() -> None:
    """A staff service account is the intended caller."""
    assert allows(User.objects.create(username="service", is_staff=True)) is True


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/v1/users/1/replace_username"),
        ("post", "/api/v1/users/1/retire"),
        ("get", "/api/v1/threads/1"),
        ("delete", "/api/v1/threads/1"),
    ],
)
def test_endpoints_reject_anonymous_callers_end_to_end(
    client: Client, method: str, path: str
) -> None:
    """With the API routed, anonymous callers still get shut out."""
    with override_settings(FORUM_ENABLE_HTTP_API=True, ROOT_URLCONF="forum.urls"):
        clear_url_caches()
        importlib.reload(forum.urls)
        response = getattr(client, method)(path)
        assert response.status_code in (
            401,
            403,
        ), f"{method.upper()} {path} returned {response.status_code}"


def test_learner_cannot_act_as_another_user(client: Client) -> None:
    """The impersonation path the parameter-based contract would otherwise open."""
    victim = User.objects.create(pk=4242, username="victim")
    learner = User.objects.create(username="opportunist", is_staff=False)
    client.force_login(learner)

    with override_settings(FORUM_ENABLE_HTTP_API=True, ROOT_URLCONF="forum.urls"):
        clear_url_caches()
        importlib.reload(forum.urls)
        response = client.post(
            "/api/v1/users/4242/replace_username",
            data='{"new_username": "hacked"}',
            content_type="application/json",
        )

    assert response.status_code in (401, 403)
    victim.refresh_from_db()
    assert victim.username == "victim"


def allows(user: Any) -> bool:
    """Run the permission against a stand-in request carrying just this user."""
    request = cast(Request, type("StubRequest", (), {"user": user})())
    return IsForumServiceUser().has_permission(request, APIView())
