"""Serializer class for content collection."""

from typing import Any

from rest_framework import serializers

from forum.serializers.custom_datetime import CustomDateTimeField
from forum.serializers.votes import VoteSummarySerializer


class EditHistorySerializer(serializers.Serializer[dict[str, Any]]):
    """
    Serializer for handling edit history of a post or comment

    Attributes:
        original_body (str): The original content of the post or comment before the edit.
        reason_code (str): The code representing the reason for editing the post or comment.
        editor_username (str): The username of the person who made the edit.
        created_at (datetime): The timestamp of when the edit was made.
    """

    original_body = serializers.CharField()
    reason_code = serializers.CharField(allow_null=True, default=None)
    editor_username = serializers.CharField()
    created_at = CustomDateTimeField()

    def create(self, validated_data: dict[str, Any]) -> Any:
        """Raise NotImplementedError"""
        raise NotImplementedError

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        """Raise NotImplementedError"""
        raise NotImplementedError


class ContentSerializer(serializers.Serializer[dict[str, Any]]):
    """
    Serializer for handling the content of a post or comment.

    Attributes:
        id (str): The ID of the Content.
        body (str): The main content text.
        course_id (str): The ID of the related course.
        anonymous (bool): Whether the content is posted anonymously.
        anonymous_to_peers (bool): Whether the content is anonymous to peers.
        created_at (datetime): The timestamp when the content was created.
        updated_at (datetime): The timestamp when the content was last updated.
        at_position_list (list): A list of positions where @mentions occur.
        user_id (str): The ID of the user who created the content.
        username (str): The username of the content creator.
        commentable_id (str): The ID of the entity the content is related to (e.g., course).
        votes (VoteSummarySerializer): A summary of votes on the content.
        abuse_flaggers (list): A list of user IDs who flagged the content as abusive.
        historical_abuse_flaggers (list): A list of user IDs who historically flagged the content as abusive.
        edit_history (list): A list of previous versions of the content.
        closed (bool): Whether the content is closed for further interactions.
        type (str): The type of content (e.g., "post", "comment").
        is_spam (bool): Whether the content was flagged as spam by AI moderation.
        ai_moderation_reason (str): The reason provided by AI for flagging as spam, if applicable.
        abuse_flagged (bool): Whether the content has been flagged for abuse by any user or system.
    """

    id = serializers.CharField(source="_id")
    body = serializers.CharField()
    course_id = serializers.CharField()
    anonymous = serializers.BooleanField(default=False)
    anonymous_to_peers = serializers.BooleanField(default=False)
    created_at = CustomDateTimeField(allow_null=True)
    updated_at = CustomDateTimeField(allow_null=True)
    at_position_list = serializers.ListField(default=[])
    user_id = serializers.CharField(source="author_id")
    username = serializers.CharField(source="author_username", allow_null=True)
    commentable_id = serializers.CharField(default="course")
    votes = VoteSummarySerializer()
    abuse_flaggers = serializers.ListField(child=serializers.CharField(), default=[])
    historical_abuse_flaggers = serializers.ListField(
        child=serializers.CharField(), default=[]
    )
    edit_history = EditHistorySerializer(default=[], many=True)
    closed = serializers.BooleanField(default=False)
    type = serializers.CharField()
    is_spam = serializers.BooleanField(default=False)
    ai_moderation_reason = serializers.CharField(allow_null=True, default=None)
    abuse_flagged = serializers.SerializerMethodField()
    
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize the serializer with context-specific settings.
        """
        context = kwargs.get("context", {})
        self.include_ai_moderation = context.pop("include_ai_moderation", True)
        
        super().__init__(*args, **kwargs)
        
        # Remove AI moderation fields if not requested
        if not self.include_ai_moderation:
            self.fields.pop("is_spam", None)
            self.fields.pop("ai_moderation_reason", None)
            self.fields.pop("abuse_flagged", None)

    def get_abuse_flagged(self, obj: dict[str, Any]) -> bool:
        """
        Determine if the content has been flagged for abuse.
        
        Args:
            obj: The content object (dict for MongoDB, model for MySQL)
            
        Returns:
            bool: True if content has been flagged for abuse, False otherwise
        """
        # Check if there are any abuse flaggers
        abuse_flaggers = obj.get('abuse_flaggers', [])
        if abuse_flaggers:
            return True
            
        # Also check if content is marked as spam
        is_spam = obj.get('is_spam', False)
        return is_spam

    def create(self, validated_data: dict[str, Any]) -> Any:
        """Raise NotImplementedError"""
        raise NotImplementedError

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        """Raise NotImplementedError"""
        raise NotImplementedError
