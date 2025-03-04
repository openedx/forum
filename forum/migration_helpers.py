"""Migration commands helper methods."""

from typing import Any

from django.contrib.auth.models import User  # pylint: disable=E5142
from django.core.management.base import OutputWrapper
from django.utils import timezone
from pymongo.collection import Collection
from pymongo.database import Database

from forum.models import (
    AbuseFlagger,
    Comment,
    CommentThread,
    CourseStat,
    EditHistory,
    ForumUser,
    HistoricalAbuseFlagger,
    LastReadTime,
    MongoContent,
    ReadState,
    Subscription,
    UserVote,
)
from forum.utils import make_aware, get_trunc_title


def get_all_course_ids(db: Database[dict[str, Any]]) -> list[str]:
    """Get all course IDs from MongoDB."""
    return db.contents.distinct("course_id")


def migrate_users(db: Database[dict[str, Any]], course_id: str) -> None:
    """Migrate users from MongoDB to MySQL."""
    users = db.users.find({"course_stats.course_id": course_id})
    for user_data in users:
        user, _ = User.objects.get_or_create(
            id=int(user_data["_id"]), defaults={"username": user_data["username"]}
        )

        _, _ = ForumUser.objects.get_or_create(
            user=user,
            defaults={"default_sort_key": user_data.get("default_sort_key", "date")},
        )

        for stat in user_data.get("course_stats", []):
            last_activity_at = stat.get("last_activity_at")
            if last_activity_at:
                last_activity_at = make_aware(last_activity_at)
            if stat["course_id"] == course_id:
                CourseStat.objects.update_or_create(
                    user=user,
                    course_id=course_id,
                    defaults={
                        "active_flags": stat.get("active_flags", 0),
                        "inactive_flags": stat.get("inactive_flags", 0),
                        "threads": stat.get("threads", 0),
                        "responses": stat.get("responses", 0),
                        "replies": stat.get("replies", 0),
                        "last_activity_at": last_activity_at,
                    },
                )


def migrate_content(db: Database[dict[str, Any]], course_id: str) -> None:
    """Migrate content from MongoDB to MySQL."""
    contents = db.contents.find({"course_id": course_id})
    for content in contents:
        if content["_type"] == "CommentThread":
            create_or_update_thread(content)
        elif content["_type"] == "Comment":
            create_or_update_comment(content)

        migrate_subscriptions(db, content["_id"])


def create_or_update_thread(thread_data: dict[str, Any]) -> None:
    """Create or update a thread."""
    author = User.objects.get(id=int(thread_data["author_id"]))
    mongo_thread_id = str(thread_data["_id"])
    mongo_content, _ = MongoContent.objects.get_or_create(
        mongo_id=mongo_thread_id,
    )
    if not mongo_content.content_object_id:
        thread = CommentThread.objects.create(
            author=author,
            course_id=thread_data["course_id"],
            title=get_trunc_title(thread_data.get("title", "")),
            body=thread_data["body"],
            thread_type=thread_data.get("thread_type", "discussion"),
            context=thread_data.get("context", "course"),
            anonymous=thread_data.get("anonymous", False),
            anonymous_to_peers=thread_data.get("anonymous_to_peers", False),
            closed=thread_data.get("closed", False),
            pinned=thread_data.get("pinned"),
            created_at=make_aware(thread_data["created_at"]),
            updated_at=make_aware(thread_data["updated_at"]),
            last_activity_at=make_aware(thread_data["last_activity_at"]),
            commentable_id=thread_data.get("commentable_id"),
        )
        mongo_content.content_object_id = thread.pk
        mongo_content.content_type = thread.content_type
        mongo_content.save()
    else:
        thread = CommentThread.objects.get(pk=mongo_content.content_object_id)

    create_or_update_edit_history(thread_data)
    create_or_update_abuse_flaggers(thread_data)
    create_votes(thread, thread_data.get("votes", {}))


def create_or_update_comment(comment_data: dict[str, Any]) -> None:
    """Create or update a comment."""
    author = User.objects.get(id=int(comment_data["author_id"]))
    mongo_thread_id = str(comment_data["comment_thread_id"])
    mongo_thread = MongoContent.objects.get(mongo_id=mongo_thread_id)
    thread = CommentThread.objects.get(pk=mongo_thread.content_object_id)
    parent = None
    if "parent_id" in comment_data and comment_data["parent_id"] != "None":
        parent_id = str(comment_data["parent_id"])
        mongo_parent_comment = MongoContent.objects.get(mongo_id=parent_id)
        parent = Comment.objects.filter(
            id=mongo_parent_comment.content_object_id
        ).first()

    mongo_comment, _ = MongoContent.objects.get_or_create(
        mongo_id=str(comment_data["_id"])
    )
    if not mongo_comment.content_object_id:
        comment = Comment.objects.create(
            author=author,
            comment_thread=thread,
            parent=parent,
            course_id=comment_data["course_id"],
            body=comment_data["body"],
            anonymous=comment_data.get("anonymous", False),
            anonymous_to_peers=comment_data.get("anonymous_to_peers", False),
            endorsed=comment_data.get("endorsed", False),
            child_count=comment_data.get("child_count", 0),
            created_at=make_aware(comment_data["created_at"]),
            updated_at=make_aware(comment_data["updated_at"]),
            depth=1 if parent else 0,
        )
        mongo_comment.content_object_id = comment.pk
        mongo_comment.content_type = comment.content_type
        mongo_comment.save()
        sort_key = f"{parent.pk}-{comment.pk}" if parent else f"{comment.pk}"
        comment.sort_key = sort_key
        comment.save()
    else:
        comment = Comment.objects.get(pk=mongo_comment.content_object_id)

    create_or_update_edit_history(comment_data)
    create_or_update_abuse_flaggers(comment_data)
    create_votes(comment, comment_data.get("votes", {}))


def create_votes(content: CommentThread | Comment, votes_data: dict[str, Any]) -> None:
    """Create or update votes for a content."""
    for vote_type in ["up", "down"]:
        for user_id in votes_data.get(vote_type, []):
            user = User.objects.get(pk=int(user_id))
            UserVote.objects.update_or_create(
                user=user,
                content_type=content.content_type,
                content_object_id=content.pk,
                defaults={"vote": 1 if vote_type == "up" else -1},
            )


def create_or_update_edit_history(content: dict[str, Any]) -> None:
    """Create or update edit history for a content."""
    edit_history = content.get("edit_history", [])
    content_type = CommentThread if content["_type"] == "CommentThread" else Comment
    mongo_content = MongoContent.objects.get(mongo_id=str(content["_id"]))
    content_object = content_type.objects.get(pk=mongo_content.content_object_id)
    for edit in edit_history:
        EditHistory.objects.get_or_create(
            content_object_id=content_object.pk,
            content_type=content_object.content_type,
            created_at=edit["created_at"],
            editor=User.objects.get(pk=int(edit["author_id"])),
            defaults={
                "original_body": edit["original_body"],
                "reason_code": edit["reason_code"],
            },
        )


def create_or_update_abuse_flaggers(content: dict[str, Any]) -> None:
    """Create or update abuse flaggers for content."""
    content_type = CommentThread if content["_type"] == "CommentThread" else Comment
    mongo_content = MongoContent.objects.get(mongo_id=str(content["_id"]))
    content_object = content_type.objects.get(pk=mongo_content.content_object_id)
    for user_id in content["abuse_flaggers"]:
        user = User.objects.get(pk=int(user_id))
        AbuseFlagger.objects.update_or_create(
            user=user,
            content_type=content_object.content_type,
            content_object_id=content_object.pk,
            defaults={
                "flagged_at": timezone.now(),
            },
        )
    for user_id in content["historical_abuse_flaggers"]:
        user = User.objects.get(pk=int(user_id))
        HistoricalAbuseFlagger.objects.update_or_create(
            user=user,
            content_type=content_object.content_type,
            content_object_id=content_object.pk,
            defaults={
                "flagged_at": timezone.now(),
            },
        )


def migrate_subscriptions(db: Database[dict[str, Any]], content_id: str) -> None:
    """Migrate subscriptions from mongo to mysql."""
    subscriptions = db.subscriptions.find({"source_id": str(content_id)})
    for sub in subscriptions:
        user = User.objects.get(id=int(sub["subscriber_id"]))
        content_type = (
            CommentThread if sub["source_type"] == "CommentThread" else Comment
        )
        mongo_content = MongoContent.objects.get(mongo_id=str(content_id))
        content = content_type.objects.get(pk=mongo_content.content_object_id)
        if content:
            Subscription.objects.update_or_create(
                subscriber=user,
                source_content_type=content.content_type,
                source_object_id=content.pk,
                defaults={
                    "created_at": sub.get("created_at", timezone.now()),
                    "updated_at": sub.get("updated_at", timezone.now()),
                },
            )


def migrate_read_states(db: Database[dict[str, Any]], course_id: str) -> None:
    """Migrate read states from mongo to mysql."""
    users = db.users.find({"course_stats.course_id": course_id})
    for user_data in users:
        user = User.objects.filter(id=int(user_data["_id"])).first()
        if not user:
            continue

        for read_state in user_data.get("read_states", []):
            if read_state["course_id"] == course_id:
                rs, _ = ReadState.objects.get_or_create(user=user, course_id=course_id)
                for thread_id, timestamp in read_state.get(
                    "last_read_times", {}
                ).items():
                    mongo_content = MongoContent.objects.filter(
                        mongo_id=thread_id
                    ).first()
                    thread = mongo_content and mongo_content.content

                    # For older courses using cs_comment_service, the thread may be None
                    # because cs_comment_service retains read_states for deleted threads
                    # in the users collection in MongoDB. As a result, MongoContent won't
                    # have a thread with deleted thread_id from read_states.
                    if not thread:
                        continue
                    existing_read_time = LastReadTime.objects.filter(
                        read_state=rs, comment_thread=thread
                    ).first()
                    if not existing_read_time:
                        LastReadTime.objects.create(
                            read_state=rs,
                            comment_thread=thread,
                            timestamp=make_aware(timestamp),
                        )
                    else:
                        existing_read_time.timestamp = make_aware(timestamp)
                        existing_read_time.save()


def delete_course_data(
    db: Database[dict[str, Any]],
    course_id: str,
    dry_run: bool,
    stdout: OutputWrapper,
) -> None:
    """Delete content (threads and comments)."""
    contents = db.contents.find({"course_id": course_id})
    for content in contents:
        subscriptions = (
            db.subscriptions.delete_many({"source_id": str(content["_id"])})
            if not dry_run
            else None
        )
    stdout.write(
        f"Subscription documents to be deleted: {subscriptions.deleted_count if subscriptions else 'N/A (dry run)'}"
    )

    content_result = (
        db.contents.delete_many({"course_id": course_id}) if not dry_run else None
    )
    stdout.write(
        f"Content documents to be deleted: {content_result.deleted_count if content_result else 'N/A (dry run)'}"
    )
    user_ids = db.users.distinct("_id", {"course_stats.course_id": course_id})

    for user_id in user_ids:
        if not dry_run:
            db.users.update_one(
                {"_id": user_id},
                {
                    "$pull": {
                        "course_stats": {"course_id": course_id},
                        "read_states": {"course_id": course_id},
                    }
                },
            )
            stdout.write(f"Updated user data for user ID: {user_id}")

    if not dry_run:
        db.users.update_many(
            {},
            {
                "$pull": {
                    "course_stats": {"course_id": course_id},
                    "read_states": {"course_id": course_id},
                }
            },
        )
        stdout.write("Cleaned up users collection")


def log_deletion(
    collection_name: str,
    result: Collection[dict[str, Any]],
    stdout: OutputWrapper,
) -> None:
    """Log the deletion of a collection."""
    stdout.write(f"Deleted {result.deleted_count} documents from {collection_name}")


# pylint: disable=import-error,import-outside-toplevel
def enable_mysql_backend_for_course(course_id: str) -> None:
    """Enable MySQL backend waffle flag for a course."""
    from opaque_keys.edx.keys import CourseKey

    from openedx.core.djangoapps.waffle_utils.models import (  # type: ignore[import-not-found]
        WaffleFlagCourseOverrideModel,
    )

    from forum.toggles import ENABLE_MYSQL_BACKEND

    course_key = CourseKey.from_string(course_id)
    WaffleFlagCourseOverrideModel.objects.create(
        course_id=course_key, waffle_flag=ENABLE_MYSQL_BACKEND.name, enabled=True
    )
