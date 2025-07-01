"""
Serializers for commentable counts.
"""

from typing import Any, Dict
from rest_framework import serializers


class CommentableSerializer(serializers.Serializer[Dict[str, Dict[str, int]]]):
    """
    Serializer for commentable counts grouped by type (discussion/question).
    Expects a dict of the form:
    {
        "commentable_id": {"discussion": int, "question": int},
        ...
    }
    """

    def to_representation(
        self, instance: Dict[str, Dict[str, int]]
    ) -> Dict[str, Dict[str, int]]:
        # instance is expected to be a dict as described above
        return instance

    def create(self, validated_data: Dict[str, Any]) -> Dict[str, Any]:
        # No-op, as this serializer is only for output
        return validated_data

    def update(self, instance: Any, validated_data: Dict[str, Any]) -> Any:
        # No-op, as this serializer is only for output
        return instance
