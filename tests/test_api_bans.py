"""
Tests for forum ban API functions.

These tests verify the ban API functions work correctly with the MySQL backend.
Tests include: ban_user, unban_user, get_banned_users, get_ban, is_user_banned,
get_user_ban_scope, get_banned_usernames, create_audit_log.
"""

# mypy: ignore-errors
# pylint: disable=redefined-outer-name

import pytest
from django.contrib.auth import get_user_model
from opaque_keys.edx.keys import CourseKey

from forum import api as forum_api
from forum.backends.mysql.models import (
    DiscussionBan,
    DiscussionBanException,
    ModerationAuditLog,
)

User = get_user_model()


@pytest.fixture
def test_users(db):  # pylint: disable=unused-argument
    """Create test users."""
    return {
        "learner": User.objects.create_user(
            username="learner", email="learner@example.com", password="password"
        ),
        "moderator": User.objects.create_user(
            username="moderator",
            email="moderator@example.com",
            password="password",
            is_staff=True,
        ),
        "another_learner": User.objects.create_user(
            username="another_learner",
            email="another@example.com",
            password="password",
        ),
    }


@pytest.fixture
def test_course_keys():
    """Create test course keys."""
    return {
        "course1": CourseKey.from_string("course-v1:edX+DemoX+2024"),
        "course2": CourseKey.from_string("course-v1:edX+DemoX+2025"),
        "mitx_course": CourseKey.from_string("course-v1:MITx+Python+2024"),
    }


@pytest.mark.django_db
class TestBanUserAPI:
    """Tests for ban_user() API function."""

    def test_ban_user_course_level(self, test_users, test_course_keys):
        """Test banning a user at course level."""
        result = forum_api.ban_user(
            user=test_users["learner"],
            banned_by=test_users["moderator"],
            course_id=test_course_keys["course1"],
            scope="course",
            reason="Posting spam",
        )

        assert result["id"] is not None
        assert result["user"]["id"] == test_users["learner"].id
        assert result["user"]["username"] == "learner"
        assert result["scope"] == "course"
        assert result["course_id"] == str(test_course_keys["course1"])
        assert result["is_active"] is True
        assert result["reason"] == "Posting spam"
        assert result["banned_by"]["id"] == test_users["moderator"].id

        # Verify in database
        ban = DiscussionBan.objects.get(user=test_users["learner"])
        assert ban.scope == "course"
        assert ban.is_active is True

    def test_ban_user_org_level(self, test_users, test_course_keys):
        """Test banning a user at organization level."""
        result = forum_api.ban_user(
            user=test_users["learner"],
            banned_by=test_users["moderator"],
            course_id=test_course_keys["course1"],
            scope="organization",
            reason="Repeated violations",
        )

        assert result["scope"] == "organization"
        assert result["org_key"] == "edX"
        assert result["course_id"] is None

        # Verify in database
        ban = DiscussionBan.objects.get(user=test_users["learner"])
        assert ban.scope == "organization"
        assert ban.org_key == "edX"
        assert ban.course_id is None

    def test_ban_user_reactivates_inactive_ban(self, test_users, test_course_keys):
        """Test that banning reactivates an inactive ban."""
        # Create inactive ban
        DiscussionBan.objects.create(
            user=test_users["learner"],
            course_id=test_course_keys["course1"],
            scope="course",
            banned_by=test_users["moderator"],
            reason="Old reason",
            is_active=False,
        )

        # Ban again
        result = forum_api.ban_user(
            user=test_users["learner"],
            banned_by=test_users["moderator"],
            course_id=test_course_keys["course1"],
            scope="course",
            reason="New reason",
        )

        assert result["is_active"] is True
        assert result["reason"] == "New reason"
        assert result.get("reactivated") is True

        # Only one ban should exist
        assert DiscussionBan.objects.filter(user=test_users["learner"]).count() == 1


@pytest.mark.django_db
class TestUnbanUserAPI:
    """Tests for unban_user() API function."""

    def test_unban_user_course_level(self, test_users, test_course_keys):
        """Test unbanning a user at course level."""
        # Create ban first
        forum_api.ban_user(
            user=test_users["learner"],
            banned_by=test_users["moderator"],
            course_id=test_course_keys["course1"],
            scope="course",
            reason="Test",
        )

        # Unban
        result = forum_api.unban_user(
            user=test_users["learner"],
            unbanned_by=test_users["moderator"],
            course_id=test_course_keys["course1"],
            scope="course",
        )

        assert result["status"] == "success"

        # Verify ban is inactive
        ban = DiscussionBan.objects.get(user=test_users["learner"])
        assert ban.is_active is False
        assert ban.unbanned_by == test_users["moderator"]

    def test_unban_user_org_level(self, test_users, test_course_keys):
        """Test unbanning a user at organization level."""
        # Create org ban
        forum_api.ban_user(
            user=test_users["learner"],
            banned_by=test_users["moderator"],
            course_id=test_course_keys["course1"],
            scope="organization",
            reason="Test",
        )

        # Unban - don't pass course_id to fully deactivate org ban
        result = forum_api.unban_user(
            user=test_users["learner"],
            unbanned_by=test_users["moderator"],
            scope="organization",
        )

        assert result["status"] == "success"

        # Verify ban is inactive
        ban = DiscussionBan.objects.get(user=test_users["learner"])
        assert ban.is_active is False


@pytest.mark.django_db
class TestGetBannedUsersAPI:
    """Tests for get_banned_users() API function."""

    def test_get_banned_users_course_and_org(self, test_users, test_course_keys):
        """Test getting banned users returns both course and org bans."""
        # Create course ban
        forum_api.ban_user(
            user=test_users["learner"],
            banned_by=test_users["moderator"],
            course_id=test_course_keys["course1"],
            scope="course",
            reason="Course ban",
        )

        # Create org ban for different user
        forum_api.ban_user(
            user=test_users["another_learner"],
            banned_by=test_users["moderator"],
            course_id=test_course_keys["course1"],
            scope="organization",
            reason="Org ban",
        )

        result = forum_api.get_banned_users(course_id=test_course_keys["course1"])

        assert len(result) == 2
        usernames = {ban["user"]["username"] for ban in result}
        assert "learner" in usernames
        assert "another_learner" in usernames

    def test_get_banned_users_filter_by_scope(self, test_users, test_course_keys):
        """Test filtering banned users by scope."""
        # Create both types of bans
        forum_api.ban_user(
            user=test_users["learner"],
            banned_by=test_users["moderator"],
            course_id=test_course_keys["course1"],
            scope="course",
            reason="Course ban",
        )

        forum_api.ban_user(
            user=test_users["another_learner"],
            banned_by=test_users["moderator"],
            course_id=test_course_keys["course1"],
            scope="organization",
            reason="Org ban",
        )

        # Filter for course-level only
        course_bans = forum_api.get_banned_users(
            course_id=test_course_keys["course1"], scope="course"
        )
        assert len(course_bans) == 1
        assert course_bans[0]["user"]["username"] == "learner"

        # Filter for org-level only
        org_bans = forum_api.get_banned_users(
            course_id=test_course_keys["course1"], scope="organization"
        )
        assert len(org_bans) == 1
        assert org_bans[0]["user"]["username"] == "another_learner"

    def test_get_banned_users_excludes_org_bans_with_course_exceptions(
        self, test_users, test_course_keys
    ):
        """Test that org-level bans with course exceptions are excluded from course's banned users list."""
        # Create org-level ban
        ban = forum_api.ban_user(
            user=test_users["learner"],
            banned_by=test_users["moderator"],
            course_id=test_course_keys["course1"],
            scope="organization",
            reason="Org-wide ban",
        )
        ban_id = ban["id"]

        # Initially, user should appear in banned users list for course1
        result = forum_api.get_banned_users(course_id=test_course_keys["course1"])
        assert len(result) == 1
        assert result[0]["user"]["username"] == "learner"

        # Create course exception (simulating course-level unban of org ban)
        DiscussionBanException.objects.create(
            ban_id=ban_id,
            course_id=test_course_keys["course1"],
            unbanned_by=test_users["moderator"],
            reason="Exception for course1",
        )

        # Now user should NOT appear in banned users list for course1
        result = forum_api.get_banned_users(course_id=test_course_keys["course1"])
        assert len(result) == 0

        # But should still appear for course2 (no exception there)
        result = forum_api.get_banned_users(course_id=test_course_keys["course2"])
        assert len(result) == 1
        assert result[0]["user"]["username"] == "learner"


@pytest.mark.django_db
class TestGetBanAPI:
    """Tests for get_ban() API function."""

    def test_get_ban_exists(self, test_users, test_course_keys):
        """Test getting an existing ban."""
        forum_api.ban_user(
            user=test_users["learner"],
            banned_by=test_users["moderator"],
            course_id=test_course_keys["course1"],
            scope="course",
            reason="Test",
        )

        result = forum_api.get_ban(
            user=test_users["learner"],
            course_id=test_course_keys["course1"],
            scope="course",
        )

        assert result is not None
        assert result["user"]["id"] == test_users["learner"].id
        assert result["scope"] == "course"
        assert result["is_active"] is True

    def test_get_ban_not_exists(self, test_users, test_course_keys):
        """Test getting a non-existent ban returns None."""
        result = forum_api.get_ban(
            user=test_users["learner"],
            course_id=test_course_keys["course1"],
            scope="course",
        )

        assert result is None


@pytest.mark.django_db
class TestIsUserBannedAPI:
    """Tests for is_user_banned() API function."""

    def test_is_user_banned_course_level(self, test_users, test_course_keys):
        """Test checking if user is banned at course level."""
        # Not banned initially
        assert (
            forum_api.is_user_banned(test_users["learner"], test_course_keys["course1"])
            is False
        )

        # Ban user
        forum_api.ban_user(
            user=test_users["learner"],
            banned_by=test_users["moderator"],
            course_id=test_course_keys["course1"],
            scope="course",
            reason="Test",
        )

        # Now banned
        assert (
            forum_api.is_user_banned(test_users["learner"], test_course_keys["course1"])
            is True
        )

    def test_is_user_banned_org_level(self, test_users, test_course_keys):
        """Test checking if user is banned at org level."""
        # Ban at org level
        forum_api.ban_user(
            user=test_users["learner"],
            banned_by=test_users["moderator"],
            course_id=test_course_keys["course1"],
            scope="organization",
            reason="Test",
        )

        # Banned in all courses of same org
        assert (
            forum_api.is_user_banned(test_users["learner"], test_course_keys["course1"])
            is True
        )
        assert (
            forum_api.is_user_banned(test_users["learner"], test_course_keys["course2"])
            is True
        )

        # Not banned in different org
        assert (
            forum_api.is_user_banned(
                test_users["learner"], test_course_keys["mitx_course"]
            )
            is False
        )

    def test_is_user_banned_with_exception(self, test_users, test_course_keys):
        """Test ban exception allows user in specific course."""
        # Create org ban
        ban_result = forum_api.ban_user(
            user=test_users["learner"],
            banned_by=test_users["moderator"],
            course_id=test_course_keys["course1"],
            scope="organization",
            reason="Test",
        )

        # Create exception for course2
        ban = DiscussionBan.objects.get(id=ban_result["id"])
        DiscussionBanException.objects.create(
            ban=ban,
            course_id=test_course_keys["course2"],
            unbanned_by=test_users["moderator"],
            reason="Exception",
        )

        # Still banned in course1
        assert (
            forum_api.is_user_banned(test_users["learner"], test_course_keys["course1"])
            is True
        )

        # Not banned in course2 due to exception
        assert (
            forum_api.is_user_banned(test_users["learner"], test_course_keys["course2"])
            is False
        )


@pytest.mark.django_db
class TestGetUserBanScopeAPI:
    """Tests for get_user_ban_scope() API function."""

    def test_get_user_ban_scope_course(self, test_users, test_course_keys):
        """Test getting course-level ban scope."""
        forum_api.ban_user(
            user=test_users["learner"],
            banned_by=test_users["moderator"],
            course_id=test_course_keys["course1"],
            scope="course",
            reason="Test",
        )

        scope = forum_api.get_user_ban_scope(
            test_users["learner"], test_course_keys["course1"]
        )
        assert scope == "course"

    def test_get_user_ban_scope_organization(self, test_users, test_course_keys):
        """Test getting organization-level ban scope."""
        forum_api.ban_user(
            user=test_users["learner"],
            banned_by=test_users["moderator"],
            course_id=test_course_keys["course1"],
            scope="organization",
            reason="Test",
        )

        scope = forum_api.get_user_ban_scope(
            test_users["learner"], test_course_keys["course1"]
        )
        assert scope == "organization"

    def test_get_user_ban_scope_not_banned(self, test_users, test_course_keys):
        """Test getting scope for non-banned user returns None."""
        scope = forum_api.get_user_ban_scope(
            test_users["learner"], test_course_keys["course1"]
        )
        assert scope is None

    def test_get_user_ban_scope_with_exception(self, test_users, test_course_keys):
        """Test scope returns None when exception exists."""
        # Create org ban
        ban_result = forum_api.ban_user(
            user=test_users["learner"],
            banned_by=test_users["moderator"],
            course_id=test_course_keys["course1"],
            scope="organization",
            reason="Test",
        )

        # Create exception
        ban = DiscussionBan.objects.get(id=ban_result["id"])
        DiscussionBanException.objects.create(
            ban=ban,
            course_id=test_course_keys["course1"],
            unbanned_by=test_users["moderator"],
            reason="Exception",
        )

        scope = forum_api.get_user_ban_scope(
            test_users["learner"], test_course_keys["course1"]
        )
        assert scope is None


@pytest.mark.django_db
class TestGetBannedUsernamesAPI:
    """Tests for get_banned_usernames() API function."""

    def test_get_banned_usernames_course(self, test_users, test_course_keys):
        """Test getting banned usernames for a course."""
        # Ban multiple users
        forum_api.ban_user(
            user=test_users["learner"],
            banned_by=test_users["moderator"],
            course_id=test_course_keys["course1"],
            scope="course",
            reason="Test",
        )

        forum_api.ban_user(
            user=test_users["another_learner"],
            banned_by=test_users["moderator"],
            course_id=test_course_keys["course1"],
            scope="organization",
            reason="Test",
        )

        usernames = forum_api.get_banned_usernames(
            course_id=test_course_keys["course1"]
        )

        assert isinstance(usernames, set)
        assert "learner" in usernames
        assert "another_learner" in usernames
        assert "moderator" not in usernames

    def test_get_banned_usernames_org_only(self, test_users, test_course_keys):
        """Test getting banned usernames at org level."""
        forum_api.ban_user(
            user=test_users["learner"],
            banned_by=test_users["moderator"],
            course_id=test_course_keys["course1"],
            scope="organization",
            reason="Test",
        )

        usernames = forum_api.get_banned_usernames(org_key="edX")

        assert "learner" in usernames


@pytest.mark.django_db
class TestCreateAuditLogAPI:
    """Tests for create_audit_log() API function."""

    def test_create_audit_log_ban_action(self, test_users, test_course_keys):
        """Test creating audit log for ban action."""
        log = forum_api.create_audit_log(
            action_type=ModerationAuditLog.ACTION_BAN,
            target_user=test_users["learner"],
            moderator=test_users["moderator"],
            course_id=str(test_course_keys["course1"]),
            scope="course",
            reason="Posting spam",
            metadata={"threads_deleted": 5, "comments_deleted": 10},
        )

        assert log.id is not None
        assert log.action_type == ModerationAuditLog.ACTION_BAN
        assert log.target_user == test_users["learner"]
        assert log.moderator == test_users["moderator"]
        assert log.course_id == str(test_course_keys["course1"])
        assert log.scope == "course"
        assert log.reason == "Posting spam"
        assert log.metadata["threads_deleted"] == 5
        assert log.metadata["comments_deleted"] == 10

    def test_create_audit_log_unban_action(self, test_users, test_course_keys):
        """Test creating audit log for unban action."""
        log = forum_api.create_audit_log(
            action_type=ModerationAuditLog.ACTION_UNBAN,
            target_user=test_users["learner"],
            moderator=test_users["moderator"],
            course_id=str(test_course_keys["course1"]),
            scope="course",
            reason="Appeal granted",
        )

        assert log.action_type == ModerationAuditLog.ACTION_UNBAN
        assert log.reason == "Appeal granted"
