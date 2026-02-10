"""
Tests for discussion ban and unban API endpoints.
"""

# mypy: ignore-errors
# pylint: disable=redefined-outer-name

from urllib.parse import quote_plus

import pytest
from django.contrib.auth import get_user_model
from opaque_keys.edx.keys import CourseKey

from forum.backends.mysql.models import DiscussionBan  # pylint: disable=import-error
from test_utils.client import APIClient  # pylint: disable=import-error

User = get_user_model()
pytestmark = pytest.mark.django_db


@pytest.fixture
def test_users():
    """Create test users for ban/unban tests."""
    learner = User.objects.create_user(
        username="test_learner", email="learner@test.com", password="password"
    )
    moderator = User.objects.create_user(
        username="test_moderator",
        email="moderator@test.com",
        password="password",
        is_staff=True,
    )
    return {"learner": learner, "moderator": moderator}


def test_ban_user_course_level(api_client: APIClient, test_users: dict) -> None:
    """Test banning a user at course level."""
    learner = test_users["learner"]
    moderator = test_users["moderator"]
    course_id = "course-v1:edX+DemoX+Demo_Course"

    data = {
        "user_id": learner.id,
        "banned_by_id": moderator.id,
        "scope": "course",
        "course_id": course_id,
        "reason": "Posting spam content",
    }

    response = api_client.post_json("/api/v2/users/bans", data=data)

    assert response.status_code == 201
    assert response.json()["user"]["id"] == learner.id
    assert response.json()["scope"] == "course"
    assert response.json()["course_id"] == course_id
    assert response.json()["is_active"] is True

    # Verify ban was created in database
    ban = DiscussionBan.objects.get(user=learner)
    assert ban.scope == "course"
    assert ban.is_active is True


def test_ban_user_org_level(api_client: APIClient, test_users: dict) -> None:
    """Test banning a user at organization level."""
    learner = test_users["learner"]
    moderator = test_users["moderator"]
    org_key = "edX"

    data = {
        "user_id": learner.id,
        "banned_by_id": moderator.id,
        "scope": "organization",
        "org_key": org_key,
        "reason": "Repeated violations across courses",
    }

    response = api_client.post_json("/api/v2/users/bans", data=data)

    assert response.status_code == 201
    assert response.json()["user"]["id"] == learner.id
    assert response.json()["scope"] == "organization"
    assert response.json()["org_key"] == org_key
    assert response.json()["course_id"] is None


def test_ban_user_missing_course_id(api_client: APIClient, test_users: dict) -> None:
    """Test banning fails when course_id is missing for course scope."""
    learner = test_users["learner"]
    moderator = test_users["moderator"]

    data = {
        "user_id": learner.id,
        "banned_by_id": moderator.id,
        "scope": "course",
        # Missing course_id
        "reason": "Test reason",
    }

    response = api_client.post_json("/api/v2/users/bans", data=data)

    assert response.status_code == 400
    assert "course_id" in str(response.json())


def test_ban_user_invalid_user_id(api_client: APIClient, test_users: dict) -> None:
    """Test banning fails with non-existent user ID."""
    moderator = test_users["moderator"]
    course_id = "course-v1:edX+DemoX+Demo_Course"

    data = {
        "user_id": 99999,  # Non-existent user
        "banned_by_id": moderator.id,
        "scope": "course",
        "course_id": course_id,
        "reason": "Test reason",
    }

    response = api_client.post_json("/api/v2/users/bans", data=data)

    assert response.status_code == 404
    assert "not found" in str(response.json()).lower()


def test_ban_reactivates_previous_ban(api_client: APIClient, test_users: dict) -> None:
    """Test that banning a previously unbanned user reactivates the ban."""
    learner = test_users["learner"]
    moderator = test_users["moderator"]
    course_id = "course-v1:edX+DemoX+Demo_Course"

    # Create an inactive ban
    ban = DiscussionBan.objects.create(
        user=learner,
        course_id=CourseKey.from_string(course_id),
        org_key="edX",
        scope="course",
        banned_by=moderator,
        is_active=False,
        reason="Old ban",
    )

    data = {
        "user_id": learner.id,
        "banned_by_id": moderator.id,
        "scope": "course",
        "course_id": course_id,
        "reason": "New ban reason",
    }

    response = api_client.post_json("/api/v2/users/bans", data=data)

    assert response.status_code == 201

    # Verify ban was reactivated
    ban.refresh_from_db()
    assert ban.is_active is True
    assert ban.reason == "New ban reason"


def test_unban_course_level_ban(api_client: APIClient, test_users: dict) -> None:
    """Test unbanning a user from a course-level ban."""
    learner = test_users["learner"]
    moderator = test_users["moderator"]
    course_id = "course-v1:edX+DemoX+Demo_Course"

    # Create active course-level ban
    ban = DiscussionBan.objects.create(
        user=learner,
        course_id=CourseKey.from_string(course_id),
        org_key="edX",
        scope="course",
        banned_by=moderator,
        is_active=True,
        reason="Spam posting",
    )

    data = {"unbanned_by_id": moderator.id, "reason": "Appeal approved"}

    response = api_client.post_json(f"/api/v2/users/bans/{ban.id}/unban", data=data)

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["exception_created"] is False

    # Verify ban was deactivated
    ban.refresh_from_db()
    assert ban.is_active is False
    assert ban.unbanned_at is not None


def test_unban_org_level_ban_completely(
    api_client: APIClient, test_users: dict
) -> None:
    """Test completely unbanning a user from organization-level ban."""
    learner = test_users["learner"]
    moderator = test_users["moderator"]

    # Create active org-level ban
    ban = DiscussionBan.objects.create(
        user=learner,
        org_key="edX",
        scope="organization",
        banned_by=moderator,
        is_active=True,
        reason="Repeated violations",
    )

    data = {"unbanned_by_id": moderator.id, "reason": "Ban period expired"}

    response = api_client.post_json(f"/api/v2/users/bans/{ban.id}/unban", data=data)

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["exception_created"] is False

    # Verify ban was deactivated
    ban.refresh_from_db()
    assert ban.is_active is False


def test_unban_org_ban_with_course_exception(
    api_client: APIClient, test_users: dict
) -> None:
    """Test creating a course exception to an organization-level ban."""
    learner = test_users["learner"]
    moderator = test_users["moderator"]
    course_id = "course-v1:edX+DemoX+Demo_Course"

    # Create active org-level ban
    ban = DiscussionBan.objects.create(
        user=learner,
        org_key="edX",
        scope="organization",
        banned_by=moderator,
        is_active=True,
        reason="Repeated violations",
    )

    data = {
        "unbanned_by_id": moderator.id,
        "course_id": course_id,
        "reason": "Approved for this course",
    }

    response = api_client.post_json(f"/api/v2/users/bans/{ban.id}/unban", data=data)

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["exception_created"] is True
    assert response.json()["exception"] is not None

    # Verify ban is still active
    ban.refresh_from_db()
    assert ban.is_active is True

    # Verify exception was created
    assert response.json()["exception"]["course_id"] == course_id


def test_unban_invalid_ban_id(api_client: APIClient, test_users: dict) -> None:
    """Test unbanning fails with invalid ban ID."""
    moderator = test_users["moderator"]

    data = {"unbanned_by_id": moderator.id, "reason": "Test"}

    response = api_client.post_json("/api/v2/users/bans/99999/unban", data=data)

    assert response.status_code == 404
    assert "not found" in str(response.json()).lower()


def test_list_all_active_bans(api_client: APIClient, test_users: dict) -> None:
    """Test listing all active bans."""
    learner1 = test_users["learner"]
    moderator = test_users["moderator"]
    course_id = "course-v1:edX+DemoX+Demo_Course"

    # Create another user
    learner2 = User.objects.create_user(
        username="learner2", email="learner2@test.com", password="password"
    )

    # Create bans
    _ban1 = DiscussionBan.objects.create(
        user=learner1,
        course_id=CourseKey.from_string(course_id),
        org_key="edX",
        scope="course",
        banned_by=moderator,
        is_active=True,
        reason="Spam",
    )
    _ban2 = DiscussionBan.objects.create(
        user=learner2,
        org_key="edX",
        scope="organization",
        banned_by=moderator,
        is_active=True,
        reason="Violations",
    )

    response = api_client.get("/api/v2/users/banned")

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_list_bans_filtered_by_course(api_client: APIClient, test_users: dict) -> None:
    """Test listing bans filtered by course ID."""
    learner1 = test_users["learner"]
    moderator = test_users["moderator"]
    course_id = "course-v1:edX+DemoX+Demo_Course"

    # Create another user
    learner2 = User.objects.create_user(
        username="learner2", email="learner2@test.com", password="password"
    )

    # Create bans in different courses
    _ban1 = DiscussionBan.objects.create(
        user=learner1,
        course_id=CourseKey.from_string(course_id),
        org_key="edX",
        scope="course",
        banned_by=moderator,
        is_active=True,
        reason="Spam",
    )
    _ban2 = DiscussionBan.objects.create(
        user=learner2,
        course_id=CourseKey.from_string("course-v1:edX+Other+Course"),
        org_key="edX",
        scope="course",
        banned_by=moderator,
        is_active=True,
        reason="Violations",
    )

    response = api_client.get(f"/api/v2/users/banned?course_id={quote_plus(course_id)}")

    assert response.status_code == 200
    # Should return ban1 and any org-level bans for this org
    assert len(response.json()) >= 1
    assert response.json()[0]["user"]["id"] == learner1.id


def test_list_bans_include_inactive(api_client: APIClient, test_users: dict) -> None:
    """Test listing bans including inactive ones."""
    learner1 = test_users["learner"]
    moderator = test_users["moderator"]
    course_id = "course-v1:edX+DemoX+Demo_Course"

    # Create another user
    learner2 = User.objects.create_user(
        username="learner2", email="learner2@test.com", password="password"
    )

    # Create active and inactive bans
    _ban1 = DiscussionBan.objects.create(
        user=learner1,
        course_id=CourseKey.from_string(course_id),
        org_key="edX",
        scope="course",
        banned_by=moderator,
        is_active=True,
        reason="Spam",
    )
    _ban2 = DiscussionBan.objects.create(
        user=learner2,
        course_id=CourseKey.from_string(course_id),
        org_key="edX",
        scope="course",
        banned_by=moderator,
        is_active=False,
        reason="Old ban",
    )

    response = api_client.get("/api/v2/users/banned?include_inactive=true")

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_get_ban_details_success(api_client: APIClient, test_users: dict) -> None:
    """Test retrieving ban details successfully."""
    learner = test_users["learner"]
    moderator = test_users["moderator"]
    course_id = "course-v1:edX+DemoX+Demo_Course"

    ban = DiscussionBan.objects.create(
        user=learner,
        course_id=CourseKey.from_string(course_id),
        org_key="edX",
        scope="course",
        banned_by=moderator,
        is_active=True,
        reason="Spam posting",
    )

    response = api_client.get(f"/api/v2/users/bans/{ban.id}")

    assert response.status_code == 200
    assert response.json()["id"] == ban.id
    assert response.json()["user"]["id"] == learner.id
    assert response.json()["scope"] == "course"
    assert response.json()["is_active"] is True


def test_get_ban_details_not_found(api_client: APIClient) -> None:
    """Test retrieving non-existent ban returns 404."""
    response = api_client.get("/api/v2/users/bans/99999")

    assert response.status_code == 404
    assert "not found" in str(response.json()).lower()
