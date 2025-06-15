"""
Serializer for the comment data.
"""

from typing import Any

from rest_framework import serializers

from forum.serializers.contents import ContentSerializer
from forum.serializers.custom_datetime import CustomDateTimeField
from forum.utils import prepare_comment_data_for_get_children
from forum.backends.mysql.models import Comment


class EndorsementSerializer(serializers.Serializer[dict[str, Any]]):
    """
    Serializer for handling endorsement of a comment

    Attributes:
        user_id (str): The endorsement user id.
        time (datetime): The timestamp of when the user has endorsed the comment.
    """

    user_id = serializers.CharField()
    time = CustomDateTimeField()

    def create(self, validated_data: dict[str, Any]) -> Any:
        """Raise NotImplementedError"""
        raise NotImplementedError

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        """Raise NotImplementedError"""
        raise NotImplementedError


class MySQLCommentSerializer(serializers.ModelSerializer):
    """
    Serializer for MySQL comment model.

    This serializer is used specifically for the MySQL backend and handles the direct
    model serialization of Comment objects.

    Attributes:
        votes (SerializerMethodField): Method field to get vote information
        abuse_flaggers (SerializerMethodField): Method field to get abuse flaggers
        historical_abuse_flaggers (SerializerMethodField): Method field to get historical abuse flaggers
        children (SerializerMethodField): Method field to get child comments
    """

    votes = serializers.SerializerMethodField()
    abuse_flaggers = serializers.SerializerMethodField()
    historical_abuse_flaggers = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = (
            'id',
            'author',
            'comment_thread',
            'parent',
            'body',
            'course_id',
            'endorsement',
            'sort_key',
            'depth',
            'anonymous',
            'anonymous_to_peers',
            'child_count',
            'votes',
            'abuse_flaggers',
            'historical_abuse_flaggers',
            'children',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

    def get_votes(self, obj):
        return obj.get_votes

    def get_abuse_flaggers(self, obj):
        return obj.abuse_flaggers

    def get_historical_abuse_flaggers(self, obj):
        return obj.historical_abuse_flaggers

    def get_children(self, obj):
        return MySQLCommentSerializer(obj.comment_set.all(), many=True).data


class CommentSerializer(ContentSerializer):
    """
    Serializer for handling user comments on threads.

    This is the main serializer used by the API endpoints. It inherits from ContentSerializer
    and provides additional fields specific to comments.

    Inherits from ContentSerializer.

    Attributes:
        endorsed (bool): Whether the comment is endorsed by an authority.
        depth (int): The depth of the comment in a nested comment structure.
        thread_id (str): The ID of the thread the comment belongs to.
        parent_id (str or None): The ID of the parent comment, if any.
        child_count (int): The number of child comments nested under this comment.
        sk (str or None): sk field, has ids data in it.
        endorsement: saves endorsement data.
    """

    endorsed = serializers.BooleanField(default=False)
    depth = serializers.IntegerField(default=0)
    thread_id = serializers.CharField(source="comment_thread_id")
    parent_id = serializers.CharField(default=None, allow_null=True)
    child_count = serializers.IntegerField(default=0)
    sk = serializers.CharField(default=None, required=False, allow_null=True)
    endorsement = EndorsementSerializer(default=None, required=False, allow_null=True)
    children = serializers.SerializerMethodField()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        exclude_fields = kwargs.pop("exclude_fields", None)
        self.backend = kwargs.pop("backend")
        super().__init__(*args, **kwargs)
        if exclude_fields:
            for field in exclude_fields:
                self.fields.pop(field, None)

    def get_children(self, obj: Any) -> list[dict[str, Any]]:
        """Get comments of a thread."""
        if not self.context.get("recursive", False):
            return []

        children = self.backend.get_comments(
            parent_id=obj["_id"],
            depth=1,
            sort=self.context.get("sort", -1),
        )
        children_data = prepare_comment_data_for_get_children(children)
        serializer = CommentSerializer(
            children_data,
            many=True,
            context={"recursive": False},
            exclude_fields=["sk"],
            backend=self.backend,
        )
        return list(serializer.data)

    def to_representation(self, instance: Any) -> dict[str, Any]:
        comment = super().to_representation(instance)
        comment.pop("historical_abuse_flaggers")
        if comment["parent_id"] == "None":
            comment["parent_id"] = None

        thread = self.backend.get_thread(comment["thread_id"])
        comment_from_db = self.backend.get_comment(comment["id"])
        if (
            not comment["endorsed"]
            and comment_from_db
            and "endorsement" not in comment_from_db
            and thread
            and thread["thread_type"] == "question"
        ):
            comment.pop("endorsement", None)
        return comment

    def create(self, validated_data: dict[str, Any]) -> Any:
        """Raise NotImplementedError"""
        raise NotImplementedError

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        """Raise NotImplementedError"""
        raise NotImplementedError
