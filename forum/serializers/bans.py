"""
Serializers for discussion ban operations.
"""

from typing import Any

from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


class BanUserSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """
    Serializer for banning a user from discussions.
    """

    user_id = serializers.IntegerField(required=True, help_text="ID of the user to ban")
    banned_by_id = serializers.IntegerField(
        required=True, help_text="ID of the moderator performing the ban"
    )
    course_id = serializers.CharField(
        required=False, allow_null=True, help_text="Course ID for course-level bans"
    )
    org_key = serializers.CharField(
        required=False, allow_null=True, help_text="Organization key for org-level bans"
    )
    scope = serializers.ChoiceField(
        choices=["course", "organization"],
        default="course",
        help_text="Ban scope: 'course' or 'organization'",
    )
    reason = serializers.CharField(
        required=False, allow_blank=True, help_text="Reason for the ban (optional)"
    )

    def create(self, validated_data: dict[str, Any]) -> Any:
        """Not implemented - use API function instead."""
        raise NotImplementedError("Use ban_user() API function instead")

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        """Not implemented - bans are created, not updated."""
        raise NotImplementedError("Bans cannot be updated")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Validate that required fields are present based on scope."""
        scope = attrs.get("scope", "course")

        if scope == "course" and not attrs.get("course_id"):
            raise serializers.ValidationError(
                {"course_id": "course_id is required for course-level bans"}
            )

        if scope == "organization" and not attrs.get("org_key"):
            raise serializers.ValidationError(
                {"org_key": "org_key is required for organization-level bans"}
            )

        return attrs


class UnbanUserSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """
    Serializer for unbanning a user from discussions.
    """

    unbanned_by_id = serializers.IntegerField(
        required=True, help_text="ID of the moderator performing the unban"
    )

    def create(self, validated_data: dict[str, Any]) -> Any:
        """Not implemented - use API function instead."""
        raise NotImplementedError("Use unban_user() API function instead")

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        """Not implemented - use API function instead."""
        raise NotImplementedError("Use unban_user() API function instead")

    def validate_unbanned_by_id(self, value: int) -> int:
        """Validate that the moderator exists."""
        try:
            User.objects.get(id=value)
        except User.DoesNotExist as exc:
            raise serializers.ValidationError("Moderator user not found") from exc
        return value

    course_id = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Course ID for creating an exception to org-level ban",
    )
    reason = serializers.CharField(
        required=False, allow_blank=True, help_text="Reason for unbanning (optional)"
    )


class BannedUserResponseSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """
    Serializer for banned user data in responses (read-only).
    """

    id = serializers.IntegerField(read_only=True)

    def create(self, validated_data: dict[str, Any]) -> Any:
        """Not implemented - read-only serializer."""
        raise NotImplementedError("Read-only serializer")

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        """Not implemented - read-only serializer."""
        raise NotImplementedError("Read-only serializer")

    user = serializers.DictField(read_only=True)
    course_id = serializers.CharField(read_only=True, allow_null=True)
    org_key = serializers.CharField(read_only=True, allow_null=True)
    scope = serializers.CharField(read_only=True)
    reason = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    banned_at = serializers.DateTimeField(read_only=True, allow_null=True)
    banned_by = serializers.DictField(read_only=True, allow_null=True)
    unbanned_at = serializers.DateTimeField(read_only=True, allow_null=True)
    unbanned_by = serializers.DictField(read_only=True, allow_null=True)


class BannedUsersListSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """
    Serializer for listing banned users with filtering options (read-only).
    """

    course_id = serializers.CharField(
        required=False, allow_null=True, help_text="Filter by course ID"
    )
    org_key = serializers.CharField(
        required=False, allow_null=True, help_text="Filter by organization key"
    )
    include_inactive = serializers.BooleanField(
        default=False, help_text="Include inactive (unbanned) users"
    )
    scope = serializers.ChoiceField(
        choices=["course", "organization"],
        required=False,
        allow_null=True,
        help_text="Filter by ban scope: 'course' or 'organization'",
    )

    def create(self, validated_data: dict[str, Any]) -> Any:
        """Not implemented - read-only serializer."""
        raise NotImplementedError("Read-only serializer")

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        """Not implemented - read-only serializer."""
        raise NotImplementedError("Read-only serializer")


class UnbanResponseSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """
    Serializer for unban operation response (read-only).
    """

    status = serializers.CharField(read_only=True)

    def create(self, validated_data: dict[str, Any]) -> Any:
        """Not implemented - read-only serializer."""
        raise NotImplementedError("Read-only serializer")

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        """Not implemented - read-only serializer."""
        raise NotImplementedError("Read-only serializer")

    message = serializers.CharField(read_only=True)
    exception_created = serializers.BooleanField(read_only=True)
    ban = BannedUserResponseSerializer(read_only=True)
    exception = serializers.DictField(read_only=True, allow_null=True)
