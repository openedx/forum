"""Tests for mysql models."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError
from django.utils import timezone

from forum.backends.mysql.models import (
    AbuseFlagger,
    Comment,
    CommentThread,
    CourseStat,
    EditHistory,
    ForumUser,
    HistoricalAbuseFlagger,
    LastReadTime,
    ReadState,
    Subscription,
    UserVote,
)

User = get_user_model()


@pytest.mark.django_db
def test_forum_user_creation() -> None:
    """Test that a ForumUser is created when a User is created."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    forum_user = ForumUser.objects.create(user=user, default_sort_key="date")
    assert forum_user.user == user
    assert forum_user.default_sort_key == "date"


@pytest.mark.django_db
def test_forum_user_unique_constraint() -> None:
    """Test that a ForumUser is not created when a User already has one."""
    user1 = User.objects.create(
        username="testuser1", email="test1@example.com", password="password"
    )
    ForumUser.objects.create(user=user1, default_sort_key="date")
    with pytest.raises(IntegrityError):
        ForumUser.objects.create(user=user1, default_sort_key="date")


@pytest.mark.django_db
def test_forum_user_default_sort_key_default_value() -> None:
    """Test that the default_sort_key is set to 'date' when not provided."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    forum_user = ForumUser.objects.create(user=user)
    assert forum_user.default_sort_key == "date"


@pytest.mark.django_db
def test_course_stat_creation() -> None:
    """Test that a CourseStat is created when a Course is created."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    course_stat = CourseStat.objects.create(user=user, course_id="course123")
    assert course_stat.user == user
    assert course_stat.course_id == "course123"
    assert course_stat.active_flags == 0
    assert course_stat.inactive_flags == 0
    assert course_stat.threads == 0
    assert course_stat.responses == 0
    assert course_stat.replies == 0
    assert course_stat.last_activity_at is None


@pytest.mark.django_db
def test_course_stat_unique_constraint() -> None:
    """Test that a CourseStat is not created when a User already has one."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    CourseStat.objects.create(user=user, course_id="course123")
    with pytest.raises(IntegrityError):
        CourseStat.objects.create(user=user, course_id="course123")


@pytest.mark.django_db
def test_comment_thread_creation() -> None:
    """Test that a CommentThread is created when a Comment is created."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    assert comment_thread.author == user
    assert comment_thread.course_id == "course123"
    assert comment_thread.title == "Test Thread"
    assert comment_thread.body == "This is a test thread"
    assert comment_thread.thread_type == "discussion"
    assert comment_thread.context == "course"
    assert comment_thread.closed is False
    assert comment_thread.pinned is None


@pytest.mark.django_db
def test_comment_creation() -> None:
    """Test that a Comment is created when a CommentThread is created."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    comment = Comment.objects.create(
        author=user,
        course_id="course123",
        body="This is a test comment",
        comment_thread=comment_thread,
    )
    assert comment.author == user
    assert comment.course_id == "course123"
    assert comment.body == "This is a test comment"
    assert comment.comment_thread == comment_thread
    assert comment.endorsement == {}
    assert comment.sort_key is None


@pytest.mark.django_db
def test_comment_thread_update() -> None:
    """Test that a Comment's thread is updated when the thread is updated."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    comment_thread.title = "Updated Title"
    comment_thread.body = "Updated Body"
    comment_thread.save()
    assert comment_thread.title == "Updated Title"
    assert comment_thread.body == "Updated Body"


@pytest.mark.django_db
def test_comment_update() -> None:
    """Test that a Comment's body is updated when the comment is updated."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    comment = Comment.objects.create(
        author=user,
        course_id="course123",
        body="This is a test comment",
        comment_thread=comment_thread,
    )
    comment.body = "Updated Comment"
    comment.save()
    assert comment.body == "Updated Comment"


@pytest.mark.django_db
def test_forum_user_update() -> None:
    """Test that a ForumUser's data is updated when the user is updated."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    forum_user = ForumUser.objects.create(user=user, default_sort_key="date")
    forum_user.default_sort_key = "votes"
    forum_user.save()
    assert forum_user.default_sort_key == "votes"


@pytest.mark.django_db
def test_comment_thread_delete() -> None:
    """Test that a CommentThread's data is deleted when the thread is deleted."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    comment_thread.delete()
    assert CommentThread.objects.filter(id=comment_thread.pk).count() == 0


@pytest.mark.django_db
def test_comment_delete() -> None:
    """Test that a Comment's data is deleted when the comment is deleted."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    comment = Comment.objects.create(
        author=user,
        course_id="course123",
        body="This is a test comment",
        comment_thread=comment_thread,
    )
    comment.delete()
    assert Comment.objects.filter(id=comment.pk).count() == 0


@pytest.mark.django_db
def test_forum_user_delete() -> None:
    """Test that a ForumUser's data is deleted when the user is deleted."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    forum_user = ForumUser.objects.create(user=user, default_sort_key="date")
    forum_user.delete()
    assert ForumUser.objects.filter(id=forum_user.pk).count() == 0


@pytest.mark.django_db
def test_edit_history_creation() -> None:
    """Test that an EditHistory is created when a Comment is edited."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    edit_history = EditHistory.objects.create(
        reason_code="grammar-spelling",
        original_body="Original body",
        editor=user,
        content=comment_thread,
    )
    assert edit_history.reason_code == "grammar-spelling"
    assert edit_history.original_body == "Original body"
    assert edit_history.editor == user
    assert edit_history.content == comment_thread


@pytest.mark.django_db
def test_edit_history_update() -> None:
    """Test that an EditHistory is updated when a Comment is edited."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    edit_history = EditHistory.objects.create(
        reason_code="grammar-spelling",
        original_body="Original body",
        editor=user,
        content=comment_thread,
    )
    edit_history.reason_code = "needs-clarity"
    edit_history.save()
    assert edit_history.reason_code == "needs-clarity"


@pytest.mark.django_db
def test_edit_history_delete() -> None:
    """Test that an EditHistory is deleted when a Comment is deleted."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    edit_history = EditHistory.objects.create(
        reason_code="grammar-spelling",
        original_body="Original body",
        editor=user,
        content=comment_thread,
    )
    edit_history.delete()
    assert EditHistory.objects.filter(id=edit_history.pk).count() == 0


@pytest.mark.django_db
def test_abuseflagger_creation() -> None:
    """Test that an AbuseFlagger is created when a Comment is flagged."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    abuseflagger = AbuseFlagger.objects.create(
        user=user, content=comment_thread, flagged_at=timezone.now()
    )
    assert abuseflagger.user == user
    assert abuseflagger.content == comment_thread
    assert abuseflagger.flagged_at is not None


@pytest.mark.django_db
def test_abuseflagger_update() -> None:
    """Test that an AbuseFlagger is updated when a Comment is flagged."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    abuseflagger = AbuseFlagger.objects.create(
        user=user, content=comment_thread, flagged_at=timezone.now()
    )
    update_flagged_at = timezone.now() + timedelta(hours=1)
    abuseflagger.flagged_at = update_flagged_at
    abuseflagger.save()
    assert abuseflagger.flagged_at == update_flagged_at


@pytest.mark.django_db
def test_abuseflagger_delete() -> None:
    """Test that an AbuseFlagger is deleted when a Comment is unflagged."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    abuseflagger = AbuseFlagger.objects.create(
        user=user, content=comment_thread, flagged_at=timezone.now()
    )
    abuseflagger.delete()
    assert AbuseFlagger.objects.filter(id=abuseflagger.pk).count() == 0


@pytest.mark.django_db
def test_historicalabuseflagger_creation() -> None:
    """Test that a HistoricalAbuseFlagger is created when an AbuseFlagger is updated."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    historicalabuseflagger = HistoricalAbuseFlagger.objects.create(
        user=user, content=comment_thread, flagged_at=timezone.now()
    )
    assert historicalabuseflagger.user == user
    assert historicalabuseflagger.content == comment_thread
    assert historicalabuseflagger.flagged_at is not None


@pytest.mark.django_db
def test_historicalabuseflagger_update() -> None:
    """Test that a HistoricalAbuseFlagger is updated when an AbuseFlagger is updated."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    historicalabuseflagger = HistoricalAbuseFlagger.objects.create(
        user=user, content=comment_thread, flagged_at=timezone.now()
    )
    update_flagged_at = timezone.now() + timedelta(hours=1)
    historicalabuseflagger.flagged_at = update_flagged_at
    historicalabuseflagger.save()
    assert historicalabuseflagger.flagged_at == update_flagged_at


@pytest.mark.django_db
def test_historicalabuseflagger_delete() -> None:
    """Test that a HistoricalAbuseFlagger is deleted when an AbuseFlagger is deleted."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    historicalabuseflagger = HistoricalAbuseFlagger.objects.create(
        user=user, content=comment_thread, flagged_at=timezone.now()
    )
    historicalabuseflagger.delete()
    assert (
        HistoricalAbuseFlagger.objects.filter(id=historicalabuseflagger.pk).count() == 0
    )


@pytest.mark.django_db
def test_readstate_creation() -> None:
    """Test that a ReadState is created when a user reads a comment thread."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    course_id = "course123"
    read_state = ReadState.objects.create(user=user, course_id=course_id)
    assert read_state.user == user
    assert read_state.course_id == course_id


@pytest.mark.django_db
def test_readstate_update() -> None:
    """Test that a ReadState is updated when a user reads a comment thread."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    course_id = "course123"
    read_state = ReadState.objects.create(user=user, course_id=course_id)
    new_course_id = "course456"
    read_state.course_id = new_course_id
    read_state.save()
    assert read_state.course_id == new_course_id


@pytest.mark.django_db
def test_readstate_delete() -> None:
    """Test that a ReadState is deleted when a user is deleted."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    course_id = "course123"
    read_state = ReadState.objects.create(user=user, course_id=course_id)
    read_state.delete()
    assert ReadState.objects.filter(id=read_state.pk).count() == 0


@pytest.mark.django_db
def test_lastreadtime_creation() -> None:
    """Test that a LastReadTime is created when a user reads a comment thread."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    course_id = "course123"
    read_state = ReadState.objects.create(user=user, course_id=course_id)
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id=course_id,
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    last_read_time = LastReadTime.objects.create(
        read_state=read_state, comment_thread=comment_thread, timestamp=timezone.now()
    )
    assert last_read_time.read_state == read_state
    assert last_read_time.comment_thread == comment_thread
    assert last_read_time.timestamp is not None


@pytest.mark.django_db
def test_lastreadtime_update() -> None:
    """Test that a LastReadTime is updated when a user reads a comment thread."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    course_id = "course123"
    read_state = ReadState.objects.create(user=user, course_id=course_id)
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id=course_id,
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    last_read_time = LastReadTime.objects.create(
        read_state=read_state, comment_thread=comment_thread, timestamp=timezone.now()
    )
    new_timestamp = timezone.now() + timedelta(hours=1)
    last_read_time.timestamp = new_timestamp
    last_read_time.save()
    assert last_read_time.timestamp == new_timestamp


@pytest.mark.django_db
def test_lastreadtime_delete() -> None:
    """Test that a LastReadTime is deleted when a user's read state is deleted."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    course_id = "course123"
    read_state = ReadState.objects.create(user=user, course_id=course_id)
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id=course_id,
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    last_read_time = LastReadTime.objects.create(
        read_state=read_state, comment_thread=comment_thread, timestamp=timezone.now()
    )
    last_read_time.delete()
    assert LastReadTime.objects.filter(id=last_read_time.pk).count() == 0


@pytest.mark.django_db
def test_lastreadtime_multiple_read_states() -> None:
    """Test that a LastReadTime is created for each read state when a user reads a comment."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    course_id1 = "course123"
    course_id2 = "course456"
    read_state1 = ReadState.objects.create(user=user, course_id=course_id1)
    read_state2 = ReadState.objects.create(user=user, course_id=course_id2)
    comment_thread1 = CommentThread.objects.create(
        author=user,
        course_id=course_id1,
        title="Test Thread 1",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    comment_thread2 = CommentThread.objects.create(
        author=user,
        course_id=course_id2,
        title="Test Thread 2",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    last_read_time1 = LastReadTime.objects.create(
        read_state=read_state1, comment_thread=comment_thread1, timestamp=timezone.now()
    )
    last_read_time2 = LastReadTime.objects.create(
        read_state=read_state2, comment_thread=comment_thread2, timestamp=timezone.now()
    )
    assert last_read_time1.read_state == read_state1
    assert last_read_time1.comment_thread == comment_thread1
    assert last_read_time2.read_state == read_state2
    assert last_read_time2.comment_thread == comment_thread2


@pytest.mark.django_db
def test_lastreadtime_multiple_comment_threads() -> None:
    """Test that a LastReadTime is created for each comment thread when a user reads a comment."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    course_id = "course123"
    read_state = ReadState.objects.create(user=user, course_id=course_id)
    comment_thread1 = CommentThread.objects.create(
        author=user,
        course_id=course_id,
        title="Test Thread 1",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    comment_thread2 = CommentThread.objects.create(
        author=user,
        course_id=course_id,
        title="Test Thread 2",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    last_read_time1 = LastReadTime.objects.create(
        read_state=read_state, comment_thread=comment_thread1, timestamp=timezone.now()
    )
    last_read_time2 = LastReadTime.objects.create(
        read_state=read_state, comment_thread=comment_thread2, timestamp=timezone.now()
    )
    assert last_read_time1.read_state == read_state
    assert last_read_time1.comment_thread == comment_thread1
    assert last_read_time2.read_state == read_state
    assert last_read_time2.comment_thread == comment_thread2


@pytest.mark.django_db
def test_readstate_multiple_last_read_times() -> None:
    """Test that a ReadState can have multiple LastReadTime instances."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    course_id = "course123"
    read_state = ReadState.objects.create(user=user, course_id=course_id)
    comment_thread1 = CommentThread.objects.create(
        author=user,
        course_id=course_id,
        title="Test Thread 1",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    comment_thread2 = CommentThread.objects.create(
        author=user,
        course_id=course_id,
        title="Test Thread 2",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    LastReadTime.objects.create(
        read_state=read_state, comment_thread=comment_thread1, timestamp=timezone.now()
    )
    LastReadTime.objects.create(
        read_state=read_state, comment_thread=comment_thread2, timestamp=timezone.now()
    )
    assert read_state.last_read_times.count() == 2
    assert read_state.last_read_times.filter(comment_thread=comment_thread1).exists()
    assert read_state.last_read_times.filter(comment_thread=comment_thread2).exists()


@pytest.mark.django_db
def test_readstate_last_read_time_update() -> None:
    """Test that updating a LastReadTime instance updates the read state's last read time."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    course_id = "course123"
    read_state = ReadState.objects.create(user=user, course_id=course_id)
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id=course_id,
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    last_read_time = LastReadTime.objects.create(
        read_state=read_state, comment_thread=comment_thread, timestamp=timezone.now()
    )
    new_timestamp = timezone.now() + timedelta(hours=1)
    last_read_time.timestamp = new_timestamp
    last_read_time.save()
    assert (
        read_state.last_read_times.get(comment_thread=comment_thread).timestamp
        == new_timestamp
    )


@pytest.mark.django_db
def test_readstate_last_read_time_delete() -> None:
    """Test that deleting a LastReadTime instance removes it from the read state's last read times."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    course_id = "course123"
    read_state = ReadState.objects.create(user=user, course_id=course_id)
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id=course_id,
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    last_read_time = LastReadTime.objects.create(
        read_state=read_state, comment_thread=comment_thread, timestamp=timezone.now()
    )
    last_read_time.delete()
    assert not read_state.last_read_times.filter(comment_thread=comment_thread).exists()


@pytest.mark.django_db
def test_uservotes_creation() -> None:
    """Test that creating a UserVote instance creates a vote for the user."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    content = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    uservote = UserVote.objects.create(user=user, content=content, vote=1)
    assert uservote.user == user
    assert uservote.content == content
    assert uservote.vote == 1


@pytest.mark.django_db
def test_uservotes_update() -> None:
    """Test that updating a UserVote instance updates the vote for the user."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    content = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    uservote = UserVote.objects.create(user=user, content=content, vote=1)
    uservote.vote = -1
    uservote.save()
    assert uservote.vote == -1


@pytest.mark.django_db
def test_uservotes_delete() -> None:
    """Test that deleting a UserVote instance removes the vote for the user."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    content = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    uservote = UserVote.objects.create(user=user, content=content, vote=1)
    uservote.delete()
    assert UserVote.objects.filter(id=uservote.pk).count() == 0


@pytest.mark.django_db
def test_uservotes_generic_foreign_key() -> None:
    """Test that the generic foreign key is correctly set."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    content1 = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread 1",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    content2 = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Post",
        body="This is a test post",
    )
    uservote1 = UserVote.objects.create(user=user, content=content1, vote=1)
    uservote2 = UserVote.objects.create(user=user, content=content2, vote=-1)
    assert uservote1.content_type == ContentType.objects.get_for_model(CommentThread)
    assert uservote2.content_type == ContentType.objects.get_for_model(CommentThread)


@pytest.mark.django_db
def test_subscription_creation() -> None:
    """Test that a subscription is created when a user votes on a content."""
    content_type = ContentType.objects.get_for_model(CommentThread)
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    subscription = Subscription.objects.create(
        subscriber=user, source_content_type=content_type, source_object_id=1
    )
    assert subscription.subscriber == user
    assert subscription.source_content_type == content_type
    assert subscription.source_object_id == 1


@pytest.mark.django_db
def test_subscription_unique_together() -> None:
    """Test that the unique together constraint is enforced."""
    content_type = ContentType.objects.get_for_model(CommentThread)
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    Subscription.objects.create(
        subscriber=user, source_content_type=content_type, source_object_id=1
    )
    with pytest.raises(IntegrityError):
        Subscription.objects.create(
            subscriber=user, source_content_type=content_type, source_object_id=1
        )


@pytest.mark.django_db
def test_comment_thread_author_username_set_on_creation() -> None:
    """Test that author_username is automatically set on CommentThread creation."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    assert comment_thread.author_username == "testuser"


@pytest.mark.django_db
def test_comment_author_username_set_on_creation() -> None:
    """Test that author_username is automatically set on Comment creation."""
    user = User.objects.create(
        username="testuser", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    comment = Comment.objects.create(
        author=user,
        course_id="course123",
        body="This is a test comment",
        comment_thread=comment_thread,
    )
    assert comment.author_username == "testuser"


@pytest.mark.django_db
def test_comment_thread_author_username_preserved_when_provided() -> None:
    """Test that author_username is preserved when explicitly provided."""
    user = User.objects.create(
        username="newusername", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        author_username="originalusername",
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    assert comment_thread.author_username == "originalusername"


@pytest.mark.django_db
def test_comment_author_username_preserved_when_provided() -> None:
    """Test that author_username is preserved when explicitly provided."""
    user = User.objects.create(
        username="newusername", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    comment = Comment.objects.create(
        author=user,
        author_username="originalusername",
        course_id="course123",
        body="This is a test comment",
        comment_thread=comment_thread,
    )
    assert comment.author_username == "originalusername"


@pytest.mark.django_db
def test_comment_thread_retired_username_priority_on_creation() -> None:
    """Test that retired_username takes priority when set during creation."""
    user = User.objects.create(
        username="retired_user_abc123", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        retired_username="originaluser",
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    # retired_username should be used as author_username
    assert comment_thread.author_username == "originaluser"
    assert comment_thread.retired_username == "originaluser"


@pytest.mark.django_db
def test_comment_retired_username_priority_on_creation() -> None:
    """Test that retired_username takes priority when set during creation."""
    user = User.objects.create(
        username="retired_user_abc123", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    comment = Comment.objects.create(
        author=user,
        retired_username="originaluser",
        course_id="course123",
        body="This is a test comment",
        comment_thread=comment_thread,
    )
    # retired_username should be used as author_username
    assert comment.author_username == "originaluser"
    assert comment.retired_username == "originaluser"


@pytest.mark.django_db
def test_comment_thread_to_dict_uses_author_username() -> None:
    """Test that to_dict uses author_username when available."""
    user = User.objects.create(
        username="currentuser", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        author_username="historicaluser",
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    thread_dict = comment_thread.to_dict()
    assert thread_dict["author_username"] == "historicaluser"


@pytest.mark.django_db
def test_comment_to_dict_uses_author_username() -> None:
    """Test that to_dict uses author_username when available."""
    user = User.objects.create(
        username="currentuser", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    comment = Comment.objects.create(
        author=user,
        author_username="historicaluser",
        course_id="course123",
        body="This is a test comment",
        comment_thread=comment_thread,
    )
    comment_dict = comment.to_dict()
    assert comment_dict["author_username"] == "historicaluser"


@pytest.mark.django_db
def test_comment_thread_to_dict_fallback_to_retired_username() -> None:
    """Test that to_dict falls back to retired_username when author_username is None."""
    user = User.objects.create(
        username="retired_user_abc123", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        retired_username="retireduser",
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    # Manually set author_username to None to test fallback
    comment_thread.author_username = None
    comment_thread.save(update_fields=["author_username"])

    thread_dict = comment_thread.to_dict()
    assert thread_dict["author_username"] == "retireduser"


@pytest.mark.django_db
def test_comment_to_dict_fallback_to_retired_username() -> None:
    """Test that to_dict falls back to retired_username when author_username is None."""
    user = User.objects.create(
        username="retired_user_abc123", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    comment = Comment.objects.create(
        author=user,
        retired_username="retireduser",
        course_id="course123",
        body="This is a test comment",
        comment_thread=comment_thread,
    )
    # Manually set author_username to None to test fallback
    comment.author_username = None
    comment.save(update_fields=["author_username"])

    comment_dict = comment.to_dict()
    assert comment_dict["author_username"] == "retireduser"


@pytest.mark.django_db
def test_comment_thread_to_dict_fallback_to_current_username() -> None:
    """Test that to_dict falls back to current username when both author_username and retired_username are None."""
    user = User.objects.create(
        username="currentuser", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    # Manually set both to None to test final fallback
    comment_thread.author_username = None
    comment_thread.retired_username = None
    comment_thread.save(update_fields=["author_username", "retired_username"])

    thread_dict = comment_thread.to_dict()
    assert thread_dict["author_username"] == "currentuser"


@pytest.mark.django_db
def test_comment_to_dict_fallback_to_current_username() -> None:
    """Test that to_dict falls back to current username when both author_username and retired_username are None."""
    user = User.objects.create(
        username="currentuser", email="test@example.com", password="password"
    )
    comment_thread = CommentThread.objects.create(
        author=user,
        course_id="course123",
        title="Test Thread",
        body="This is a test thread",
        thread_type="discussion",
        context="course",
    )
    comment = Comment.objects.create(
        author=user,
        course_id="course123",
        body="This is a test comment",
        comment_thread=comment_thread,
    )
    # Manually set both to None to test final fallback
    comment.author_username = None
    comment.retired_username = None
    comment.save(update_fields=["author_username", "retired_username"])

    comment_dict = comment.to_dict()
    assert comment_dict["author_username"] == "currentuser"
