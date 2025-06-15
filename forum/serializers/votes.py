"""
Serializer for votes data.

Serializes the votes field in the ContentSerializer.
"""

from typing import Any

from rest_framework import serializers
from forum.backends.mysql.models import UserVote
from forum.utils import validate_upvote_or_downvote


class UserVoteSerializer(serializers.ModelSerializer):
    """Serializer for user votes."""

    class Meta:
        model = UserVote
        fields = ('id', 'user', 'content_type', 'content_object_id', 'vote')
        read_only_fields = ('id',)

    def validate_vote(self, value):
        validate_upvote_or_downvote(value)
        return value


class VotesSerializer(serializers.Serializer[dict[str, Any]]):
    """
    Serializer for votes data.

    Handles data of type dict[str, int].

    Attributes:
        up (list[str]): List of user IDs who upvoted the content.
        down (list[str]): List of user IDs who downvoted the content.
        up_count (int): Total number of upvotes.
        down_count (int): Total number of downvotes.
        count (int): Total number of votes.
        point (int): The point value of the content.
    """

    up = serializers.ListField(child=serializers.CharField(), default=[])
    down = serializers.ListField(child=serializers.CharField(), default=[])
    up_count = serializers.IntegerField()
    down_count = serializers.IntegerField()
    count = serializers.IntegerField()
    point = serializers.IntegerField()

    def create(self, validated_data: dict[str, Any]) -> Any:
        """Raise NotImplementedError"""
        raise NotImplementedError

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        """Raise NotImplementedError"""
        raise NotImplementedError


class VotesInputSerializer(serializers.Serializer[dict[str, Any]]):
    """
    Serializer for handling votes on a content item.

    Attributes:
        user_id (str): The ID of the user casting the vote.
        value (str): The value of the vote, either "up" or "down".
    """

    user_id = serializers.CharField(required=True)
    value = serializers.ChoiceField(choices=["up", "down"], required=True)

    def create(self, validated_data: dict[str, Any]) -> Any:
        """Raise NotImplementedError"""
        raise NotImplementedError

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        """Raise NotImplementedError"""
        raise NotImplementedError


class VoteSummarySerializer(serializers.Serializer[dict[str, Any]]):
    """
    Serializer for summarizing votes on a content item.

    Attributes:
        count (int): The total number of votes.
        up_count (int): The number of upvotes.
        down_count (int): The number of downvotes.
        point (int): The net score (upvotes minus downvotes).
    """

    count = serializers.IntegerField(min_value=0)
    up_count = serializers.IntegerField(min_value=0)
    down_count = serializers.IntegerField(min_value=0)
    point = serializers.IntegerField()

    def create(self, validated_data: dict[str, Any]) -> Any:
        """Raise NotImplementedError"""
        raise NotImplementedError

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        """Raise NotImplementedError"""
        raise NotImplementedError
