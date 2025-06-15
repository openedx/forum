"""Serializer for Subscriptions."""

from typing import Any

from rest_framework import serializers
from forum.backends.mysql.models import Subscription


class SubscriptionSerializer(serializers.ModelSerializer):
    """
    Serializer for Subscription data.

    This serializer is used to serialize and deserialize subscription data.
    """

    class Meta:
        model = Subscription
        fields = (
            'id',
            'subscriber',
            'source_content_type',
            'source_object_id',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

    def create(self, validated_data: dict[str, Any]) -> Any:
        """Raise NotImplementedError"""
        raise NotImplementedError

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        """Raise NotImplementedError"""
        raise NotImplementedError
