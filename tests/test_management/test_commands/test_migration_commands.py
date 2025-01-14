"""Test forum mongodb migration commands."""

from io import StringIO
from typing import Any

import pytest
from bson import ObjectId
from django.core.management import call_command
from django.contrib.auth.models import User  # pylint: disable=E5142
from django.utils import timezone
from pymongo.database import Database

from forum.models import (
    Comment,
    CommentThread,
    CourseStat,
    ForumUser,
    LastReadTime,
    MongoContent,
    ReadState,
    Subscription,
    UserVote,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def patch_enable_mysql_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch enable_mysql_backend_for_course to just return."""
    monkeypatch.setattr(
        "forum.migration_helpers.enable_mysql_backend_for_course",
        lambda course_id: None,
    )


def test_migrate_users(patched_mongodb: Database[Any]) -> None:
    patched_mongodb.users.insert_one(
        {
            "_id": "1",
            "username": "testuser",
            "default_sort_key": "date",
            "course_stats": [
                {
                    "course_id": "test_course",
                    "active_flags": 1,
                    "inactive_flags": 2,
                    "threads": 3,
                    "responses": 4,
                    "replies": 5,
                    "last_activity_at": timezone.now(),
                }
            ],
        }
    )

    call_command("forum_migrate_course_from_mongodb_to_mysql", "test_course")

    user = User.objects.get(pk=1)
    assert user.username == "testuser"
    forum_user = ForumUser.objects.get(user=user)
    assert forum_user.default_sort_key == "date"

    course_stat = CourseStat.objects.get(user=user, course_id="test_course")
    assert course_stat.active_flags == 1
    assert course_stat.inactive_flags == 2
    assert course_stat.threads == 3
    assert course_stat.responses == 4
    assert course_stat.replies == 5


def test_migrate_content(patched_mongodb: Database[Any]) -> None:
    """Test migrate comments and comment threads."""
    comment_thread_id = ObjectId()
    comment_id = ObjectId()
    sub_comment_id = ObjectId()
    patched_mongodb.users.insert_many(
        [
            {
                "_id": "1",
                "username": "testuser",
                "default_sort_key": "date",
                "course_stats": [
                    {
                        "course_id": "test_course",
                    }
                ],
                "read_states": [
                    {
                        "course_id": "test_course",
                        "last_read_times": {str(comment_thread_id): timezone.now()},
                    }
                ],
            },
            {
                "_id": "2",
                "username": "testuser2",
                "default_sort_key": "date",
                "course_stats": [
                    {
                        "course_id": "test_course",
                    }
                ],
                "read_states": [
                    {
                        "course_id": "test_course",
                        "last_read_times": {str(comment_thread_id): timezone.now()},
                    }
                ],
            },
        ]
    )
    patched_mongodb.contents.insert_many(
        [
            {
                "_id": comment_thread_id,
                "_type": "CommentThread",
                "author_id": "1",
                "course_id": "test_course",
                "title": "Test Thread",
                "body": "Test body",
                "created_at": timezone.now(),
                "updated_at": timezone.now(),
                "votes": {"up": ["1"], "down": []},
                "abuse_flaggers": ["1", "2"],
                "historical_abuse_flaggers": ["1", "2"],
                "last_activity_at": timezone.now(),
            },
            {
                "_id": comment_id,
                "_type": "Comment",
                "author_id": "1",
                "course_id": "test_course",
                "body": "Test comment",
                "created_at": timezone.now(),
                "updated_at": timezone.now(),
                "comment_thread_id": comment_thread_id,
                "votes": {"up": [], "down": ["1"]},
                "abuse_flaggers": ["1", "2"],
                "historical_abuse_flaggers": ["1", "2"],
                "depth": 0,
                "sk": f"{comment_id}",
            },
            {
                "_id": sub_comment_id,
                "_type": "Comment",
                "author_id": "1",
                "course_id": "test_course",
                "body": "Test sub comment",
                "created_at": timezone.now(),
                "updated_at": timezone.now(),
                "comment_thread_id": comment_thread_id,
                "votes": {"up": [], "down": ["1"]},
                "abuse_flaggers": ["1", "2"],
                "historical_abuse_flaggers": ["1", "2"],
                "parent_id": comment_id,
                "depth": 1,
                "sk": f"{comment_id}-{sub_comment_id}",
            },
        ]
    )

    user = User.objects.create(id=1, username="testuser")

    call_command("forum_migrate_course_from_mongodb_to_mysql", "test_course")

    mongo_thread = MongoContent.objects.get(mongo_id=comment_thread_id)
    assert mongo_thread
    thread = CommentThread.objects.get(pk=mongo_thread.content_object_id)
    assert thread.title == "Test Thread"
    assert thread.body == "Test body"

    mongo_comment = MongoContent.objects.get(mongo_id=comment_id)
    comment = Comment.objects.get(pk=mongo_comment.content_object_id)
    assert comment.body == "Test comment"
    assert comment.comment_thread == thread
    assert comment.sort_key == f"{comment.pk}"
    assert comment.depth == 0

    mongo_sub_comment = MongoContent.objects.get(mongo_id=sub_comment_id)
    sub_comment = Comment.objects.get(pk=mongo_sub_comment.content_object_id)
    assert sub_comment.body == "Test sub comment"
    assert sub_comment.comment_thread == thread
    assert sub_comment.sort_key == f"{comment.pk}-{sub_comment.pk}"
    assert sub_comment.depth == 1

    assert UserVote.objects.filter(content_object_id=thread.pk, vote=1).exists()
    assert UserVote.objects.filter(content_object_id=comment.pk, vote=-1).exists()

    read_state = ReadState.objects.get(user=user, course_id="test_course")
    assert LastReadTime.objects.filter(read_state=read_state).exists()


def test_migrate_subscriptions(patched_mongodb: Database[Any]) -> None:
    """Test migrate subscriptions."""
    comment_thread_id = ObjectId()
    comment_id = ObjectId()
    patched_mongodb.contents.insert_many(
        [
            {
                "_id": comment_thread_id,
                "_type": "CommentThread",
                "author_id": "1",
                "course_id": "test_course",
                "title": "Test Thread",
                "body": "Test body",
                "created_at": timezone.now(),
                "updated_at": timezone.now(),
                "last_activity_at": timezone.now(),
                "votes": {"up": ["1"], "down": []},
                "abuse_flaggers": [
                    "1",
                ],
                "historical_abuse_flaggers": [
                    "1",
                ],
            },
            {
                "_id": comment_id,
                "_type": "Comment",
                "author_id": "1",
                "course_id": "test_course",
                "body": "Test comment",
                "created_at": timezone.now(),
                "updated_at": timezone.now(),
                "comment_thread_id": comment_thread_id,
                "votes": {"up": [], "down": ["1"]},
                "abuse_flaggers": [
                    "1",
                ],
                "historical_abuse_flaggers": [
                    "1",
                ],
            },
        ]
    )
    patched_mongodb.subscriptions.insert_one(
        {
            "subscriber_id": "1",
            "source_id": str(comment_thread_id),
            "source_type": "CommentThread",
            "source": {"course_id": "test_course"},
            "created_at": timezone.now(),
            "updated_at": timezone.now(),
        }
    )

    user = User.objects.create(pk=1, username="testuser")
    call_command("forum_migrate_course_from_mongodb_to_mysql", "test_course")

    mongo_thread = MongoContent.objects.get(mongo_id=str(comment_thread_id))

    assert Subscription.objects.filter(
        subscriber=user, source_object_id=mongo_thread.content_object_id
    ).exists()


def test_delete_course_data(patched_mongodb: Database[Any]) -> None:
    """Test delete mongo course management command."""
    comment_thread_id = ObjectId()
    comment_id = ObjectId()
    patched_mongodb.users.insert_one(
        {
            "_id": "1",
            "username": "testuser",
            "default_sort_key": "date",
            "course_stats": [
                {
                    "course_id": "test_course",
                }
            ],
            "read_states": [
                {
                    "course_id": "test_course",
                    "last_read_times": {str(comment_thread_id): timezone.now()},
                }
            ],
        }
    )
    patched_mongodb.contents.insert_many(
        [
            {
                "_id": comment_thread_id,
                "_type": "CommentThread",
                "author_id": "1",
                "course_id": "test_course",
                "title": "Test Thread",
                "body": "Test body",
                "created_at": timezone.now(),
                "updated_at": timezone.now(),
                "votes": {"up": ["1"], "down": []},
            },
            {
                "_id": comment_id,
                "_type": "Comment",
                "author_id": "1",
                "course_id": "test_course",
                "body": "Test comment",
                "created_at": timezone.now(),
                "updated_at": timezone.now(),
                "comment_thread_id": comment_thread_id,
                "votes": {"up": [], "down": ["1"]},
            },
        ]
    )
    patched_mongodb.subscriptions.insert_one(
        {
            "subscriber_id": "1",
            "source_id": str(comment_thread_id),
            "source_type": "CommentThread",
            "source": {"course_id": "test_course"},
            "created_at": timezone.now(),
            "updated_at": timezone.now(),
        }
    )

    out = StringIO()
    call_command("forum_delete_course_from_mongodb", "test_course", stdout=out)

    assert len(list(patched_mongodb.users.find())) == 1
    user = patched_mongodb.users.find_one()
    assert user
    assert user["course_stats"] == []
    assert user["read_states"] == []
    assert len(list(patched_mongodb.contents.find())) == 0
    assert len(list(patched_mongodb.subscriptions.find())) == 0

    output = out.getvalue()
    assert "Deleting data for course: test_course" in output
    assert "Cleaned up users collection" in output
    assert "Data deletion completed successfully" in output


def test_delete_dry_run(patched_mongodb: Database[Any]) -> None:
    """Call the command with dry-run option."""
    patched_mongodb.users.insert_one(
        {
            "_id": "1",
            "username": "testuser",
            "default_sort_key": "date",
            "course_stats": [
                {
                    "course_id": "test_course",
                }
            ],
            "read_states": [
                {
                    "course_id": "test_course",
                    "last_read_times": {"000000000000000000000001": timezone.now()},
                }
            ],
        }
    )
    patched_mongodb.contents.insert_one(
        {
            "_id": ObjectId("000000000000000000000001"),
            "_type": "CommentThread",
            "author_id": "1",
            "course_id": "test_course",
            "title": "Test Thread",
            "body": "Test body",
            "created_at": timezone.now(),
            "updated_at": timezone.now(),
            "votes": {"up": ["1"], "down": []},
        }
    )
    out = StringIO()
    call_command(
        "forum_delete_course_from_mongodb", "test_course", "--dry-run", stdout=out
    )

    output = out.getvalue()
    assert "Performing dry run. No data will be deleted." in output
    assert "Dry run completed. No data was deleted." in output
    assert len(list(patched_mongodb.contents.find())) == 1


def test_delete_all_courses(patched_mongodb: Database[Any]) -> None:
    """Mock get_all_course_ids method."""
    patched_mongodb.users.insert_one(
        {
            "_id": "1",
            "username": "testuser",
            "default_sort_key": "date",
            "course_stats": [
                {
                    "course_id": "test_course_1",
                },
                {
                    "course_id": "test_course_2",
                },
            ],
            "read_states": [
                {
                    "course_id": "test_course_1",
                    "last_read_times": {"000000000000000000000001": timezone.now()},
                }
            ],
        }
    )
    patched_mongodb.contents.insert_many(
        [
            {
                "_id": ObjectId("000000000000000000000001"),
                "_type": "CommentThread",
                "author_id": "1",
                "course_id": "test_course_1",
                "title": "Test Thread",
                "body": "Test body",
                "created_at": timezone.now(),
                "updated_at": timezone.now(),
                "votes": {"up": ["1"], "down": []},
            },
            {
                "_id": ObjectId("000000000000000000000002"),
                "_type": "Comment",
                "author_id": "1",
                "course_id": "test_course_2",
                "body": "Test comment",
                "created_at": timezone.now(),
                "updated_at": timezone.now(),
                "comment_thread_id": ObjectId("000000000000000000000001"),
                "votes": {"up": [], "down": ["1"]},
            },
        ]
    )
    out = StringIO()
    call_command("forum_delete_course_from_mongodb", "all", stdout=out)

    output = out.getvalue()
    assert len(list(patched_mongodb.contents.find())) == 0
    assert "Deleting data for course: test_course_1" in output
    assert "Deleting data for course: test_course_2" in output


def test_last_read_times_migration(patched_mongodb: Database[Any]) -> None:
    """Mock test last_read_times migration while migrating read_states of a thread."""
    comment_thread_id = ObjectId()
    deleted_comment_thread_id = ObjectId()
    last_read_time_for_thread = timezone.now()
    patched_mongodb.users.insert_one(
        {
            "_id": "1",
            "username": "testuser",
            "default_sort_key": "date",
            "course_stats": [
                {
                    "course_id": "test_course",
                }
            ],
            "read_states": [
                {
                    "course_id": "test_course",
                    "last_read_times": {
                        str(comment_thread_id): last_read_time_for_thread,
                        str(deleted_comment_thread_id): last_read_time_for_thread,
                    },
                }
            ],
        }
    )
    patched_mongodb.contents.insert_one(
        {
            "_id": comment_thread_id,
            "_type": "CommentThread",
            "author_id": "1",
            "course_id": "test_course",
            "title": "Test Thread",
            "body": "Test body",
            "created_at": timezone.now(),
            "updated_at": timezone.now(),
            "votes": {"up": ["1"], "down": []},
            "abuse_flaggers": ["1"],
            "historical_abuse_flaggers": ["1"],
            "last_activity_at": timezone.now(),
        }
    )

    user = User.objects.create(id=1, username="testuser")

    call_command("forum_migrate_course_from_mongodb_to_mysql", "test_course")

    mongo_thread = MongoContent.objects.get(mongo_id=comment_thread_id)
    assert mongo_thread
    thread = CommentThread.objects.get(pk=mongo_thread.content_object_id)
    assert thread.title == "Test Thread"
    assert thread.body == "Test body"

    read_state = ReadState.objects.get(user=user, course_id="test_course")
    last_read_time = LastReadTime.objects.filter(
        read_state=read_state, comment_thread=thread
    ).first()
    assert last_read_time is not None

    updated_last_read_time_for_thread = timezone.now()
    patched_mongodb.users.update_one(
        {"_id": "1"},
        {
            "$set": {
                "read_states.0.last_read_times": {
                    str(comment_thread_id): updated_last_read_time_for_thread
                }
            }
        },
    )
    call_command("forum_migrate_course_from_mongodb_to_mysql", "test_course")
    updated_last_read_time = LastReadTime.objects.filter(
        read_state=read_state, comment_thread=thread
    ).first()
    assert updated_last_read_time is not None
    assert updated_last_read_time.timestamp > last_read_time.timestamp
