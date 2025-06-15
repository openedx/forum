"""Users Serializers class."""

from rest_framework import serializers
from django.contrib.auth.models import User
from forum.serializers.contents import CourseStatSerializer
from forum.backends.mysql.models import ForumUser


class UserSerializer(serializers.ModelSerializer):
    """Serializer for users."""

    class Meta:
        model = User
        fields = ('id', 'username', 'email')
        read_only_fields = ('id',)


class ForumUserSerializer(serializers.ModelSerializer):
    """Serializer for forum users."""

    user = UserSerializer(read_only=True)
    course_stats = serializers.SerializerMethodField()
    read_states = serializers.SerializerMethodField()

    class Meta:
        model = ForumUser
        fields = ('user', 'default_sort_key', 'course_stats', 'read_states')

    def get_course_stats(self, obj):
        course_id = self.context.get('course_id')
        if course_id:
            course_stat = obj.user.course_stats.filter(course_id=course_id).first()
            return CourseStatSerializer(course_stat).data if course_stat else None
        return CourseStatSerializer(obj.user.course_stats.all(), many=True).data

    def get_read_states(self, obj):
        from forum.serializers.contents import ReadStateSerializer
        return ReadStateSerializer(obj.user.read_states.all(), many=True).data
