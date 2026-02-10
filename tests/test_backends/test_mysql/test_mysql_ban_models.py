"""Tests for discussion ban models."""

# mypy: ignore-errors
# pylint: disable=redefined-outer-name,unused-argument

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from opaque_keys.edx.keys import CourseKey

from forum.backends.mysql.models import (  # pylint: disable=import-error
    DiscussionBan,
    DiscussionBanException,
)

User = get_user_model()


@pytest.fixture
def test_users(db):  # db fixture ensures database access
    """Create test users."""
    return {
        "banned_user": User.objects.create(
            username="banned_user", email="banned@example.com"
        ),
        "moderator": User.objects.create(username="moderator", email="mod@example.com"),
        "another_user": User.objects.create(
            username="another_user", email="another@example.com"
        ),
    }


@pytest.fixture
def test_course_keys():
    """Create test course keys."""
    return {
        "harvard_cs50": CourseKey.from_string("course-v1:HarvardX+CS50+2024"),
        "harvard_math": CourseKey.from_string("course-v1:HarvardX+Math101+2024"),
        "mitx_python": CourseKey.from_string("course-v1:MITx+Python+2024"),
    }


# ==================== DiscussionBan Model Tests ====================


@pytest.mark.django_db
class TestDiscussionBanModel:
    """Tests for DiscussionBan model."""

    def test_create_course_level_ban(self, test_users, test_course_keys):
        """Test creating a course-level ban."""
        ban = DiscussionBan.objects.create(
            user=test_users["banned_user"],
            course_id=test_course_keys["harvard_cs50"],
            scope=DiscussionBan.SCOPE_COURSE,
            banned_by=test_users["moderator"],
            reason="Posting spam content",
            is_active=True,
        )

        assert ban.user == test_users["banned_user"]
        assert ban.course_id == test_course_keys["harvard_cs50"]
        assert ban.scope == "course"
        assert ban.banned_by == test_users["moderator"]
        assert ban.reason == "Posting spam content"
        assert ban.is_active is True
        assert ban.org_key is None
        assert ban.unbanned_at is None
        assert ban.unbanned_by is None

    def test_create_org_level_ban(self, test_users):
        """Test creating an organization-level ban."""
        ban = DiscussionBan.objects.create(
            user=test_users["banned_user"],
            org_key="HarvardX",
            scope=DiscussionBan.SCOPE_ORGANIZATION,
            banned_by=test_users["moderator"],
            reason="Repeated violations across courses",
            is_active=True,
        )

        assert ban.user == test_users["banned_user"]
        assert ban.org_key == "HarvardX"
        assert ban.scope == "organization"
        assert ban.course_id is None
        assert ban.is_active is True

    def test_unique_active_course_ban_constraint(self, test_users, test_course_keys):
        """Test that duplicate active course-level bans are prevented."""
        # Create first ban
        DiscussionBan.objects.create(
            user=test_users["banned_user"],
            course_id=test_course_keys["harvard_cs50"],
            scope=DiscussionBan.SCOPE_COURSE,
            banned_by=test_users["moderator"],
            reason="First ban",
            is_active=True,
        )

        # Attempt to create duplicate - should fail
        with pytest.raises(IntegrityError):
            DiscussionBan.objects.create(
                user=test_users["banned_user"],
                course_id=test_course_keys["harvard_cs50"],
                scope=DiscussionBan.SCOPE_COURSE,
                banned_by=test_users["moderator"],
                reason="Duplicate ban",
                is_active=True,
            )

    def test_unique_active_org_ban_constraint(self, test_users):
        """Test that duplicate active org-level bans are prevented."""
        # Create first ban
        DiscussionBan.objects.create(
            user=test_users["banned_user"],
            org_key="HarvardX",
            scope=DiscussionBan.SCOPE_ORGANIZATION,
            banned_by=test_users["moderator"],
            reason="First org ban",
            is_active=True,
        )

        # Attempt to create duplicate - should fail
        with pytest.raises(IntegrityError):
            DiscussionBan.objects.create(
                user=test_users["banned_user"],
                org_key="HarvardX",
                scope=DiscussionBan.SCOPE_ORGANIZATION,
                banned_by=test_users["moderator"],
                reason="Duplicate org ban",
                is_active=True,
            )

    def test_multiple_inactive_bans_allowed(self, test_users, test_course_keys):
        """Test that multiple inactive bans are allowed (no unique constraint)."""
        # Create first inactive ban
        DiscussionBan.objects.create(
            user=test_users["banned_user"],
            course_id=test_course_keys["harvard_cs50"],
            scope=DiscussionBan.SCOPE_COURSE,
            banned_by=test_users["moderator"],
            reason="First ban - now inactive",
            is_active=False,
        )

        # Create second inactive ban - should succeed
        ban2 = DiscussionBan.objects.create(
            user=test_users["banned_user"],
            course_id=test_course_keys["harvard_cs50"],
            scope=DiscussionBan.SCOPE_COURSE,
            banned_by=test_users["moderator"],
            reason="Second ban - also inactive",
            is_active=False,
        )

        assert ban2.is_active is False
        assert (
            DiscussionBan.objects.filter(
                user=test_users["banned_user"],
                course_id=test_course_keys["harvard_cs50"],
                is_active=False,
            ).count()
            == 2
        )

    def test_ban_str_representation_course_level(self, test_users, test_course_keys):
        """Test string representation for course-level ban."""
        ban = DiscussionBan.objects.create(
            user=test_users["banned_user"],
            course_id=test_course_keys["harvard_cs50"],
            scope=DiscussionBan.SCOPE_COURSE,
            banned_by=test_users["moderator"],
            reason="Test",
        )

        expected = f"Ban: {test_users['banned_user'].username} in {test_course_keys['harvard_cs50']} (course-level)"
        assert str(ban) == expected

    def test_ban_str_representation_org_level(self, test_users):
        """Test string representation for org-level ban."""
        ban = DiscussionBan.objects.create(
            user=test_users["banned_user"],
            org_key="HarvardX",
            scope=DiscussionBan.SCOPE_ORGANIZATION,
            banned_by=test_users["moderator"],
            reason="Test",
        )

        expected = f"Ban: {test_users['banned_user'].username} in HarvardX (org-level)"
        assert str(ban) == expected

    def test_clean_validation_course_scope_requires_course_id(self, test_users):
        """Test that course-level bans require course_id."""
        ban = DiscussionBan(
            user=test_users["banned_user"],
            scope=DiscussionBan.SCOPE_COURSE,
            banned_by=test_users["moderator"],
            reason="Test",
            # Missing course_id
        )

        with pytest.raises(
            ValidationError, match="Course-level bans require course_id"
        ):
            ban.clean()

    def test_clean_validation_org_scope_requires_org_key(self, test_users):
        """Test that org-level bans require org_key."""
        ban = DiscussionBan(
            user=test_users["banned_user"],
            scope=DiscussionBan.SCOPE_ORGANIZATION,
            banned_by=test_users["moderator"],
            reason="Test",
            # Missing org_key
        )

        with pytest.raises(
            ValidationError, match="Organization-level bans require organization"
        ):
            ban.clean()

    def test_clean_validation_org_scope_cannot_have_course_id(
        self, test_users, test_course_keys
    ):
        """Test that org-level bans should not have course_id set."""
        ban = DiscussionBan(
            user=test_users["banned_user"],
            org_key="HarvardX",
            course_id=test_course_keys["harvard_cs50"],  # Should not be set
            scope=DiscussionBan.SCOPE_ORGANIZATION,
            banned_by=test_users["moderator"],
            reason="Test",
        )

        with pytest.raises(
            ValidationError,
            match="Organization-level bans should not have course_id set",
        ):
            ban.clean()

    def test_is_user_banned_course_level(self, test_users, test_course_keys):
        """Test is_user_banned for course-level ban."""
        # Create course-level ban
        DiscussionBan.objects.create(
            user=test_users["banned_user"],
            course_id=test_course_keys["harvard_cs50"],
            scope=DiscussionBan.SCOPE_COURSE,
            banned_by=test_users["moderator"],
            reason="Spam",
            is_active=True,
        )

        # User should be banned in CS50
        assert (
            DiscussionBan.is_user_banned(
                test_users["banned_user"], test_course_keys["harvard_cs50"]
            )
            is True
        )

        # User should NOT be banned in Math101
        assert (
            DiscussionBan.is_user_banned(
                test_users["banned_user"], test_course_keys["harvard_math"]
            )
            is False
        )

        # Another user should NOT be banned
        assert (
            DiscussionBan.is_user_banned(
                test_users["another_user"], test_course_keys["harvard_cs50"]
            )
            is False
        )

    def test_is_user_banned_org_level(self, test_users, test_course_keys):
        """Test is_user_banned for org-level ban (applies to all courses in org)."""
        # Create org-level ban for HarvardX
        DiscussionBan.objects.create(
            user=test_users["banned_user"],
            org_key="HarvardX",
            scope=DiscussionBan.SCOPE_ORGANIZATION,
            banned_by=test_users["moderator"],
            reason="Org-wide violation",
            is_active=True,
        )

        # User should be banned in all HarvardX courses
        assert (
            DiscussionBan.is_user_banned(
                test_users["banned_user"], test_course_keys["harvard_cs50"]
            )
            is True
        )

        assert (
            DiscussionBan.is_user_banned(
                test_users["banned_user"], test_course_keys["harvard_math"]
            )
            is True
        )

        # User should NOT be banned in MITx course
        assert (
            DiscussionBan.is_user_banned(
                test_users["banned_user"], test_course_keys["mitx_python"]
            )
            is False
        )

    def test_is_user_banned_inactive_ban_ignored(self, test_users, test_course_keys):
        """Test that inactive bans are ignored."""
        DiscussionBan.objects.create(
            user=test_users["banned_user"],
            course_id=test_course_keys["harvard_cs50"],
            scope=DiscussionBan.SCOPE_COURSE,
            banned_by=test_users["moderator"],
            reason="Old ban",
            is_active=False,  # Inactive
        )

        # User should NOT be banned (ban is inactive)
        assert (
            DiscussionBan.is_user_banned(
                test_users["banned_user"], test_course_keys["harvard_cs50"]
            )
            is False
        )

    def test_is_user_banned_with_course_id_as_string(
        self, test_users, test_course_keys
    ):
        """Test is_user_banned accepts course_id as string."""
        DiscussionBan.objects.create(
            user=test_users["banned_user"],
            course_id=test_course_keys["harvard_cs50"],
            scope=DiscussionBan.SCOPE_COURSE,
            banned_by=test_users["moderator"],
            reason="Spam",
            is_active=True,
        )

        # Pass course_id as string
        assert (
            DiscussionBan.is_user_banned(
                test_users["banned_user"], str(test_course_keys["harvard_cs50"])
            )
            is True
        )


# ==================== DiscussionBanException Model Tests ====================


@pytest.mark.django_db
class TestDiscussionBanExceptionModel:
    """Tests for DiscussionBanException model."""

    def test_create_ban_exception(self, test_users, test_course_keys):
        """Test creating a ban exception."""
        # Create org-level ban
        org_ban = DiscussionBan.objects.create(
            user=test_users["banned_user"],
            org_key="HarvardX",
            scope=DiscussionBan.SCOPE_ORGANIZATION,
            banned_by=test_users["moderator"],
            reason="Org-wide ban",
            is_active=True,
        )

        # Create exception for CS50
        exception = DiscussionBanException.objects.create(
            ban=org_ban,
            course_id=test_course_keys["harvard_cs50"],
            unbanned_by=test_users["moderator"],
            reason="Appeal approved for CS50",
        )

        assert exception.ban == org_ban
        assert exception.course_id == test_course_keys["harvard_cs50"]
        assert exception.unbanned_by == test_users["moderator"]
        assert exception.reason == "Appeal approved for CS50"

    def test_exception_str_representation(self, test_users, test_course_keys):
        """Test string representation of exception."""
        org_ban = DiscussionBan.objects.create(
            user=test_users["banned_user"],
            org_key="HarvardX",
            scope=DiscussionBan.SCOPE_ORGANIZATION,
            banned_by=test_users["moderator"],
            reason="Org ban",
        )

        exception = DiscussionBanException.objects.create(
            ban=org_ban,
            course_id=test_course_keys["harvard_cs50"],
            unbanned_by=test_users["moderator"],
        )

        expected = f"Exception: {test_users['banned_user'].username} allowed in {test_course_keys['harvard_cs50']}"
        assert str(exception) == expected

    def test_unique_ban_exception_constraint(self, test_users, test_course_keys):
        """Test that duplicate exceptions for same ban + course are prevented."""
        org_ban = DiscussionBan.objects.create(
            user=test_users["banned_user"],
            org_key="HarvardX",
            scope=DiscussionBan.SCOPE_ORGANIZATION,
            banned_by=test_users["moderator"],
            reason="Org ban",
        )

        # Create first exception
        DiscussionBanException.objects.create(
            ban=org_ban,
            course_id=test_course_keys["harvard_cs50"],
            unbanned_by=test_users["moderator"],
        )

        # Attempt duplicate - should fail
        with pytest.raises(IntegrityError):
            DiscussionBanException.objects.create(
                ban=org_ban,
                course_id=test_course_keys["harvard_cs50"],
                unbanned_by=test_users["moderator"],
            )

    def test_exception_only_for_org_bans_validation(self, test_users, test_course_keys):
        """Test that exceptions can only be created for org-level bans."""
        # Create course-level ban
        course_ban = DiscussionBan.objects.create(
            user=test_users["banned_user"],
            course_id=test_course_keys["harvard_cs50"],
            scope=DiscussionBan.SCOPE_COURSE,
            banned_by=test_users["moderator"],
            reason="Course ban",
        )

        # Try to create exception for course-level ban
        exception = DiscussionBanException(
            ban=course_ban,
            course_id=test_course_keys["harvard_math"],
            unbanned_by=test_users["moderator"],
        )

        with pytest.raises(
            ValidationError,
            match="Exceptions can only be created for organization-level bans",
        ):
            exception.clean()

    def test_org_ban_with_exception_allows_user(self, test_users, test_course_keys):
        """Test that exception to org ban allows user in specific course."""
        # Create org-level ban for HarvardX
        org_ban = DiscussionBan.objects.create(
            user=test_users["banned_user"],
            org_key="HarvardX",
            scope=DiscussionBan.SCOPE_ORGANIZATION,
            banned_by=test_users["moderator"],
            reason="Org ban",
            is_active=True,
        )

        # User is banned in all HarvardX courses
        assert (
            DiscussionBan.is_user_banned(
                test_users["banned_user"], test_course_keys["harvard_cs50"]
            )
            is True
        )

        assert (
            DiscussionBan.is_user_banned(
                test_users["banned_user"], test_course_keys["harvard_math"]
            )
            is True
        )

        # Create exception for CS50
        DiscussionBanException.objects.create(
            ban=org_ban,
            course_id=test_course_keys["harvard_cs50"],
            unbanned_by=test_users["moderator"],
            reason="Appeal approved",
        )

        # User should now be allowed in CS50
        assert (
            DiscussionBan.is_user_banned(
                test_users["banned_user"], test_course_keys["harvard_cs50"]
            )
            is False
        )

        # But still banned in Math101
        assert (
            DiscussionBan.is_user_banned(
                test_users["banned_user"], test_course_keys["harvard_math"]
            )
            is True
        )

    def test_exception_cascade_delete_with_ban(self, test_users, test_course_keys):
        """Test that exceptions are deleted when parent ban is deleted."""
        org_ban = DiscussionBan.objects.create(
            user=test_users["banned_user"],
            org_key="HarvardX",
            scope=DiscussionBan.SCOPE_ORGANIZATION,
            banned_by=test_users["moderator"],
            reason="Org ban",
        )

        exception = DiscussionBanException.objects.create(
            ban=org_ban,
            course_id=test_course_keys["harvard_cs50"],
            unbanned_by=test_users["moderator"],
        )

        exception_id = exception.id

        # Delete parent ban
        org_ban.delete()

        # Exception should be deleted
        assert not DiscussionBanException.objects.filter(id=exception_id).exists()
