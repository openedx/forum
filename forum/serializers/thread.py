"""
Serializer for the thread data.
"""

from typing import Any, Optional

from rest_framework import serializers
from rest_framework.serializers import ValidationError

from forum.serializers.comment import CommentSerializer
from forum.serializers.contents import ContentSerializer
from forum.serializers.custom_datetime import CustomDateTimeField
from forum.utils import prepare_comment_data_for_get_children


class ThreadSerializer(ContentSerializer):
    """
    Serializer for handling user-created threads.

    Inherits from ContentSerializer.

    Attributes:
        thread_type (str): The type of thread (e.g., "discussion", "question").
        title (str): The title of the thread.
        context (str): The context or additional description of the thread.
        last_activity_at (datetime): The timestamp of the last activity in the thread.
        closed_by (str or None): The user who closed the thread, if any.
        tags (list): A list of tags associated with the thread.
        group_id (int or None): The ID of the group associated with the thread, if any.
        pinned (bool): Whether the thread is pinned at the top of the list.
        comment_count (int): The number of comments on the thread.

    This serializer extends the `ThreadSerializer` and customizes fields based on various context
    parameters. It manages fields related to read state, comment counts, endorsements, abuse flags,
    and response information.

    Custom Attributes:
        read (serializers.SerializerMethodField): A method field to determine if the thread is read.
        unread_comments_count (serializers.SerializerMethodField): A method field to count unread comments.
        endorsed (serializers.SerializerMethodField): A method field to check if the thread is endorsed.
        abuse_flagged_count (serializers.SerializerMethodField, optional): A method field to count flagged abuse.
        children (serializers.SerializerMethodField, optional): A method field for responses to the thread.
        resp_total (serializers.SerializerMethodField, optional): A method field for total responses.
        resp_skip (serializers.IntegerField, optional): An integer field for pagination (responses to skip).
        resp_limit (serializers.IntegerField, optional): An integer field for pagination (responses limit).
    """

    thread_type = serializers.CharField()
    title = serializers.CharField()
    context = serializers.CharField()  # type: ignore
    last_activity_at = CustomDateTimeField(allow_null=True, default=None)
    closed_by_id = serializers.CharField(allow_null=True, default=None)
    closed_by = serializers.SerializerMethodField()
    close_reason_code = serializers.CharField(allow_null=True, default=None)
    tags = serializers.ListField(default=[])
    group_id = serializers.IntegerField(allow_null=True, default=None)
    pinned = serializers.BooleanField(default=False)
    comments_count = serializers.IntegerField(required=False, source="comment_count")
    read = serializers.SerializerMethodField()
    unread_comments_count = serializers.SerializerMethodField()
    endorsed = serializers.SerializerMethodField()
    abuse_flagged_count = serializers.SerializerMethodField(required=False)
    children = serializers.SerializerMethodField(required=False)
    resp_total = serializers.SerializerMethodField(required=False)
    resp_skip = serializers.IntegerField(required=False, default=0)
    resp_limit = serializers.IntegerField(required=False, default=10)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize the serializer with context-specific settings.

        Args:
            *args: Variable length argument list for serializer initialization.
            **kwargs: Keyword arguments for serializer initialization, including 'context'.

        Keyword Args:
            context (dict[str, Any]): Contextual data to customize the serializer's behavior.
                - 'with_responses' (bool): Whether to include response-related fields.
                - 'count_flagged' (bool): Whether to include abuse-flagged count.
                - 'include_endorsed' (bool): Whether to include endorsement status.
                - 'include_read_state' (bool): Whether to include read state information.
        """
        self.context_data = kwargs.get("context", {})
        self.backend = kwargs.pop("backend")
        self.with_responses = self.context_data.pop("with_responses", False)
        self.count_flagged = self.context_data.pop("count_flagged", False)
        self.include_endorsed = self.context_data.pop("include_endorsed", False)
        self.include_read_state = self.context_data.pop("include_read_state", False)
        self.merge_question_type_responses = self.context_data.pop(
            "merge_question_type_responses", False
        )

        # Customize fields based on context
        if not self.with_responses:
            self.fields.pop("children")
            self.fields.pop("resp_total")
            self.fields.pop("resp_skip")
            self.fields.pop("resp_limit")

        if not self.count_flagged:
            self.fields.pop("abuse_flagged_count")

        if not self.include_endorsed:
            self.fields.pop("endorsed")

        if not self.include_read_state:
            self.fields.pop("read", None)
            self.fields.pop("unread_comments_count", None)

        super().__init__(*args, **kwargs)

    def get_read(self, obj: dict[str, Any]) -> Optional[bool]:
        """
        Retrieve the read state of the thread.

        Args:
            obj (dict[str, Any]): The dictionary or object representing the thread.

        Returns:
            Optional[bool]: True if the thread is read, otherwise False or None.
        """
        if self.include_read_state:
            if isinstance(obj, dict) and obj.get("read") is not None:
                return obj.get("read", True)
            user_id = self.context_data.get("user_id", None)
            course_id = obj["course_id"]
            thread_key = obj["_id"]
            is_read, _ = self.backend.get_read_states(
                [obj["_id"]], user_id, course_id
            ).get(thread_key, (False, obj["comment_count"]))
            return is_read
        return None

    def get_unread_comments_count(self, obj: dict[str, Any]) -> Optional[int]:
        """
        Retrieve the count of unread comments for the thread.

        Args:
            obj (dict[str, Any]): The dictionary or object representing the thread.

        Returns:
            Optional[int]: The number of unread comments or None.
        """
        if self.include_read_state:
            if isinstance(obj, dict) and obj.get("unread_comments_count") is not None:
                return obj.get("unread_comments_count", 0)
            user_id = self.context_data.get("user_id", None)
            course_id = obj["course_id"]
            thread_key = obj["_id"]
            _, unread_count = self.backend.get_read_states(
                [obj["_id"]], user_id, course_id
            ).get(thread_key, (False, obj["comment_count"]))
            return unread_count
        return None

    def get_endorsed(self, obj: dict[str, Any]) -> Optional[bool]:
        """
        Determine if the thread is endorsed.

        Args:
            obj (dict[str, Any]): The dictionary or object representing the thread.

        Returns:
            Optional[bool]: True if the thread is endorsed, otherwise False or None.
        """
        if self.include_endorsed:
            if isinstance(obj, dict) and obj.get("endorsed") is not None:
                return obj.get("endorsed", True)
            thread_key = obj["_id"]
            return self.backend.get_endorsed([thread_key]).get(thread_key, False)
        return None

    def get_abuse_flagged_count(self, obj: dict[str, Any]) -> int:
        """
        Retrieve the count of abuse-flagged instances for the thread.

        Args:
            obj (dict[str, Any]): The dictionary or object representing the thread.

        Returns:
            int: The count of abuse-flagged instances, defaulting to 0 if not applicable.
        """
        if self.count_flagged:
            if isinstance(obj, dict) and obj.get("abuse_flagged_count") is not None:
                return obj.get("abuse_flagged_count", 0)
            thread_key = obj["_id"]
            return self.backend.get_abuse_flagged_count([thread_key]).get(thread_key, 0)
        return 0

    def get_children(self, obj: dict[str, Any]) -> Optional[Any]:
        """
        Retrieve the children (responses) for the thread if applicable.

        Args:
            obj (dict[str, Any]): The dictionary or object representing the thread.

        Returns:
            Optional[Any]: The responses or children related to the thread, or None if not included.
        """
        if self.with_responses:
            sorting_order = -1 if self.context_data.get("reverse_order", True) else 1
            children = self.backend.get_comments(
                comment_thread_id=obj["_id"],
                depth=0,
                parent_id=None,
                sort=sorting_order,
                resp_skip=obj["resp_skip"],
                resp_limit=obj["resp_limit"],
            )
            children_data = prepare_comment_data_for_get_children(children)
            serializer = CommentSerializer(
                data=children_data,
                many=True,
                context={
                    "recursive": self.context_data.get("recursive", False),
                    "sort": sorting_order,
                },
                exclude_fields=["sk"],
                backend=self.backend,
            )
            if not serializer.is_valid(raise_exception=True):
                raise ValidationError(serializer.errors)
            return serializer.data
        return []

    def get_resp_total(self, obj: dict[str, Any]) -> int:
        """
        Retrieve the total number of responses for the thread if applicable.

        Args:
            obj (dict[str, Any]): The dictionary or object representing the thread.

        Returns:
            int: The total number of responses, defaulting to 0 if not included.
        """
        if self.with_responses:
            return self.backend.get_comments_count(
                comment_thread_id=obj["_id"],
                depth=0,
                parent_id=None,
            )
        return 0

    def to_representation(self, instance: dict[str, Any]) -> dict[str, Any]:
        """
        Convert the instance to its representation format, removing fields based on conditions.

        Args:
            instance (dict[str, Any]): The dictionary representing the instance to be converted.

        Returns:
            dict[str, Any]: The dictionary representation of the instance with certain fields removed.
        """
        data = super().to_representation(instance)
        data.pop("closed_by_id")
        data.pop("historical_abuse_flaggers")
        if not data.get("abuse_flagged_count", None):
            data.pop("abuse_flagged_count", None)
        if not data.get("closed_by", None):
            data.pop("close_reason_code", None)
        if (
            self.with_responses
            and (
                not ("recursive" in self.context_data)
                or self.context_data.get("recursive") is True
            )
            and data.get("thread_type") == "question"
            and not self.merge_question_type_responses
        ):
            children = data.pop("children")
            data["non_endorsed_responses"] = []
            data["endorsed_responses"] = []
            for child in children:
                if child["endorsed"]:
                    data["endorsed_responses"].append(child)
                else:
                    data["non_endorsed_responses"].append(child)

            data["non_endorsed_resp_total"] = len(data["non_endorsed_responses"])

        return data

    def create(self, validated_data: dict[str, Any]) -> Any:
        """Raise NotImplementedError"""
        raise NotImplementedError

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        """Raise NotImplementedError"""
        raise NotImplementedError

    def get_closed_by(self, obj: dict[str, Any]) -> Optional[str]:
        """Retrieve the username of the person who closed the object."""
        if closed_by_id := obj.get("closed_by_id"):
            return self.backend.get_username_from_id(closed_by_id)
        return None
