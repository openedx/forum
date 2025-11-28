"""Test forum mongodb migration commands."""

from io import StringIO
from datetime import timedelta
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
from forum.utils import get_trunc_title


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

    User.objects.create(id=1, username="testuser")
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


def test_get_trunc_title() -> None:
    """
    Test the get_trunc_title function for various scenarios:
    - Title shorter than 1024 characters
    - Title exactly 1024 characters long
    - Title longer than 1024 characters
    - Empty title
    """
    # Test case 1: Short title
    title_short = "Short title"
    assert get_trunc_title(title_short) == title_short

    # Test case 2: Title exactly 1024 characters
    title_exact = "a" * 1024
    assert get_trunc_title(title_exact) == title_exact

    # Test case 3: Title longer than 1024 characters
    title_long = "a" * 1025
    expected_long = "a" * 1024
    assert get_trunc_title(title_long) == expected_long

    # Test case 4: Empty title
    title_empty = ""
    assert get_trunc_title(title_empty) == title_empty


# Additional test to validate skipping missing users during migration
def test_skip_missing_user_in_migration(patched_mongodb: Database[Any]) -> None:
    """Ensure missing users are skipped gracefully during migration."""
    comment_thread_id = ObjectId()
    comment_id = ObjectId()

    # No user is inserted here; author_id refers to a non-existent user.
    patched_mongodb.contents.insert_many(
        [
            {
                "_id": comment_thread_id,
                "_type": "CommentThread",
                "author_id": "999",  # Non-existent user
                "course_id": "test_course",
                "title": "Missing Author Thread",
                "body": "Thread with no valid author",
                "created_at": timezone.now(),
                "updated_at": timezone.now(),
                "votes": {"up": ["999"], "down": []},
                "abuse_flaggers": ["999"],
                "historical_abuse_flaggers": ["999"],
                "last_activity_at": timezone.now(),
            },
            {
                "_id": comment_id,
                "_type": "Comment",
                "author_id": "999",  # Non-existent user
                "course_id": "test_course",
                "body": "Comment with no valid author",
                "created_at": timezone.now(),
                "updated_at": timezone.now(),
                "comment_thread_id": comment_thread_id,
                "votes": {"up": [], "down": ["999"]},
                "abuse_flaggers": ["999"],
                "historical_abuse_flaggers": ["999"],
                "depth": 0,
                "sk": f"{comment_id}",
            },
        ]
    )
    patched_mongodb.subscriptions.insert_one(
        {
            "subscriber_id": "999",  # Non-existent user
            "source_id": str(comment_thread_id),
            "source_type": "CommentThread",
            "source": {"course_id": "test_course"},
            "created_at": timezone.now(),
            "updated_at": timezone.now(),
        }
    )

    call_command("forum_migrate_course_from_mongodb_to_mysql", "test_course")

    # Ensure no thread/comment/subscription is created due to missing user
    assert not MongoContent.objects.exists()
    assert not CommentThread.objects.exists()
    assert not Comment.objects.exists()
    assert not Subscription.objects.exists()
    assert not UserVote.objects.exists()


def test_partial_user_existence_migration(patched_mongodb: Database[Any]) -> None:
    """Ensure that content for valid users is migrated and invalid user content is skipped."""
    comment_thread_id_valid = ObjectId()
    comment_thread_id_invalid = ObjectId()
    comment_id_valid = ObjectId()
    comment_id_invalid = ObjectId()

    patched_mongodb.users.insert_one(
        {
            "_id": "100",
            "username": "validuser",
            "default_sort_key": "date",
            "course_stats": [
                {
                    "course_id": "test_course",
                    "active_flags": 1,
                    "inactive_flags": 1,
                    "threads": 1,
                    "responses": 1,
                    "replies": 1,
                    "last_activity_at": timezone.now(),
                }
            ],
        }
    )

    User.objects.create(id=100, username="validuser")

    patched_mongodb.contents.insert_many(
        [
            {
                "_id": comment_thread_id_valid,
                "_type": "CommentThread",
                "author_id": "100",  # valid user
                "course_id": "test_course",
                "title": "Valid Thread",
                "body": "Thread with valid author",
                "created_at": timezone.now(),
                "updated_at": timezone.now(),
                "votes": {"up": ["100"], "down": []},
                "abuse_flaggers": ["100"],
                "historical_abuse_flaggers": ["100"],
                "last_activity_at": timezone.now(),
            },
            {
                "_id": comment_id_valid,
                "_type": "Comment",
                "author_id": "100",  # valid user
                "course_id": "test_course",
                "body": "Valid comment",
                "created_at": timezone.now(),
                "updated_at": timezone.now(),
                "comment_thread_id": comment_thread_id_valid,
                "votes": {"up": [], "down": ["100"]},
                "abuse_flaggers": ["100"],
                "historical_abuse_flaggers": ["100"],
                "depth": 0,
                "sk": f"{comment_id_valid}",
            },
            {
                "_id": comment_thread_id_invalid,
                "_type": "CommentThread",
                "author_id": "999",  # invalid user
                "course_id": "test_course",
                "title": "Invalid Thread",
                "body": "Thread with invalid author",
                "created_at": timezone.now(),
                "updated_at": timezone.now(),
                "votes": {"up": ["999"], "down": []},
                "abuse_flaggers": ["999"],
                "historical_abuse_flaggers": ["999"],
                "last_activity_at": timezone.now(),
            },
            {
                "_id": comment_id_invalid,
                "_type": "Comment",
                "author_id": "999",  # invalid user
                "course_id": "test_course",
                "body": "Invalid comment",
                "created_at": timezone.now(),
                "updated_at": timezone.now(),
                "comment_thread_id": comment_thread_id_invalid,
                "votes": {"up": [], "down": ["999"]},
                "abuse_flaggers": ["999"],
                "historical_abuse_flaggers": ["999"],
                "depth": 0,
                "sk": f"{comment_id_invalid}",
            },
        ]
    )

    call_command("forum_migrate_course_from_mongodb_to_mysql", "test_course")

    # Validate valid content is migrated
    assert MongoContent.objects.filter(mongo_id=comment_thread_id_valid).exists()
    assert MongoContent.objects.filter(mongo_id=comment_id_valid).exists()
    assert CommentThread.objects.exists()
    assert Comment.objects.exists()
    assert UserVote.objects.exists()

    # Validate invalid content is skipped
    assert not MongoContent.objects.filter(mongo_id=comment_thread_id_invalid).exists()
    assert not MongoContent.objects.filter(mongo_id=comment_id_invalid).exists()


def test_migrate_thread_preserves_author_username(
    patched_mongodb: Database[Any],
) -> None:
    """Test that author_username is preserved during thread migration."""
    comment_thread_id = ObjectId()
    patched_mongodb.contents.insert_one(
        {
            "_id": comment_thread_id,
            "_type": "CommentThread",
            "author_id": "1",
            "author_username": "historical_username",
            "course_id": "test_course",
            "title": "Test Thread",
            "body": "Test body",
            "created_at": timezone.now(),
            "updated_at": timezone.now(),
            "votes": {"up": [], "down": []},
            "abuse_flaggers": [],
            "historical_abuse_flaggers": [],
            "last_activity_at": timezone.now(),
        }
    )

    User.objects.create(id=1, username="current_username")
    call_command("forum_migrate_course_from_mongodb_to_mysql", "test_course")

    mongo_thread = MongoContent.objects.get(mongo_id=comment_thread_id)
    thread = CommentThread.objects.get(pk=mongo_thread.content_object_id)
    assert thread.author_username == "historical_username"
    assert thread.author.username == "current_username"


def test_migrate_comment_preserves_author_username(
    patched_mongodb: Database[Any],
) -> None:
    """Test that author_username is preserved during comment migration."""
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
                "votes": {"up": [], "down": []},
                "abuse_flaggers": [],
                "historical_abuse_flaggers": [],
                "last_activity_at": timezone.now(),
            },
            {
                "_id": comment_id,
                "_type": "Comment",
                "author_id": "1",
                "author_username": "historical_username",
                "course_id": "test_course",
                "body": "Test comment",
                "created_at": timezone.now(),
                "updated_at": timezone.now(),
                "comment_thread_id": comment_thread_id,
                "votes": {"up": [], "down": []},
                "abuse_flaggers": [],
                "historical_abuse_flaggers": [],
                "depth": 0,
                "sk": f"{comment_id}",
            },
        ]
    )

    User.objects.create(id=1, username="current_username")
    call_command("forum_migrate_course_from_mongodb_to_mysql", "test_course")

    mongo_comment = MongoContent.objects.get(mongo_id=comment_id)
    comment = Comment.objects.get(pk=mongo_comment.content_object_id)
    assert comment.author_username == "historical_username"
    assert comment.author.username == "current_username"


def test_migrate_thread_preserves_retired_username(
    patched_mongodb: Database[Any],
) -> None:
    """Test that retired_username is preserved during thread migration."""
    comment_thread_id = ObjectId()
    patched_mongodb.contents.insert_one(
        {
            "_id": comment_thread_id,
            "_type": "CommentThread",
            "author_id": "1",
            "retired_username": "retired_user",
            "course_id": "test_course",
            "title": "Test Thread",
            "body": "Test body",
            "created_at": timezone.now(),
            "updated_at": timezone.now(),
            "votes": {"up": [], "down": []},
            "abuse_flaggers": [],
            "historical_abuse_flaggers": [],
            "last_activity_at": timezone.now(),
        }
    )

    User.objects.create(id=1, username="retired_user_abc123")
    call_command("forum_migrate_course_from_mongodb_to_mysql", "test_course")

    mongo_thread = MongoContent.objects.get(mongo_id=comment_thread_id)
    thread = CommentThread.objects.get(pk=mongo_thread.content_object_id)
    assert thread.retired_username == "retired_user"
    assert thread.author_username == "retired_user"


def test_migrate_comment_preserves_retired_username(
    patched_mongodb: Database[Any],
) -> None:
    """Test that retired_username is preserved during comment migration."""
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
                "votes": {"up": [], "down": []},
                "abuse_flaggers": [],
                "historical_abuse_flaggers": [],
                "last_activity_at": timezone.now(),
            },
            {
                "_id": comment_id,
                "_type": "Comment",
                "author_id": "1",
                "retired_username": "retired_user",
                "course_id": "test_course",
                "body": "Test comment",
                "created_at": timezone.now(),
                "updated_at": timezone.now(),
                "comment_thread_id": comment_thread_id,
                "votes": {"up": [], "down": []},
                "abuse_flaggers": [],
                "historical_abuse_flaggers": [],
                "depth": 0,
                "sk": f"{comment_id}",
            },
        ]
    )

    User.objects.create(id=1, username="retired_user_abc123")
    call_command("forum_migrate_course_from_mongodb_to_mysql", "test_course")

    mongo_comment = MongoContent.objects.get(mongo_id=comment_id)
    comment = Comment.objects.get(pk=mongo_comment.content_object_id)
    assert comment.retired_username == "retired_user"
    assert comment.author_username == "retired_user"


def test_migrate_thread_fallback_to_current_username(
    patched_mongodb: Database[Any],
) -> None:
    """Test that migration falls back to current username when author_username is missing."""
    comment_thread_id = ObjectId()
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
            "votes": {"up": [], "down": []},
            "abuse_flaggers": [],
            "historical_abuse_flaggers": [],
            "last_activity_at": timezone.now(),
        }
    )

    User.objects.create(id=1, username="current_username")
    call_command("forum_migrate_course_from_mongodb_to_mysql", "test_course")

    mongo_thread = MongoContent.objects.get(mongo_id=comment_thread_id)
    thread = CommentThread.objects.get(pk=mongo_thread.content_object_id)
    assert thread.author_username == "current_username"


def test_migrate_comment_fallback_to_current_username(
    patched_mongodb: Database[Any],
) -> None:
    """Test that migration falls back to current username when author_username is missing."""
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
                "votes": {"up": [], "down": []},
                "abuse_flaggers": [],
                "historical_abuse_flaggers": [],
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
                "votes": {"up": [], "down": []},
                "abuse_flaggers": [],
                "historical_abuse_flaggers": [],
                "depth": 0,
                "sk": f"{comment_id}",
            },
        ]
    )

    User.objects.create(id=1, username="current_username")
    call_command("forum_migrate_course_from_mongodb_to_mysql", "test_course")

    mongo_comment = MongoContent.objects.get(mongo_id=comment_id)
    comment = Comment.objects.get(pk=mongo_comment.content_object_id)
    assert comment.author_username == "current_username"


def test_migrate_preserves_timestamps(patched_mongodb: Database[Any]) -> None:
    """Test that timestamps are preserved during migration (regression test for issue #261).

    This test verifies that when migrating content from MongoDB to MySQL,
    the original timestamps (created_at, updated_at, last_activity_at) are
    preserved and not overwritten with the migration time.
    """

    comment_thread_id = ObjectId()
    comment_id = ObjectId()

    # Create timestamps that are significantly in the past (30 days ago)
    # This ensures we can clearly distinguish between preserved timestamps
    # and timestamps that would be set to "now" during migration
    now = timezone.now()
    original_created_at = now - timedelta(days=30)
    original_updated_at = now - timedelta(days=15)
    original_last_activity_at = now - timedelta(days=10)
    original_subscription_created_at = now - timedelta(days=25)
    original_subscription_updated_at = now - timedelta(days=5)

    patched_mongodb.users.insert_one(
        {
            "_id": "1",
            "username": "testuser",
            "default_sort_key": "date",
            "course_stats": [{"course_id": "test_course"}],
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
                "created_at": original_created_at,
                "updated_at": original_updated_at,
                "last_activity_at": original_last_activity_at,
                "votes": {"up": [], "down": []},
                "abuse_flaggers": [],
                "historical_abuse_flaggers": [],
            },
            {
                "_id": comment_id,
                "_type": "Comment",
                "author_id": "1",
                "course_id": "test_course",
                "body": "Test comment",
                "created_at": original_created_at,
                "updated_at": original_updated_at,
                "comment_thread_id": comment_thread_id,
                "votes": {"up": [], "down": []},
                "abuse_flaggers": [],
                "historical_abuse_flaggers": [],
                "depth": 0,
                "sk": f"{comment_id}",
            },
        ]
    )
    patched_mongodb.subscriptions.insert_one(
        {
            "subscriber_id": "1",
            "source_id": str(comment_thread_id),
            "source_type": "CommentThread",
            "source": {"course_id": "test_course"},
            "created_at": original_subscription_created_at,
            "updated_at": original_subscription_updated_at,
        }
    )

    User.objects.create(id=1, username="testuser")
    call_command("forum_migrate_course_from_mongodb_to_mysql", "test_course")

    # The key assertion is that timestamps are NOT set to "now" during migration.
    # We verify this by checking that the timestamps are within the expected
    # date range (accounting for potential timezone/precision differences).
    # If timestamps were being set to migration time, they would be ~30 days newer.

    # Verify thread timestamps are preserved (within 1 second tolerance for precision)
    mongo_thread = MongoContent.objects.get(mongo_id=comment_thread_id)
    thread = CommentThread.objects.get(pk=mongo_thread.content_object_id)

    # The timestamp should be approximately 30 days old, not "now"
    thread_created_age = now - thread.created_at
    assert thread_created_age > timedelta(days=29), (
        f"Thread created_at should be ~30 days ago, but is only {thread_created_age} ago. "
        "Timestamps are not being preserved during migration!"
    )

    thread_updated_age = now - thread.updated_at
    assert thread_updated_age > timedelta(days=14), (
        f"Thread updated_at should be ~15 days ago, but is only {thread_updated_age} ago. "
        "Timestamps are not being preserved during migration!"
    )

    thread_last_activity_age = now - thread.last_activity_at
    assert thread_last_activity_age > timedelta(days=9), (
        f"Thread last_activity_at should be ~10 days ago, but is only {thread_last_activity_age} ago. "
        "Timestamps are not being preserved during migration!"
    )

    # Verify comment timestamps are preserved
    mongo_comment = MongoContent.objects.get(mongo_id=comment_id)
    comment = Comment.objects.get(pk=mongo_comment.content_object_id)

    comment_created_age = now - comment.created_at
    assert comment_created_age > timedelta(days=29), (
        f"Comment created_at should be ~30 days ago, but is only {comment_created_age} ago. "
        "Timestamps are not being preserved during migration!"
    )

    comment_updated_age = now - comment.updated_at
    assert comment_updated_age > timedelta(days=14), (
        f"Comment updated_at should be ~15 days ago, but is only {comment_updated_age} ago. "
        "Timestamps are not being preserved during migration!"
    )

    # Verify subscription timestamps are preserved
    subscription = Subscription.objects.get(
        subscriber_id=1, source_object_id=mongo_thread.content_object_id
    )

    subscription_created_age = now - subscription.created_at
    assert subscription_created_age > timedelta(days=24), (
        f"Subscription created_at should be ~25 days ago, but is only {subscription_created_age} ago. "
        "Timestamps are not being preserved during migration!"
    )

    subscription_updated_age = now - subscription.updated_at
    assert subscription_updated_age > timedelta(days=4), (
        f"Subscription updated_at should be ~5 days ago, but is only {subscription_updated_age} ago. "
        "Timestamps are not being preserved during migration!"
    )
