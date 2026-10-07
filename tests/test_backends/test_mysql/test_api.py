"""Tests for db client."""

import unittest
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from forum.backends.mysql.api import MySQLBackend as backend
from forum.backends.mysql.models import AbuseFlagger, Comment, CommentThread, CourseStat
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
def test_threads_presentor_includes_endorsed_status() -> None:
    """Test that threads_presentor marks threads with an endorsed response as endorsed."""
    user = User.objects.create(username="testuser")
    course_id = "course123"
    answered_thread = CommentThread.objects.create(
        author=user,
        course_id=course_id,
        title="Answered question",
        body="This question has an endorsed response",
        thread_type="question",
        context="course",
    )
    unanswered_thread = CommentThread.objects.create(
        author=user,
        course_id=course_id,
        title="Unanswered question",
        body="This question has no endorsed response",
        thread_type="question",
        context="course",
    )
    Comment.objects.create(
        author=user,
        course_id=course_id,
        body="Endorsed response",
        comment_thread=answered_thread,
        endorsed=True,
    )
    Comment.objects.create(
        author=user,
        course_id=course_id,
        body="Unendorsed response",
        comment_thread=unanswered_thread,
    )

    presented = backend.threads_presentor(
        [str(answered_thread.pk), str(unanswered_thread.pk)],
        str(user.pk),
        course_id,
    )

    endorsed_by_id = {str(thread["_id"]): thread["endorsed"] for thread in presented}
    assert endorsed_by_id == {
        str(answered_thread.pk): True,
        str(unanswered_thread.pk): False,
    }


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


@pytest.mark.django_db
def test_flag_and_unflag_thread_as_spam() -> None:
    """AI moderation marks a thread as spam through the backend, and can undo it."""
    author = User.objects.create(username="spam-thread-author")
    thread = CommentThread.objects.create(
        author=author,
        course_id="course123",
        title="Buy followers now",
        body="Message me on WhatsApp",
        thread_type="discussion",
        context="course",
    )

    assert backend.flag_content_as_spam("CommentThread", str(thread.pk)) == 1
    thread.refresh_from_db()
    assert thread.is_spam is True

    assert backend.unflag_content_as_spam("CommentThread", str(thread.pk)) == 1
    thread.refresh_from_db()
    assert thread.is_spam is False


@pytest.mark.django_db
def test_flag_and_unflag_comment_as_spam() -> None:
    """Anything that is not a thread is flagged as a comment."""
    author = User.objects.create(username="spam-comment-author")
    thread = CommentThread.objects.create(
        author=author,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    comment = Comment.objects.create(
        author=author,
        comment_thread=thread,
        course_id="course123",
        body="Guaranteed returns, DM me",
    )

    assert backend.flag_content_as_spam("Comment", str(comment.pk)) == 1
    comment.refresh_from_db()
    assert comment.is_spam is True

    assert backend.unflag_content_as_spam("Comment", str(comment.pk)) == 1
    comment.refresh_from_db()
    assert comment.is_spam is False


@pytest.mark.django_db
def test_is_spam_is_only_written_when_passed() -> None:
    """An update that says nothing about spam leaves the flag alone."""
    author = User.objects.create(username="untouched-author")
    thread = CommentThread.objects.create(
        author=author,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
        is_spam=True,
    )
    comment = Comment.objects.create(
        author=author,
        comment_thread=thread,
        course_id="course123",
        body="A comment",
        is_spam=True,
    )

    backend.update_thread(str(thread.pk), title="Edited title")
    backend.update_comment(str(comment.pk), body="Edited body")

    thread.refresh_from_db()
    comment.refresh_from_db()
    assert thread.is_spam is True
    assert comment.is_spam is True
