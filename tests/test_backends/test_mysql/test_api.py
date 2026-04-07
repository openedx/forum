"""Tests for db client."""

import unittest
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from forum.backends.mysql.api import MySQLBackend as backend
from forum.backends.mysql.models import (
    AbuseFlagger,
    Comment,
    CommentThread,
    CourseStat,
    Subscription,
)
from forum.serializers.thread import ThreadSerializer

User = get_user_model()


@pytest.mark.django_db
def test_flag_as_abuse() -> None:
    """Test flagging a comment as abuse."""
    author = User.objects.create(username="author-user")
    flag_user = User.objects.create(username="flag-user")
    comment_thread = CommentThread.objects.create(
        author=author,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    flagged_comment_thread = backend.flag_as_abuse(
        str(flag_user.pk),
        str(comment_thread.pk),
        entity_type=comment_thread.type,
    )

    assert flagged_comment_thread["_id"] == str(comment_thread.pk)
    assert flagged_comment_thread["abuse_flaggers"] == [str(flag_user.pk)]


@pytest.mark.django_db
def test_un_flag_as_abuse_success() -> None:
    """test for un_flag_as_abuse works successfully."""
    user = User.objects.create(username="testuser")
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    AbuseFlagger.objects.create(user=user, content=comment_thread)
    comment_thread.save()
    un_flagged_entity = backend.un_flag_as_abuse(
        user.pk,
        comment_thread.pk,
        entity_type=comment_thread.type,
    )

    assert user.pk not in comment_thread.abuse_flaggers
    assert un_flagged_entity["_id"] == str(comment_thread.pk)
    assert (
        AbuseFlagger.objects.filter(
            user=user, content_object_id=comment_thread.pk
        ).count()
        == 0
    )


@pytest.mark.django_db
def test_un_flag_all_as_abuse_historical_flags_updated() -> None:
    """test for un_flag_as_abuse updates historical flags."""
    user = User.objects.create(username="testuser")
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    AbuseFlagger.objects.create(user=user, content=comment_thread)
    un_flagged_comment_thread = backend.un_flag_all_as_abuse(
        comment_thread.pk,
        entity_type=comment_thread.type,
    )

    assert un_flagged_comment_thread["_id"] == str(comment_thread.pk)
    assert len(comment_thread.abuse_flaggers) == 0
    assert len(comment_thread.historical_abuse_flaggers) == 1


@pytest.mark.django_db
def test_update_stats_for_course_creates_new_stat() -> None:
    """Test that a new CourseStat is created with default values."""
    user = User.objects.create(username="testuser")
    course_id = "course123"
    backend.update_stats_for_course(str(user.pk), course_id)

    course_stat = CourseStat.objects.get(user=user, course_id=course_id)
    assert course_stat.active_flags == 0
    assert course_stat.inactive_flags == 0
    assert course_stat.threads == 0
    assert course_stat.responses == 0
    assert course_stat.replies == 0


@pytest.mark.django_db
def test_update_stats_for_course_updates_existing_stat() -> None:
    """Test that an existing CourseStat is updated correctly."""
    user = User.objects.create(username="testuser")
    user_2 = User.objects.create(username="testuser2")
    course_id = "course123"
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id=course_id,
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    comment_thread_2 = CommentThread.objects.create(
        author=user,
        course_id=course_id,
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    AbuseFlagger.objects.create(user=user, content=comment_thread)
    AbuseFlagger.objects.create(user=user_2, content=comment_thread_2)
    course_stat = CourseStat.objects.create(
        user=user, course_id=course_id, active_flags=2
    )

    backend.update_stats_for_course(str(user.pk), course_id, active_flags=2, threads=2)

    course_stat.refresh_from_db()
    assert course_stat.active_flags == 2
    assert course_stat.threads == 2


@pytest.mark.django_db
def test_update_stats_for_course_ignores_invalid_keys() -> None:
    """Test that invalid keys in kwargs are ignored."""
    user = User.objects.create(username="testuser")
    course_id = "course123"
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id=course_id,
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    AbuseFlagger.objects.create(user=user, content=comment_thread)
    course_stat = CourseStat.objects.create(
        user=user, course_id=course_id, active_flags=1
    )

    # Update stats with an invalid key
    backend.update_stats_for_course(str(user.pk), course_id, invalid_key=10)

    course_stat.refresh_from_db()
    assert course_stat.active_flags == 1


@pytest.mark.django_db
def test_update_stats_for_course_calls_build_course_stats() -> None:
    """Test that build_course_stats is called after updating stats."""
    user = User.objects.create(username="testuser")
    course_id = "course123"

    with patch.object(backend, "build_course_stats") as mock_build_course_stats:
        backend.update_stats_for_course(str(user.pk), course_id, active_flags=1)
        mock_build_course_stats.assert_called_once_with(str(user.pk), course_id)


@pytest.mark.django_db
class TestMongoAPI(unittest.TestCase):
    """
    Test cases for the MySQL backend API.
    """

    def setUp(self) -> None:
        user = User.objects.create(username="testuser")

        self.thread_1 = CommentThread.objects.create(
            author=user,
            course_id="course123",
            title="Test Thread",
            body="This is a test thread",
            thread_type="discussion",
            context="course",
            commentable_id="id_1",
        )
        self.thread_2 = CommentThread.objects.create(
            author=user,
            course_id="course123",
            title="Test Thread",
            body="This is a test thread",
            thread_type="discussion",
            context="course",
            commentable_id="id_2",
        )
        self.thread_3 = CommentThread.objects.create(
            author=user,
            course_id="course123",
            title="Test Thread",
            body="This is a test thread",
            thread_type="discussion",
            context="course",
            commentable_id="id_2",
        )

    def test_filter_by_commentable_ids(self) -> None:
        """
        Test filtering threads by commentable_ids.
        """
        threads = backend.get_threads(
            user_id="",
            params={"commentable_ids": ["id_2"], "course_id": "course_id"},
            serializer=ThreadSerializer,
            thread_ids=[self.thread_1.id, self.thread_2.id, self.thread_3.id],  # type: ignore[attr-defined]
        )
        # make sure the threads are filtered correctly by commentable_ids aka Topics ids
        assert threads["thread_count"] == 2
        for thread in threads["collection"]:
            assert thread["commentable_id"] == "id_2"


# Bulk Delete and Count API Tests


@pytest.mark.django_db
def test_get_user_threads_count() -> None:
    """Test counting user threads across multiple courses."""
    user = User.objects.create(username="testuser")
    other_user = User.objects.create(username="otheruser")

    # Create threads for user in different courses
    CommentThread.objects.create(
        author=user,
        course_id="course1",
        title="Thread 1",
        body="Body 1",
        thread_type="discussion",
    )
    CommentThread.objects.create(
        author=user,
        course_id="course1",
        title="Thread 2",
        body="Body 2",
        thread_type="discussion",
    )
    CommentThread.objects.create(
        author=user,
        course_id="course2",
        title="Thread 3",
        body="Body 3",
        thread_type="discussion",
    )
    # Create deleted thread (should not be counted)
    CommentThread.objects.create(
        author=user,
        course_id="course1",
        title="Deleted Thread",
        body="Deleted",
        thread_type="discussion",
        is_deleted=True,
    )
    # Create thread by other user (should not be counted)
    CommentThread.objects.create(
        author=other_user,
        course_id="course1",
        title="Other Thread",
        body="Other",
        thread_type="discussion",
    )

    # Test counting across specific courses
    count = backend.get_user_threads_count(str(user.pk), ["course1", "course2"])
    assert count == 3

    # Test counting in single course
    count = backend.get_user_threads_count(str(user.pk), ["course1"])
    assert count == 2

    # Test counting in course with no threads
    count = backend.get_user_threads_count(str(user.pk), ["course3"])
    assert count == 0


@pytest.mark.django_db
def test_get_user_comment_count() -> None:
    """Test counting user comments across multiple courses."""
    user = User.objects.create(username="testuser")
    other_user = User.objects.create(username="otheruser")

    thread = CommentThread.objects.create(
        author=user,
        course_id="course1",
        title="Thread",
        body="Body",
        thread_type="discussion",
    )

    # Create comments for user in different courses
    Comment.objects.create(
        author=user,
        course_id="course1",
        body="Comment 1",
        comment_thread=thread,
    )
    Comment.objects.create(
        author=user,
        course_id="course1",
        body="Comment 2",
        comment_thread=thread,
    )
    Comment.objects.create(
        author=user,
        course_id="course2",
        body="Comment 3",
        comment_thread=thread,
    )
    # Create deleted comment (should not be counted)
    Comment.objects.create(
        author=user,
        course_id="course1",
        body="Deleted Comment",
        comment_thread=thread,
        is_deleted=True,
    )
    # Create comment by other user (should not be counted)
    Comment.objects.create(
        author=other_user,
        course_id="course1",
        body="Other Comment",
        comment_thread=thread,
    )

    # Test counting across specific courses
    count = backend.get_user_comment_count(str(user.pk), ["course1", "course2"])
    assert count == 3

    # Test counting in single course
    count = backend.get_user_comment_count(str(user.pk), ["course1"])
    assert count == 2

    # Test counting in course with no comments
    count = backend.get_user_comment_count(str(user.pk), ["course3"])
    assert count == 0


@pytest.mark.django_db
def test_delete_user_threads() -> None:
    """Test bulk deletion of user threads."""
    user = User.objects.create(username="testuser")
    other_user = User.objects.create(username="otheruser")

    # Create threads
    thread1 = CommentThread.objects.create(
        author=user,
        course_id="course1",
        title="Thread 1",
        body="Body 1",
        thread_type="discussion",
    )
    thread2 = CommentThread.objects.create(
        author=user,
        course_id="course1",
        title="Thread 2",
        body="Body 2",
        thread_type="discussion",
    )
    thread3 = CommentThread.objects.create(
        author=user,
        course_id="course2",
        title="Thread 3",
        body="Body 3",
        thread_type="discussion",
    )
    # Already deleted thread (should be skipped)
    deleted_thread = CommentThread.objects.create(
        author=user,
        course_id="course1",
        title="Deleted Thread",
        body="Deleted",
        thread_type="discussion",
        is_deleted=True,
    )
    # Other user's thread (should not be deleted)
    other_thread = CommentThread.objects.create(
        author=other_user,
        course_id="course1",
        title="Other Thread",
        body="Other",
        thread_type="discussion",
    )

    # Delete threads
    count = backend.delete_user_threads(str(user.pk), ["course1", "course2"])

    # Verify count
    assert count == 3

    # Verify threads are soft-deleted
    thread1.refresh_from_db()
    thread2.refresh_from_db()
    thread3.refresh_from_db()
    assert thread1.is_deleted is True
    assert thread2.is_deleted is True
    assert thread3.is_deleted is True

    # Verify already deleted thread unchanged
    deleted_thread.refresh_from_db()
    assert deleted_thread.is_deleted is True

    # Verify other user's thread not deleted
    other_thread.refresh_from_db()
    assert other_thread.is_deleted is False


@pytest.mark.django_db
def test_delete_user_threads_with_subscriptions() -> None:
    """Test that thread subscriptions are cleaned up during bulk delete."""
    user = User.objects.create(username="testuser")
    subscriber = User.objects.create(username="subscriber")

    # Create thread with subscription
    thread = CommentThread.objects.create(
        author=user,
        course_id="course1",
        title="Thread with Subscription",
        body="Body",
        thread_type="discussion",
    )

    # Create subscription
    Subscription.objects.create(
        subscriber=subscriber,
        source=thread,
    )

    # Verify subscription exists
    assert Subscription.objects.filter(source_object_id=thread.pk).count() == 1

    # Delete threads
    count = backend.delete_user_threads(str(user.pk), ["course1"])
    assert count == 1

    # Verify subscription was deleted
    assert Subscription.objects.filter(source_object_id=thread.pk).count() == 0


@pytest.mark.django_db
def test_delete_user_threads_with_comments() -> None:
    """Test that thread comments are soft-deleted during bulk thread delete."""
    user = User.objects.create(username="testuser")
    commenter = User.objects.create(username="commenter")

    # Create thread
    thread = CommentThread.objects.create(
        author=user,
        course_id="course1",
        title="Thread",
        body="Body",
        thread_type="discussion",
    )

    # Create comments on the thread
    response = Comment.objects.create(
        author=commenter,
        course_id="course1",
        body="Response",
        comment_thread=thread,
    )
    reply = Comment.objects.create(
        author=commenter,
        course_id="course1",
        body="Reply",
        comment_thread=thread,
        parent=response,
    )

    # Delete threads
    count = backend.delete_user_threads(str(user.pk), ["course1"])
    assert count == 1

    # Verify thread is deleted
    thread.refresh_from_db()
    assert thread.is_deleted is True

    # Verify comments are also soft-deleted
    response.refresh_from_db()
    reply.refresh_from_db()
    assert response.is_deleted is True
    assert reply.is_deleted is True


@pytest.mark.django_db
def test_delete_user_threads_stats_rebuild() -> None:
    """Test that stats are rebuilt once per course after bulk thread delete."""
    user = User.objects.create(username="testuser")

    # Create threads in different courses
    CommentThread.objects.create(
        author=user,
        course_id="course1",
        title="Thread 1",
        body="Body 1",
        thread_type="discussion",
    )
    CommentThread.objects.create(
        author=user,
        course_id="course1",
        title="Thread 2",
        body="Body 2",
        thread_type="discussion",
    )
    CommentThread.objects.create(
        author=user,
        course_id="course2",
        title="Thread 3",
        body="Body 3",
        thread_type="discussion",
    )

    # Mock build_course_stats to verify it's called efficiently
    with patch.object(backend, "build_course_stats") as mock_build:
        backend.delete_user_threads(str(user.pk), ["course1", "course2"])

        # Should be called once per course, not once per thread
        assert mock_build.call_count == 2
        mock_build.assert_any_call(str(user.pk), "course1")
        mock_build.assert_any_call(str(user.pk), "course2")


@pytest.mark.django_db
def test_delete_user_comments_replies_first() -> None:
    """Test that replies are deleted before responses to avoid redundant work."""
    user = User.objects.create(username="testuser")

    thread = CommentThread.objects.create(
        author=user,
        course_id="course1",
        title="Thread",
        body="Body",
        thread_type="discussion",
    )

    # Create response and reply by user
    response = Comment.objects.create(
        author=user,
        course_id="course1",
        body="Response",
        comment_thread=thread,
    )
    reply = Comment.objects.create(
        author=user,
        course_id="course1",
        body="Reply",
        comment_thread=thread,
        parent=response,
    )

    # Delete comments
    count = backend.delete_user_comments(str(user.pk), ["course1"])

    # Should count both the response and reply
    assert count == 2

    # Verify both are deleted
    response.refresh_from_db()
    reply.refresh_from_db()
    assert response.is_deleted is True
    assert reply.is_deleted is True


@pytest.mark.django_db
def test_delete_user_comments_parent_child() -> None:
    """Test deleting parent comment also deletes its children."""
    user = User.objects.create(username="testuser")
    other_user = User.objects.create(username="otheruser")

    thread = CommentThread.objects.create(
        author=user,
        course_id="course1",
        title="Thread",
        body="Body",
        thread_type="discussion",
    )

    # Create response by user with child reply by other user
    response = Comment.objects.create(
        author=user,
        course_id="course1",
        body="User Response",
        comment_thread=thread,
    )
    other_reply = Comment.objects.create(
        author=other_user,
        course_id="course1",
        body="Other's Reply",
        comment_thread=thread,
        parent=response,
    )

    # Delete user's comments
    count = backend.delete_user_comments(str(user.pk), ["course1"])

    # Should delete response and its child reply
    assert count == 2

    # Verify parent is deleted
    response.refresh_from_db()
    assert response.is_deleted is True

    # Verify child is also deleted (even though author is different)
    other_reply.refresh_from_db()
    assert other_reply.is_deleted is True


@pytest.mark.django_db
def test_delete_user_comments_stats_rebuild() -> None:
    """Test that stats are rebuilt once per course after bulk comment delete."""
    user = User.objects.create(username="testuser")

    thread = CommentThread.objects.create(
        author=user,
        course_id="course1",
        title="Thread",
        body="Body",
        thread_type="discussion",
    )

    # Create comments in different courses
    Comment.objects.create(
        author=user,
        course_id="course1",
        body="Comment 1",
        comment_thread=thread,
    )
    Comment.objects.create(
        author=user,
        course_id="course1",
        body="Comment 2",
        comment_thread=thread,
    )
    Comment.objects.create(
        author=user,
        course_id="course2",
        body="Comment 3",
        comment_thread=thread,
    )

    # Mock build_course_stats to verify it's called efficiently
    with patch.object(backend, "build_course_stats") as mock_build:
        backend.delete_user_comments(str(user.pk), ["course1", "course2"])

        # Should be called once per course, not once per comment
        assert mock_build.call_count == 2
        mock_build.assert_any_call(str(user.pk), "course1")
        mock_build.assert_any_call(str(user.pk), "course2")


@pytest.mark.django_db
def test_delete_user_comments_skips_already_deleted() -> None:
    """Test that already deleted comments are not processed."""
    user = User.objects.create(username="testuser")

    thread = CommentThread.objects.create(
        author=user,
        course_id="course1",
        title="Thread",
        body="Body",
        thread_type="discussion",
    )

    # Create active comment
    active_comment = Comment.objects.create(
        author=user,
        course_id="course1",
        body="Active Comment",
        comment_thread=thread,
    )
    # Create already deleted comment
    deleted_comment = Comment.objects.create(
        author=user,
        course_id="course1",
        body="Deleted Comment",
        comment_thread=thread,
        is_deleted=True,
    )

    # Delete comments
    count = backend.delete_user_comments(str(user.pk), ["course1"])

    # Should only count the active comment
    assert count == 1

    # Verify active comment is now deleted
    active_comment.refresh_from_db()
    assert active_comment.is_deleted is True

    # Verify already deleted comment is unchanged
    deleted_comment.refresh_from_db()
    assert deleted_comment.is_deleted is True


@pytest.mark.django_db
def test_delete_user_threads_with_deleted_by() -> None:
    """Test that deleted_by is recorded when provided."""
    user = User.objects.create(username="testuser")
    admin = User.objects.create(username="admin")

    # Create thread
    thread = CommentThread.objects.create(
        author=user,
        course_id="course1",
        title="Thread",
        body="Body",
        thread_type="discussion",
    )

    # Delete with deleted_by
    backend.delete_user_threads(str(user.pk), ["course1"], deleted_by=str(admin.pk))

    # Verify deleted_by is set
    thread.refresh_from_db()
    assert thread.is_deleted is True
    assert thread.deleted_by == admin


@pytest.mark.django_db
def test_delete_user_comments_with_deleted_by() -> None:
    """Test that deleted_by is recorded for comments when provided."""
    user = User.objects.create(username="testuser")
    admin = User.objects.create(username="admin")

    thread = CommentThread.objects.create(
        author=user,
        course_id="course1",
        title="Thread",
        body="Body",
        thread_type="discussion",
    )

    # Create comment
    comment = Comment.objects.create(
        author=user,
        course_id="course1",
        body="Comment",
        comment_thread=thread,
    )

    # Delete with deleted_by
    backend.delete_user_comments(str(user.pk), ["course1"], deleted_by=str(admin.pk))

    # Verify deleted_by is set
    comment.refresh_from_db()
    assert comment.is_deleted is True
    assert comment.deleted_by == admin
