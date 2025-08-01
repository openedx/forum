"""MySQL models for forum v2."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, Optional, Union

from django.contrib.auth.models import User  # pylint: disable=E5142
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Count, Exists, F, Max, OuterRef, Q, QuerySet, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ObjectDoesNotExist

from forum.constants import RETIRED_BODY, RETIRED_TITLE
from forum.utils import validate_upvote_or_downvote


class ForumUser(models.Model):
    """Forum user model."""

    class Meta:
        app_label = "forum"

    user: models.OneToOneField[User, User] = models.OneToOneField(
        User, related_name="forum", on_delete=models.CASCADE
    )
    default_sort_key: models.CharField[str, str] = models.CharField(
        max_length=25, default="date"
    )

    @classmethod
    def get_by_user_id(cls, user_id: str) -> dict[str, Any] | None:
        """
        Get forum user by user_id.

        Args:
            user_id: The ID of the user to retrieve.

        Returns:
            Dictionary representation of the forum user or None if not found.
        """
        try:
            forum_user = cls.objects.get(user__pk=int(user_id))
            return forum_user.to_dict()
        except (cls.DoesNotExist, ValueError):
            return None

    def to_dict(self, course_id: Optional[str] = None) -> dict[str, Any]:
        """Return a dictionary representation of the model."""
        course_stats = CourseStat.objects.filter(user=self.user)
        read_states = ReadState.objects.filter(user=self.user)

        if course_id:
            course_stat = course_stats.filter(course_id=course_id).first()
        else:
            course_stat = None

        return {
            "_id": self.user.pk,
            "default_sort_key": self.default_sort_key,
            "external_id": self.user.pk,
            "username": self.user.username,
            "email": self.user.email,
            "course_stats": (
                course_stat.to_dict()
                if course_stat
                else [stat.to_dict() for stat in course_stats]
            ),
            "read_states": [state.to_dict() for state in read_states],
        }

    @classmethod
    def get_by_user_id(cls, user_id: str) -> Optional["ForumUser"]:
        """Return ForumUser instance from user_id."""
        try:
            return cls.objects.get(user__pk=int(user_id))
        except ObjectDoesNotExist:
            return None

    @classmethod
    def get_by_username(cls, username: str) -> Optional["ForumUser"]:
        """Return ForumUser instance from username."""
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return None
        try:
            return cls.objects.get(user=user)
        except cls.DoesNotExist:
            return None

    @classmethod
    def find_or_create_user(
        cls,
        user_id: str,
        username: Optional[str] = None,
        default_sort_key: Optional[str] = "date",
    ) -> "ForumUser":
        """Find or create a ForumUser and underlying User."""
        username = username or user_id
        try:
            user = User.objects.get(pk=int(user_id))
        except User.DoesNotExist:
            user = None

        if user is None:
            if User.objects.filter(username=username).exists():
                raise ValueError(f"User with username {username} already exists")
            user = User.objects.create(pk=int(user_id), username=username)

        forum_user, _ = cls.objects.get_or_create(
            user=user, defaults={"default_sort_key": default_sort_key}
        )
        return forum_user

    @classmethod
    def update_user(cls, user_id: str, data: dict[str, Any]) -> int:
        """Update User and ForumUser fields, and handle read_states."""
        try:
            user = User.objects.get(id=user_id)
            forum_user = cls.objects.get(user=user)
        except ObjectDoesNotExist:
            return 0

        if "username" in data:
            user.username = data["username"]
        if "email" in data:
            user.email = data["email"]
        if "default_sort_key" in data:
            forum_user.default_sort_key = data["default_sort_key"]
        if "read_states" in data:
            # Remove all existing ReadState objects for this user
            ReadState.objects.filter(user=user).delete()
            # Insert new ReadState objects from data['read_states']
            for state in data["read_states"]:
                last_read_times = state.get("last_read_times", {})
                for thread_id, dt in last_read_times.items():
                    thread = CommentThread.objects.get(pk=thread_id)
                    read_state, _ = ReadState.objects.get_or_create(
                        user=user, course_id=thread.course_id
                    )
                    LastReadTime.objects.update_or_create(
                        read_state=read_state,
                        comment_thread=thread,
                        defaults={"timestamp": dt},
                    )
        user.save()
        forum_user.save()
        return 1

    @classmethod
    def user_to_hash(
        cls,
        user_id: str,
        params: Optional[dict[str, Any]] = None,
        filter_standalone_threads: Optional[Callable[[list[str]], list[str]]] = None,
        find_subscribed_threads: Optional[Callable[[str], list[str]]] = None,
        get_user_voted_ids: Optional[Callable[[str, str], list[str]]] = None,
    ) -> dict[str, Any]:
        """Converts user data to a hash."""
        user = User.objects.get(pk=user_id)
        forum_user = cls.objects.get(user__pk=user_id)
        if params is None:
            params = {}

        user_data = forum_user.to_dict()
        hash_data = {}
        hash_data["username"] = user_data["username"]
        hash_data["external_id"] = user_data["external_id"]
        hash_data["id"] = user_data["external_id"]

        if params.get("complete"):
            if find_subscribed_threads and get_user_voted_ids:
                subscribed_thread_ids = find_subscribed_threads(user_id)
                upvoted_ids = get_user_voted_ids(user_id, "up")
                downvoted_ids = get_user_voted_ids(user_id, "down")
            else:
                subscribed_thread_ids = []
                upvoted_ids = []
                downvoted_ids = []
            hash_data.update(
                {
                    "subscribed_thread_ids": subscribed_thread_ids,
                    "subscribed_commentable_ids": [],
                    "subscribed_user_ids": [],
                    "follower_ids": [],
                    "id": user_id,
                    "upvoted_ids": upvoted_ids,
                    "downvoted_ids": downvoted_ids,
                    "default_sort_key": user_data["default_sort_key"],
                }
            )

        if params.get("course_id"):
            threads = CommentThread.objects.filter(
                author=user,
                course_id=params["course_id"],
                anonymous=False,
                anonymous_to_peers=False,
            )
            comments = Comment.objects.filter(
                author=user,
                course_id=params["course_id"],
                anonymous=False,
                anonymous_to_peers=False,
            )
            comment_ids = list(comments.values_list("pk", flat=True))
            if params.get("group_ids") and filter_standalone_threads:
                group_threads = threads.filter(
                    group_id__in=params["group_ids"] + [None]
                )
                group_thread_ids = [str(thread.pk) for thread in group_threads]
                threads_count = len(group_thread_ids)
                comment_thread_ids = filter_standalone_threads(comment_ids)

                group_comment_threads = CommentThread.objects.filter(
                    id__in=comment_thread_ids, group_id__in=params["group_ids"] + [None]
                )
                group_comment_thread_ids = [
                    str(thread.pk) for thread in group_comment_threads
                ]
                comments_count = sum(
                    1
                    for comment_thread_id in comment_thread_ids
                    if comment_thread_id in group_comment_thread_ids
                )
            else:
                thread_ids = [str(thread.pk) for thread in threads]
                threads_count = len(thread_ids)
                if filter_standalone_threads:
                    comment_thread_ids = filter_standalone_threads(comment_ids)
                    comments_count = len(comment_thread_ids)
                else:
                    comments_count = 0

            hash_data.update(
                {
                    "threads_count": threads_count,
                    "comments_count": comments_count,
                }
            )

        return hash_data

    @classmethod
    def replace_username_in_all_content(cls, user_id: str, username: str) -> None:
        """Replace the username of a Django user."""
        try:
            user = User.objects.get(pk=user_id)
            user.username = username
            user.save()
        except User.DoesNotExist as exc:
            raise ValueError("User does not exist") from exc

    @classmethod
    def unsubscribe_all(cls, user_id: str) -> None:
        """Unsubscribe user from all content."""
        Subscription.unsubscribe_all(user_id)

    @classmethod
    def retire_all_content(cls, user_id: str) -> None:
        """Retire all content from user."""

        comments = Comment.objects.filter(author__pk=user_id)
        for comment in comments:
            comment.body = RETIRED_BODY
            comment.save()
        comment_threads = CommentThread.objects.filter(author__pk=user_id)
        for comment_thread in comment_threads:
            comment_thread.body = RETIRED_BODY
            comment_thread.title = RETIRED_TITLE
            comment_thread.save()

    @classmethod
    def get_users(cls, **kwargs: Any) -> list[dict[str, Any]]:
        """Retrieves a list of users in the database based on provided filters."""
        forum_users = cls.objects.filter(**kwargs)
        sort_key = kwargs.get("sort_key")
        if sort_key:
            forum_users = forum_users.order_by(sort_key)
        return [user.to_dict() for user in forum_users]

    @classmethod
    def get_user_sort_criterion(cls, sort_by: str) -> dict[str, Any]:
        """Get sort criterion based on sort_by parameter."""
        if sort_by == "flagged":
            return {
                "course_stats__active_flags": -1,
                "course_stats__inactive_flags": -1,
                "username": -1,
            }
        elif sort_by == "recency":
            return {"course_stats__last_activity_at": -1, "username": -1}
        else:
            return {
                "course_stats__threads": -1,
                "course_stats__responses": -1,
                "course_stats__replies": -1,
                "username": -1,
            }

    @classmethod
    def get_paginated_user_stats(
        cls, course_id: str, page: int, per_page: int, sort_criterion: dict[str, Any]
    ) -> dict[str, Any]:
        """Get paginated user stats."""
        users = User.objects.filter(
            Q(course_stats__course_id=course_id)
            & Q(course_stats__course_id__isnull=False)
        ).order_by(
            *[f"-{key}" for key, value in sort_criterion.items() if value == -1],
            *[key for key, value in sort_criterion.items() if value == 1],
        )
        paginator = Paginator(users, per_page)
        paginated_users = paginator.page(page)
        forum_users = [
            cls.objects.get(user_id=user_id) for user_id in paginated_users.object_list
        ]
        return {
            "pagination": [{"total_count": paginator.count}],
            "data": [user.to_dict(course_id=course_id) for user in forum_users],
        }

    @classmethod
    def update_all_users_in_course(cls, course_id: str) -> list[str]:
        """Update all user stats in a course."""
        course_comments = Comment.objects.filter(
            anonymous=False,
            anonymous_to_peers=False,
            course_id=course_id,
        )
        course_threads = CommentThread.objects.filter(
            anonymous=False,
            anonymous_to_peers=False,
            course_id=course_id,
        )
        comment_authors = set(course_comments.values_list("author__id", flat=True))
        thread_authors = set(course_threads.values_list("author__id", flat=True))
        author_ids = list(comment_authors | thread_authors)
        for author_id in author_ids:
            cls.build_course_stats(author_id, course_id)
        return author_ids

    @classmethod
    def build_course_stats(cls, author_id: str, course_id: str) -> None:
        """Build course stats for a user in a course."""
        author = User.objects.get(pk=author_id)
        threads = CommentThread.objects.filter(
            author=author,
            course_id=course_id,
            anonymous_to_peers=False,
            anonymous=False,
        )
        comments = Comment.objects.filter(
            author=author,
            course_id=course_id,
            anonymous_to_peers=False,
            anonymous=False,
        )
        responses = comments.filter(parent__isnull=True)
        replies = comments.filter(parent__isnull=False)
        comment_ids = [comment.pk for comment in comments]
        threads_ids = [thread.pk for thread in threads]
        active_flags_comments = (
            AbuseFlagger.objects.filter(
                content_object_id__in=comment_ids, content_type=Comment().content_type
            )
            .values("content_object_id")
            .annotate(count=Count("content_object_id"))
            .count()
        )
        active_flags_threads = (
            AbuseFlagger.objects.filter(
                content_object_id__in=threads_ids,
                content_type=CommentThread().content_type,
            )
            .values("content_object_id")
            .annotate(count=Count("content_object_id"))
            .count()
        )
        active_flags = active_flags_comments + active_flags_threads
        inactive_flags_comments = (
            HistoricalAbuseFlagger.objects.filter(
                content_object_id__in=comment_ids, content_type=Comment().content_type
            )
            .values("content_object_id")
            .annotate(count=Count("content_object_id"))
            .count()
        )
        inactive_flags_threads = (
            HistoricalAbuseFlagger.objects.filter(
                content_object_id__in=threads_ids,
                content_type=CommentThread().content_type,
            )
            .values("content_object_id")
            .annotate(count=Count("content_object_id"))
            .count()
        )
        inactive_flags = inactive_flags_comments + inactive_flags_threads
        threads_updated_at = threads.aggregate(Max("updated_at"))["updated_at__max"]
        comments_updated_at = comments.aggregate(Max("updated_at"))["updated_at__max"]
        updated_at = max(
            threads_updated_at or timezone.now() - timedelta(days=365 * 100),
            comments_updated_at or timezone.now() - timedelta(days=365 * 100),
        )
        stats, _ = CourseStat.objects.get_or_create(user=author, course_id=course_id)
        stats.threads = threads.count()
        stats.responses = responses.count()
        stats.replies = replies.count()
        stats.active_flags = active_flags
        stats.inactive_flags = inactive_flags
        stats.last_activity_at = updated_at
        stats.save()
        # If you need to update user stats for course, call the backend method here if needed


class CourseStat(models.Model):
    """Course stats model."""

    course_id: models.CharField[str, str] = models.CharField(max_length=255)
    active_flags: models.IntegerField[int, int] = models.IntegerField(default=0)
    inactive_flags: models.IntegerField[int, int] = models.IntegerField(default=0)
    threads: models.IntegerField[int, int] = models.IntegerField(default=0)
    responses: models.IntegerField[int, int] = models.IntegerField(default=0)
    replies: models.IntegerField[int, int] = models.IntegerField(default=0)
    last_activity_at: models.DateTimeField[Optional[datetime], datetime] = (
        models.DateTimeField(default=None, null=True, blank=True)
    )
    user: models.ForeignKey[User, User] = models.ForeignKey(
        User, related_name="course_stats", on_delete=models.CASCADE
    )

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the model."""
        return {
            "_id": str(self.pk),
            "active_flags": self.active_flags,
            "inactive_flags": self.inactive_flags,
            "threads": self.threads,
            "responses": self.responses,
            "replies": self.replies,
            "course_id": self.course_id,
            "last_activity_at": self.last_activity_at,
        }

    @classmethod
    def update_stats_for_user_and_course(
        cls, user_id: str, course_id: str, **kwargs: Any
    ) -> None:
        """
        Update stats for a specific user and course.

        Args:
            user_id: The ID of the user.
            course_id: The ID of the course.
            **kwargs: Key-value pairs of stats to update (e.g., threads=1, responses=-1).
        """
        user = User.objects.get(pk=user_id)
        course_stat, created = cls.objects.get_or_create(user=user, course_id=course_id)

        if created:
            course_stat.active_flags = 0
            course_stat.inactive_flags = 0
            course_stat.threads = 0
            course_stat.responses = 0
            course_stat.replies = 0

        for key, value in kwargs.items():
            if hasattr(course_stat, key):
                setattr(course_stat, key, F(key) + value)

        course_stat.save()

    class Meta:
        app_label = "forum"
        unique_together = ("user", "course_id")


class Content(models.Model):
    """Content model."""

    index_name = ""

    author: models.ForeignKey[User, User] = models.ForeignKey(
        User, on_delete=models.CASCADE
    )
    course_id: models.CharField[str, str] = models.CharField(max_length=255)
    body: models.TextField[str, str] = models.TextField()
    visible: models.BooleanField[bool, bool] = models.BooleanField(default=True)
    endorsed: models.BooleanField[bool, bool] = models.BooleanField(default=False)
    anonymous: models.BooleanField[bool, bool] = models.BooleanField(default=False)
    anonymous_to_peers: models.BooleanField[bool, bool] = models.BooleanField(
        default=False
    )
    group_id: models.PositiveIntegerField[int, int] = models.PositiveIntegerField(
        null=True
    )
    created_at: models.DateTimeField[datetime, datetime] = models.DateTimeField(
        auto_now_add=True
    )
    updated_at: models.DateTimeField[datetime, datetime] = models.DateTimeField(
        auto_now=True
    )
    uservote = GenericRelation(
        "UserVote",
        object_id_field="content_object_id",
        content_type_field="content_type",
    )

    @property
    def type(self) -> str:
        """Return the type of content as str."""
        return self._meta.object_name or ""

    @property
    def content_type(self) -> ContentType:
        """Return the type of content."""
        return ContentType.objects.get_for_model(self)

    @property
    def abuse_flaggers(self) -> list[int]:
        """Return a list of users who have flagged the content for abuse."""
        return list(
            AbuseFlagger.objects.filter(
                content_object_id=self.pk, content_type=self.content_type
            ).values_list("user_id", flat=True)
        )

    @property
    def historical_abuse_flaggers(self) -> list[int]:
        """Return a list of users who have historically flagged the content for abuse."""
        return list(
            HistoricalAbuseFlagger.objects.filter(
                content_object_id=self.pk, content_type=self.content_type
            ).values_list("user_id", flat=True)
        )

    @property
    def edit_history(self) -> QuerySet[EditHistory]:
        """Return a list of edit history for the content."""
        return EditHistory.objects.filter(
            content_object_id=self.pk, content_type=self.content_type
        )

    @property
    def votes(self) -> models.QuerySet[UserVote]:
        """Get all user vote query for content."""
        return UserVote.objects.filter(
            content_object_id=self.pk,
            content_type=self.content_type,
        )

    @property
    def get_votes(self) -> dict[str, Any]:
        """Get all user votes for content."""
        votes: dict[str, Any] = {
            "up": [],
            "down": [],
            "up_count": 0,
            "down_count": 0,
            "count": 0,
            "point": 0,
        }
        for vote in self.votes:
            if vote.vote == 1:
                votes["up"].append(vote.user.pk)
                votes["up_count"] += 1
            elif vote.vote == -1:
                votes["down"].append(vote.user.pk)
                votes["down_count"] += 1
            votes["point"] = votes["up_count"] - votes["down_count"]
            votes["count"] = votes["count"]
        return votes

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the content."""
        raise NotImplementedError

    def doc_to_hash(self) -> dict[str, Any]:
        """Return a dictionary representation of the content."""
        raise NotImplementedError

    @staticmethod
    def get_entity_from_type(
        entity_id: str, entity_type: str
    ) -> Union["Comment", "CommentThread", None]:
        """
        Get entity from type.

        Args:
            entity_id (str): The ID of the entity.
            entity_type (str): The type of entity ('Comment' or 'CommentThread').

        Returns:
            Union[Comment, CommentThread, None]: The entity instance or None if not found.
        """
        try:
            if entity_type == "Comment":
                return Comment.objects.get(pk=entity_id)
            else:
                return CommentThread.objects.get(pk=entity_id)
        except ObjectDoesNotExist:
            return None

    class Meta:
        app_label = "forum"
        abstract = True


class CommentThread(Content):
    """Comment thread model."""

    index_name = "comment_threads"

    THREAD_TYPE_CHOICES = [
        ("question", "Question"),
        ("discussion", "Discussion"),
    ]

    CONTEXT_CHOICES = [
        ("course", "Course"),
        ("standalone", "Standalone"),
    ]

    title: models.CharField[str, str] = models.CharField(max_length=1024)
    thread_type: models.CharField[str, str] = models.CharField(
        max_length=50, choices=THREAD_TYPE_CHOICES, default="discussion"
    )
    context: models.CharField[str, str] = models.CharField(
        max_length=50, choices=CONTEXT_CHOICES, default="course"
    )
    closed: models.BooleanField[bool, bool] = models.BooleanField(default=False)
    pinned: models.BooleanField[Optional[bool], bool] = models.BooleanField(
        null=True, blank=True
    )
    last_activity_at: models.DateTimeField[Optional[datetime], datetime] = (
        models.DateTimeField(null=True, blank=True)
    )
    close_reason_code: models.CharField[Optional[str], str] = models.CharField(
        max_length=255, null=True, blank=True
    )
    closed_by: models.ForeignKey[User, User] = models.ForeignKey(
        User,
        related_name="threads_closed",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    commentable_id: models.CharField[str, str] = models.CharField(
        max_length=255,
        default=None,
        blank=True,
        null=True,
    )

    @property
    def comment_count(self) -> int:
        """Return the number of comments in the thread."""
        return Comment.objects.filter(comment_thread=self).count()

    @classmethod
    def get(cls, thread_id: str) -> CommentThread:
        """Get a comment thread model instance."""
        return cls.objects.get(pk=int(thread_id))

    @classmethod
    def delete_by_id(cls, thread_id: str) -> int:
        """
        Delete a thread by its ID.

        Args:
            thread_id: The ID of the thread to delete.

        Returns:
            1 if the thread was successfully deleted, 0 if the thread doesn't exist.
        """
        try:
            thread = cls.objects.get(pk=thread_id)
            thread.delete()
            return 1
        except cls.DoesNotExist:
            return 0

    @classmethod
    def update_by_id(cls, thread_id: str, **kwargs: Any) -> int:
        """
        Update a thread by its ID with the provided data.

        Args:
            thread_id: The ID of the thread to update.
            **kwargs: The fields to update and their new values.

        Returns:
            1 if the thread was successfully updated, 0 if the thread doesn't exist.
        """
        thread = cls.objects.get(id=thread_id)

        if "thread_type" in kwargs:
            thread.thread_type = kwargs["thread_type"]
        if "title" in kwargs:
            thread.title = kwargs["title"]
        if "body" in kwargs:
            thread.body = kwargs["body"]
        if "course_id" in kwargs:
            thread.course_id = kwargs["course_id"]
        if "anonymous" in kwargs:
            thread.anonymous = kwargs["anonymous"]
        if "anonymous_to_peers" in kwargs:
            thread.anonymous_to_peers = kwargs["anonymous_to_peers"]
        if "commentable_id" in kwargs:
            thread.commentable_id = kwargs["commentable_id"]
        if "author_id" in kwargs and kwargs["author_id"]:
            thread.author = User.objects.get(pk=int(kwargs["author_id"]))
        if "closed_by_id" in kwargs and kwargs["closed_by_id"]:
            thread.closed_by = User.objects.get(pk=int(kwargs["closed_by_id"]))
        if "pinned" in kwargs:
            thread.pinned = kwargs["pinned"]
        if "close_reason_code" in kwargs:
            thread.close_reason_code = kwargs["close_reason_code"]
        if "closed" in kwargs:
            thread.closed = kwargs["closed"]
            if not kwargs["closed"]:
                thread.closed_by = None  # type: ignore
                thread.close_reason_code = None
        if "endorsed" in kwargs:
            thread.endorsed = kwargs["endorsed"]
        if "group_id" in kwargs:
            thread.group_id = kwargs["group_id"]

        if "abuse_flaggers" in kwargs:
            existing_abuse_flaggers = AbuseFlagger.objects.filter(
                content_object_id=thread.pk,
                content_type=thread.content_type,
            ).values_list("user_id", flat=True)

            new_abuse_flaggers = [
                int(user_id)
                for user_id in kwargs["abuse_flaggers"]
                if int(user_id) not in existing_abuse_flaggers
            ]

            for user_id in new_abuse_flaggers:
                AbuseFlagger.objects.create(
                    user=User.objects.get(pk=user_id),
                    content_object_id=thread.pk,
                    content_type=thread.content_type,
                )

        if "historical_abuse_flaggers" in kwargs:
            existing_historical_abuse_flaggers = HistoricalAbuseFlagger.objects.filter(
                content_object_id=thread.pk,
                content_type=thread.content_type,
            ).values_list("user__pk", flat=True)

            new_historical_abuse_flaggers = [
                int(user_id)
                for user_id in kwargs["historical_abuse_flaggers"]
                if int(user_id) not in existing_historical_abuse_flaggers
            ]

            HistoricalAbuseFlagger.objects.bulk_create(
                [
                    HistoricalAbuseFlagger(
                        user=User.objects.get(pk=user_id),
                        content_object_id=thread.pk,
                        content_type=thread.content_type,
                    )
                    for user_id in new_historical_abuse_flaggers
                ]
            )

        if "editing_user_id" in kwargs and kwargs["editing_user_id"]:
            EditHistory.objects.create(
                content_object_id=thread.pk,
                content_type=thread.content_type,
                reason_code=kwargs.get("edit_reason_code"),
                original_body=kwargs.get("original_body"),
                editor=User.objects.get(pk=kwargs["editing_user_id"]),
                created_at=timezone.now(),
            )

        if "votes" in kwargs:
            up_votes = kwargs["votes"].get("up", [])
            down_votes = kwargs["votes"].get("down", [])
            for user_id in up_votes:
                UserVote.objects.update_or_create(
                    user=User.objects.get(id=int(user_id)),
                    content_type=thread.content_type,
                    content_object_id=thread.pk,
                    vote=1,
                )
            for user_id in down_votes:
                UserVote.objects.update_or_create(
                    user=User.objects.get(id=int(user_id)),
                    content_type=thread.content_type,
                    content_object_id=thread.pk,
                    vote=-1,
                )

        thread.updated_at = timezone.now()
        thread.save()
        return 1

    @classmethod
    def get_by_id(cls, thread_id: str) -> dict[str, Any] | None:
        """
        Get a thread by its ID.

        Args:
            thread_id: The ID of the thread to retrieve.

        Returns:
            Dictionary representation of the thread or None if not found.
        """
        try:
            thread = cls.objects.get(pk=thread_id)
            return thread.to_dict()
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_filtered_by_query(cls, query: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Get a list of threads that match the given filter criteria.

        Args:
            query: Dictionary containing filter criteria.

        Returns:
            List of thread dictionaries that match the filter.
        """
        threads = cls.objects.filter(**query)
        return [thread.to_dict() for thread in threads]

    @classmethod
    def build_complex_query(
        cls,
        thread_ids: list[str],
        course_id: str,
        context: str = "course",
        group_ids: Optional[list[int]] = None,
        author_id: Optional[str] = None,
        thread_type: Optional[str] = None,
        filter_flagged: bool = False,
        filter_unanswered: bool = False,
        filter_unresponded: bool = False,
        user: Optional[Any] = None,
    ) -> Any:
        """
        Build a complex query for threads with various filters.

        Args:
            thread_ids: List of thread IDs to filter by.
            course_id: The course ID to filter by.
            context: The context to filter by (default: "course").
            group_ids: List of group IDs for group-based filtering.
            author_id: The ID of the author to filter threads by.
            thread_type: The type of thread to filter by.
            filter_flagged: Whether to filter threads flagged for abuse.
            filter_unanswered: Whether to filter unanswered questions.
            filter_unresponded: Whether to filter threads with no responses.
            user: The user making the request for anonymous filtering.

        Returns:
            Django QuerySet with applied filters.
        """
        # Convert thread IDs to integers
        mysql_thread_ids = []
        for tid in thread_ids:
            try:
                thread_id = int(tid)
                mysql_thread_ids.append(thread_id)
            except ValueError:
                continue

        # Base query
        base_query = cls.objects.filter(pk__in=mysql_thread_ids, context=context)

        # Group filtering
        if group_ids:
            base_query = base_query.filter(
                Q(group_id__in=group_ids) | Q(group_id__isnull=True)
            )

        # Author filtering
        if author_id:
            base_query = base_query.filter(author__pk=author_id)
            if user and int(author_id) != user.pk:
                base_query = base_query.filter(
                    anonymous=False, anonymous_to_peers=False
                )

        # Thread type filtering
        if thread_type:
            base_query = base_query.filter(thread_type=thread_type)

        # Flagged content filtering
        if filter_flagged:
            comment_abuse_flaggers = AbuseFlagger.objects.filter(
                content_object_id=OuterRef("pk"),
                content_type=ContentType.objects.get_for_model(Comment),
            )

            flagged_comments = (
                Comment.objects.filter(course_id=course_id)
                .annotate(has_abuse_flaggers=Exists(comment_abuse_flaggers))
                .filter(has_abuse_flaggers=True)
                .values_list("comment_thread_id", flat=True)
            )

            thread_abuse_flaggers = AbuseFlagger.objects.filter(
                content_object_id=OuterRef("pk"),
                content_type=ContentType.objects.get_for_model(cls),
            )

            flagged_threads = (
                cls.objects.filter(course_id=course_id)
                .annotate(has_abuse_flaggers=Exists(thread_abuse_flaggers))
                .filter(has_abuse_flaggers=True)
                .values_list("id", flat=True)
            )

            base_query = base_query.filter(
                pk__in=list(
                    set(mysql_thread_ids) & set(flagged_comments) | set(flagged_threads)
                )
            )

        # Unanswered questions filtering
        if filter_unanswered:
            endorsed_threads = Comment.objects.filter(
                course_id=course_id,
                parent__isnull=True,
                endorsed=True,
            ).values_list("comment_thread_id", flat=True)
            base_query = base_query.filter(
                thread_type="question",
            ).exclude(pk__in=endorsed_threads)

        # Unresponded threads filtering
        if filter_unresponded:
            base_query = base_query.annotate(num_comments=Count("comment")).filter(
                num_comments=0
            )

        # Add annotations for votes and comments count
        base_query = base_query.annotate(
            votes_point=Sum("uservote__vote", distinct=True),
            comments_count=Count("comment", distinct=True),
        )

        return base_query

    @classmethod
    def get_course_id_by_id(cls, thread_id: str) -> str | None:
        """
        Get the course_id for a thread by its ID.

        Args:
            thread_id: The ID of the thread to look up.

        Returns:
            The course_id of the thread, or None if the thread doesn't exist.
        """
        thread = cls.objects.filter(id=thread_id).first()
        return thread.course_id if thread else None

    @classmethod
    def create_from_data(cls, data: dict[str, Any]) -> str:
        """
        Create a new thread from the provided data.

        Args:
            data: Dictionary containing thread data.

        Returns:
            The ID of the created thread as a string.
        """
        optional_args = {}
        if group_id := data.get("group_id"):
            optional_args["group_id"] = group_id

        new_thread = cls.objects.create(
            title=data["title"],
            body=data["body"],
            course_id=data["course_id"],
            anonymous=data.get("anonymous", False),
            anonymous_to_peers=data.get("anonymous_to_peers", False),
            author=User.objects.get(pk=int(data["author_id"])),
            commentable_id=data.get("commentable_id", "course"),
            thread_type=data.get("thread_type", "discussion"),
            context=data.get("context", "course"),
            last_activity_at=timezone.now(),
            **optional_args,
        )
        return str(new_thread.pk)

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the model."""
        edit_history = []
        for edit in self.edit_history.all():
            edit_history.append(
                {
                    "_id": str(edit.pk),
                    "original_body": edit.original_body,
                    "reason_code": edit.reason_code,
                    "editor_username": edit.editor.username,
                    "author_id": edit.editor.pk,
                    "created_at": edit.created_at,
                }
            )

        return {
            "_id": str(self.pk),
            "votes": self.get_votes,
            "visible": self.visible,
            "abuse_flaggers": [str(flagger) for flagger in self.abuse_flaggers],
            "historical_abuse_flaggers": [
                str(flagger) for flagger in self.historical_abuse_flaggers
            ],
            "thread_type": self.thread_type,
            "_type": "CommentThread",
            "commentable_id": self.commentable_id,
            "context": self.context,
            "comment_count": self.comment_count,
            "at_position_list": [],
            "pinned": self.pinned if self.pinned else False,
            "title": self.title,
            "body": self.body,
            "course_id": self.course_id,
            "anonymous": self.anonymous,
            "anonymous_to_peers": self.anonymous_to_peers,
            "closed": self.closed,
            "closed_by_id": str(self.closed_by.pk) if self.closed_by else None,
            "close_reason_code": self.close_reason_code,
            "author_id": str(self.author.pk),
            "author_username": self.author.username,
            "updated_at": self.updated_at,
            "created_at": self.created_at,
            "last_activity_at": self.last_activity_at,
            "edit_history": edit_history,
            "group_id": self.group_id,
        }

    def doc_to_hash(self) -> dict[str, Any]:
        """
        Converts the CommentThread model instance to a dictionary representation for Elasticsearch.
        """
        return {
            "id": str(self.pk),
            "title": self.title,
            "body": self.body,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_activity_at": (
                self.last_activity_at.isoformat() if self.last_activity_at else None
            ),
            "comment_count": self.comment_count,
            "votes_point": self.get_votes.get("point"),
            "context": self.context,
            "course_id": self.course_id,
            "commentable_id": self.commentable_id,
            "author_id": str(self.author.pk),
            "group_id": self.group_id,
            "thread_id": str(self.pk),
        }

    class Meta:
        app_label = "forum"
        indexes = [
            models.Index(fields=["context"]),
            models.Index(fields=["author"]),
            models.Index(fields=["author", "course_id"]),
            models.Index(fields=["course_id", "anonymous", "anonymous_to_peers"]),
            models.Index(
                fields=["author", "course_id", "anonymous", "anonymous_to_peers"]
            ),
        ]


class Comment(Content):
    """Comment model class"""

    index_name = "comments"

    endorsement: models.JSONField[dict[str, Any], dict[str, Any]] = models.JSONField(
        default=dict
    )
    sort_key: models.CharField[Optional[str], str] = models.CharField(
        max_length=255, null=True, blank=True
    )
    child_count: models.PositiveIntegerField[int, int] = models.PositiveIntegerField(
        default=0
    )
    retired_username: models.CharField[Optional[str], str] = models.CharField(
        max_length=255, null=True, blank=True
    )
    comment_thread: models.ForeignKey[CommentThread, CommentThread] = models.ForeignKey(
        CommentThread, on_delete=models.CASCADE
    )
    parent: models.ForeignKey[Comment, Comment] = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True
    )
    depth: models.PositiveIntegerField[int, int] = models.PositiveIntegerField(
        default=0
    )

    def get_sort_key(self) -> str:
        """Get the sort key for the comment"""
        if self.parent:
            return f"{self.parent.pk}-{self.pk}"
        return str(self.pk)

    @staticmethod
    def get_list(**kwargs: Any) -> list[dict[str, Any]]:
        """
        Retrieves a list of all comments in the database based on provided filters.

        Args:
            kwargs: The filter arguments.

        Returns:
            A list of comments.
        """
        sort = kwargs.pop("sort", None)
        resp_skip = kwargs.pop("resp_skip", 0)
        resp_limit = kwargs.pop("resp_limit", None)
        comments = Comment.objects.filter(**kwargs)
        result = []
        if sort:
            if sort == 1:
                result = sorted(
                    comments, key=lambda x: (x.sort_key is None, x.sort_key or "")
                )
            elif sort == -1:
                result = sorted(
                    comments,
                    key=lambda x: (x.sort_key is None, x.sort_key or ""),
                    reverse=True,
                )

        paginated_comments = result or list(comments)

        # Apply pagination if resp_limit is provided
        if resp_limit is not None:
            resp_end = resp_skip + resp_limit
            paginated_comments = result[resp_skip:resp_end]
        elif resp_skip:  # If resp_limit is None but resp_skip is provided
            paginated_comments = result[resp_skip:]

        return [content.to_dict() for content in paginated_comments]

    @staticmethod
    def get_list_total_count(**kwargs: Any) -> int:
        """
        Retrieves the total count of comments in the database based on provided filters.

        Args:
            kwargs: The filter arguments to apply when counting comments.

        Returns:
            The total number of comments matching the provided filters.
        """
        kwargs.pop("sort", None)
        kwargs.pop("resp_skip", 0)
        kwargs.pop("resp_limit", None)
        return Comment.objects.filter(**kwargs).count()

    @classmethod
    def delete_by_thread_id(cls, thread_id: str) -> None:
        """
        Delete all parent comments (comments without a parent) that belong to a specific thread.

        Args:
            thread_id: The ID of the thread whose comments should be deleted.
        """
        cls.objects.filter(comment_thread__pk=thread_id, parent=None).delete()

    def get_parent_ids(self) -> list[str]:
        """Return a list of all parent IDs of a comment."""
        parent_ids = []
        current_comment = self
        while current_comment.parent:
            parent_ids.append(str(current_comment.parent.pk))
            current_comment = current_comment.parent
        return parent_ids

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the model."""
        edit_history = []
        for edit in self.edit_history.all():
            edit_history.append(
                {
                    "_id": str(edit.pk),
                    "original_body": edit.original_body,
                    "reason_code": edit.reason_code,
                    "editor_username": edit.editor.username,
                    "author_id": edit.editor.pk,
                    "created_at": edit.created_at,
                }
            )

        endorsement = {
            "user_id": self.endorsement.get("user_id") if self.endorsement else None,
            "time": self.endorsement.get("time") if self.endorsement else None,
        }

        data = {
            "_id": str(self.pk),
            "votes": self.get_votes,
            "visible": self.visible,
            "abuse_flaggers": [str(flagger) for flagger in self.abuse_flaggers],
            "historical_abuse_flaggers": [
                str(flagger) for flagger in self.historical_abuse_flaggers
            ],
            "parent_ids": self.get_parent_ids(),
            "parent_id": str(self.parent.pk) if self.parent else "None",
            "at_position_list": [],
            "body": self.body,
            "course_id": self.course_id,
            "_type": "Comment",
            "endorsed": self.endorsed,
            "anonymous": self.anonymous,
            "anonymous_to_peers": self.anonymous_to_peers,
            "author_id": str(self.author.pk),
            "comment_thread_id": str(self.comment_thread.pk),
            "child_count": self.child_count,
            "author_username": self.author.username,
            "sk": str(self.pk),
            "updated_at": self.updated_at,
            "created_at": self.created_at,
            "endorsement": endorsement if self.endorsement else None,
        }
        if edit_history:
            data["edit_history"] = edit_history

        return data

    @classmethod
    def get(cls, comment_id: str) -> Comment:
        """Get a comment model instance."""
        return cls.objects.get(pk=int(comment_id))

    @classmethod
    def create_comment(cls, data: dict[str, Any]) -> "Comment":
        """Create and return a new Comment instance using ORM logic."""
        comment_thread = None
        parent = None
        comment_thread_id = data.get("comment_thread_id")
        parent_id = data.get("parent_id")
        if comment_thread_id:
            comment_thread = CommentThread.objects.get(pk=int(comment_thread_id))
        if parent_id:
            parent = cls.objects.get(pk=int(parent_id))
        new_comment = cls.objects.create(
            body=data.get("body"),
            course_id=data.get("course_id"),
            anonymous=data.get("anonymous", False),
            anonymous_to_peers=data.get("anonymous_to_peers", False),
            author=User.objects.get(pk=int(data["author_id"])),
            comment_thread=comment_thread,
            parent=parent,
            depth=data.get("depth", 0),
        )
        new_comment.sort_key = new_comment.get_sort_key()
        new_comment.save()
        return new_comment

    @classmethod
    def get_thread_id_by_comment_id(cls, comment_id: str) -> str:
        """Return the thread id for the given comment id."""
        try:
            comment = cls.objects.get(pk=comment_id)
        except ObjectDoesNotExist as exc:
            raise ValueError("comment does not exist.") from exc
        return comment.comment_thread.pk

    @classmethod
    def get_comment(cls, comment_id: str) -> dict[str, Any] | None:
        """Return comment as dict from comment_id."""
        try:
            comment = cls.objects.get(pk=comment_id)
        except cls.DoesNotExist:
            return None
        return comment.to_dict()

    @classmethod
    def update_comment_and_get_updated_comment(
        cls,
        comment_id: str,
        body: Optional[str] = None,
        course_id: Optional[str] = None,
        user_id: Optional[str] = None,
        anonymous: Optional[bool] = False,
        anonymous_to_peers: Optional[bool] = False,
        endorsed: Optional[bool] = None,
        editing_user_id: Optional[str] = None,
        edit_reason_code: Optional[str] = None,
        endorsement_user_id: Optional[str] = None,
    ) -> dict[str, Any] | None:
        """Update an existing comment and return its dict."""
        try:
            comment = cls.objects.get(id=comment_id)
        except cls.DoesNotExist:
            return None

        original_body = comment.body
        if body:
            comment.body = body
        if course_id:
            comment.course_id = course_id
        if user_id:
            comment.author = User.objects.get(pk=user_id)
        if anonymous is not None:
            comment.anonymous = anonymous
        if anonymous_to_peers is not None:
            comment.anonymous_to_peers = anonymous_to_peers
        if endorsed is not None:
            comment.endorsed = endorsed
            if endorsed is False:
                comment.endorsement = {}
            if endorsement_user_id:
                comment.endorsement = {
                    "user_id": endorsement_user_id,
                    "time": str(timezone.now()),
                }
        if editing_user_id:
            EditHistory.objects.create(
                content_object_id=comment.pk,
                content_type=comment.content_type,
                editor=User.objects.get(pk=editing_user_id),
                original_body=original_body,
                reason_code=edit_reason_code,
                created_at=timezone.now(),
            )
        comment.updated_at = timezone.now()
        comment.save()
        return comment.to_dict()

    @classmethod
    def delete_comment(cls, comment_id: str) -> None:
        """Delete comment from comment_id."""
        comment = cls.objects.get(pk=comment_id)
        comment.delete()

    def doc_to_hash(self) -> dict[str, Any]:
        """
        Converts the Comment model instance to a dictionary representation for Elasticsearch.
        """
        return {
            "body": self.body,
            "course_id": self.course_id,
            "comment_thread_id": self.comment_thread.pk,
            "commentable_id": None,
            "group_id": self.group_id,
            "context": "course",
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "title": None,
        }

    @classmethod
    def get_course_id_by_comment_id(cls, comment_id: str) -> str | None:
        """Return course_id for the matching comment."""
        comment = cls.objects.filter(id=comment_id).first()
        if comment:
            return comment.course_id
        return None

    class Meta:
        app_label = "forum"
        indexes = [
            models.Index(fields=["author", "course_id"]),
            models.Index(fields=["comment_thread", "author", "created_at"]),
            models.Index(fields=["comment_thread", "endorsed"]),
            models.Index(fields=["course_id", "parent", "endorsed"]),
            models.Index(fields=["course_id", "anonymous", "anonymous_to_peers"]),
            models.Index(
                fields=["author", "course_id", "anonymous", "anonymous_to_peers"]
            ),
        ]


class EditHistory(models.Model):
    """Edit history model class"""

    DISCUSSION_MODERATION_EDIT_REASON_CODES = [
        ("grammar-spelling", _("Has grammar / spelling issues")),
        ("needs-clarity", _("Content needs clarity")),
        ("academic-integrity", _("Has academic integrity concern")),
        ("inappropriate-language", _("Has inappropriate language")),
        ("format-change", _("Formatting changes needed")),
        ("post-type-change", _("Post type needs change")),
        ("contains-pii", _("Contains personally identifiable information")),
        ("violates-guidelines", _("Violates community guidelines")),
    ]

    reason_code: models.CharField[Optional[str], str] = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        choices=DISCUSSION_MODERATION_EDIT_REASON_CODES,
    )
    original_body: models.TextField[str, str] = models.TextField()
    editor: models.ForeignKey[User, User] = models.ForeignKey(
        User, on_delete=models.CASCADE
    )
    created_at: models.DateTimeField[datetime, datetime] = models.DateTimeField(
        auto_now_add=True
    )
    content_type: models.ForeignKey[ContentType] = models.ForeignKey(
        ContentType, on_delete=models.CASCADE
    )
    content_object_id: models.PositiveIntegerField[int, int] = (
        models.PositiveIntegerField()
    )
    content: GenericForeignKey = GenericForeignKey("content_type", "content_object_id")

    class Meta:
        app_label = "forum"
        indexes = [
            models.Index(fields=["editor"]),
            models.Index(fields=["content_type", "content_object_id"]),
            models.Index(fields=["created_at"]),
        ]


class AbuseFlagger(models.Model):
    """Abuse flagger model class"""

    content_type: models.ForeignKey[ContentType] = models.ForeignKey(
        ContentType, on_delete=models.CASCADE
    )
    content_object_id: models.PositiveIntegerField[int, int] = (
        models.PositiveIntegerField()
    )
    content: GenericForeignKey = GenericForeignKey("content_type", "content_object_id")
    user: models.ForeignKey[User, User] = models.ForeignKey(
        User, on_delete=models.CASCADE
    )
    flagged_at: models.DateTimeField[datetime, datetime] = models.DateTimeField(
        default=timezone.now
    )

    @staticmethod
    def flag_content(content: Any, user: User) -> bool:
        """
        Flag content as abuse by a user.

        Args:
            content: The content instance (thread or comment).
            user: The user instance.

        Returns:
            bool: True if this is the first flag, False otherwise.
        """

        # Check if user already flagged this content
        existing_flag = AbuseFlagger.objects.filter(
            user=user,
            content_object_id=content.pk,
            content_type=content.content_type,
        ).first()

        if not existing_flag:
            AbuseFlagger.objects.create(
                user=user,
                content_type=content.content_type,
                content_object_id=content.pk,
                flagged_at=timezone.now(),
            )
            return True
        return False

    @staticmethod
    def unflag_content(content: Any, user: User) -> bool:
        """
        Remove abuse flag from content by a user.

        Args:
            content: The content instance (thread or comment).
            user: The user instance.

        Returns:
            bool: True if flag was removed, False if no flag existed.
        """

        deleted_count = AbuseFlagger.objects.filter(
            user=user,
            content_object_id=content.pk,
            content_type=content.content_type,
        ).delete()[0]

        return deleted_count > 0

    @staticmethod
    def unflag_all_content(content: Any) -> None:
        """
        Remove all abuse flags from content.

        Args:
            content: The content instance (thread or comment).
        """

        # Get all current abuse flaggers
        current_flaggers = AbuseFlagger.objects.filter(
            content_object_id=content.pk,
            content_type=content.content_type,
        )

        # Move current flags to historical flags
        for flag in current_flaggers:
            HistoricalAbuseFlagger.objects.get_or_create(
                content_type=content.content_type,
                content_object_id=content.pk,
                user=flag.user,
                defaults={"flagged_at": timezone.now()},
            )

        # Delete all current abuse flags
        current_flaggers.delete()

    class Meta:
        app_label = "forum"
        unique_together = ("user", "content_type", "content_object_id")
        indexes = [
            models.Index(fields=["content_type", "content_object_id"]),
            models.Index(fields=["user", "content_type", "content_object_id"]),
        ]


class HistoricalAbuseFlagger(models.Model):
    """Historical abuse flagger model class"""

    content_type: models.ForeignKey[ContentType] = models.ForeignKey(
        ContentType, on_delete=models.CASCADE
    )
    content_object_id: models.PositiveIntegerField[int, int] = (
        models.PositiveIntegerField()
    )
    content: GenericForeignKey = GenericForeignKey("content_type", "content_object_id")
    user: models.ForeignKey[User, User] = models.ForeignKey(
        User, on_delete=models.CASCADE
    )
    flagged_at: models.DateTimeField[datetime, datetime] = models.DateTimeField(
        default=timezone.now
    )

    @staticmethod
    def has_historical_flags(content: Any) -> bool:
        """
        Check if content has any historical abuse flags.

        Args:
            content: The content instance (thread or comment).

        Returns:
            bool: True if content has historical flags, False otherwise.
        """

        return HistoricalAbuseFlagger.objects.filter(
            content_object_id=content.pk,
            content_type=content.content_type,
        ).exists()

    class Meta:
        app_label = "forum"
        unique_together = ("user", "content_type", "content_object_id")
        indexes = [
            models.Index(fields=["content_type", "content_object_id"]),
            models.Index(fields=["user", "content_type", "content_object_id"]),
        ]


class ReadState(models.Model):
    """Read state model."""

    course_id: models.CharField[str, str] = models.CharField(max_length=255)
    user: models.ForeignKey[User, User] = models.ForeignKey(
        User, related_name="read_states", on_delete=models.CASCADE
    )
    last_read_times: models.QuerySet[LastReadTime]

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the model."""
        last_read_times = {}
        for last_read_time in self.last_read_times.all():
            last_read_times[str(last_read_time.comment_thread.pk)] = (
                last_read_time.timestamp
            )
        return {
            "_id": str(self.pk),
            "last_read_times": last_read_times,
            "course_id": self.course_id,
        }

    class Meta:
        app_label = "forum"
        unique_together = ("course_id", "user")
        indexes = [
            models.Index(fields=["user", "course_id"]),
        ]


class LastReadTime(models.Model):
    """Last read time model."""

    read_state: models.ForeignKey[ReadState] = models.ForeignKey(
        ReadState, related_name="last_read_times", on_delete=models.CASCADE
    )
    comment_thread: models.ForeignKey[CommentThread, CommentThread] = models.ForeignKey(
        CommentThread, on_delete=models.CASCADE
    )
    timestamp: models.DateTimeField[datetime, datetime] = models.DateTimeField()

    class Meta:
        app_label = "forum"
        unique_together = ("read_state", "comment_thread")
        indexes = [
            models.Index(fields=["read_state", "timestamp"]),
            models.Index(fields=["comment_thread"]),
        ]


class UserVote(models.Model):
    """User votes model class"""

    user: models.ForeignKey[User, User] = models.ForeignKey(
        User, on_delete=models.CASCADE
    )
    content_type: models.ForeignKey[ContentType] = models.ForeignKey(
        ContentType, on_delete=models.CASCADE
    )
    content_object_id: models.PositiveIntegerField[int, int] = (
        models.PositiveIntegerField()
    )
    content: GenericForeignKey = GenericForeignKey("content_type", "content_object_id")
    vote: models.IntegerField[int, int] = models.IntegerField(
        validators=[validate_upvote_or_downvote]
    )

    @staticmethod
    def update_vote(
        content: Content, user: User, vote_type: str = "", is_deleted: bool = False
    ) -> bool:
        """
        Update a vote on a thread or comment (either upvote or downvote).
        :param content: The content instance (thread or comment).
        :param user: The user instance.
        :param vote_type: String indicating the type of vote ('up' or 'down').
        :param is_deleted: Boolean indicating if the user is removing their vote (True) or voting (False).
        :return: True if the vote was successfully updated, False otherwise.
        """
        votes = content.votes
        user_vote = votes.filter(user__pk=user.pk).first()
        if not is_deleted:
            if vote_type not in ["up", "down"]:
                raise ValueError("Invalid vote_type, use ('up' or 'down')")
            if not user_vote:
                vote = 1 if vote_type == "up" else -1
                user_vote = UserVote.objects.create(
                    user=user,
                    content=content,
                    vote=vote,
                    content_type=content.content_type,
                )
            if vote_type == "up":
                user_vote.vote = 1
            else:
                user_vote.vote = -1
            user_vote.save()
            return True
        else:
            if user_vote:
                user_vote.delete()
                return True
        return False

    class Meta:
        app_label = "forum"
        unique_together = ("user", "content_type", "content_object_id")
        indexes = [
            models.Index(fields=["vote"]),
            models.Index(fields=["user", "vote"]),
            models.Index(fields=["content_type", "content_object_id"]),
        ]


class Subscription(models.Model):
    """Subscription model class"""

    subscriber: models.ForeignKey[User, User] = models.ForeignKey(
        User, on_delete=models.CASCADE
    )
    source_content_type: models.ForeignKey[ContentType, ContentType] = (
        models.ForeignKey(ContentType, on_delete=models.CASCADE)
    )
    source_object_id: models.PositiveIntegerField[int, int] = (
        models.PositiveIntegerField()
    )
    source: GenericForeignKey = GenericForeignKey(
        "source_content_type", "source_object_id"
    )
    created_at: models.DateTimeField[datetime, datetime] = models.DateTimeField(
        auto_now_add=True
    )
    updated_at: models.DateTimeField[datetime, datetime] = models.DateTimeField(
        auto_now=True
    )

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the model."""
        return {
            "_id": str(self.pk),
            "subscriber_id": str(self.subscriber.pk),
            "source_id": str(self.source_object_id),
            "source_type": self.source_content_type.model,
            "updated_at": self.updated_at,
            "created_at": self.created_at,
        }

    @staticmethod
    def find_subscribed_threads(
        user_id: str, course_id: Optional[str] = None
    ) -> list[str]:
        """
        Find threads that a user is subscribed to in a specific course.

        Args:
            user_id (str): The ID of the user.
            course_id (str): The ID of the course.

        Returns:
            list: A list of thread ids that the user is subscribed to in the course.
        """
        subscriptions = Subscription.objects.filter(
            subscriber__pk=user_id,
            source_content_type=ContentType.objects.get_for_model(CommentThread),
        )
        thread_ids = [
            str(subscription.source_object_id) for subscription in subscriptions
        ]
        if course_id:
            thread_ids = list(
                CommentThread.objects.filter(
                    pk__in=thread_ids,
                    course_id=course_id,
                ).values_list("pk", flat=True)
            )

        return thread_ids

    @staticmethod
    def subscribe_user(
        user_id: str, source_id: str, source_type: str
    ) -> dict[str, Any] | None:
        """
        Subscribe a user to a source.

        Args:
            user_id (str): The ID of the user to subscribe.
            source_id (str): The ID of the source to subscribe to.
            source_type (str): The type of the source.

        Returns:
            dict[str, Any] | None: The subscription data if successful, None otherwise.
        """
        source = Content.get_entity_from_type(source_id, source_type)
        if source is None:
            return None

        subscription, _ = Subscription.objects.get_or_create(
            subscriber=User.objects.get(pk=int(user_id)),
            source_object_id=source.pk,
            source_content_type=source.content_type,
        )
        return subscription.to_dict()

    @staticmethod
    def unsubscribe_user(user_id: str, source_id: str, source_type: str) -> None:
        """
        Unsubscribe a user from a source.

        Args:
            user_id (str): The ID of the user to unsubscribe.
            source_id (str): The ID of the source to unsubscribe from.
            source_type (str): The type of the source.
        """
        source = Content.get_entity_from_type(source_id, source_type)
        if source is None:
            return

        Subscription.objects.filter(
            subscriber=User.objects.get(pk=int(user_id)),
            source_object_id=source.pk,
            source_content_type=source.content_type,
        ).delete()

    @staticmethod
    def delete_subscriptions_of_a_thread(thread_id: str) -> None:
        """
        Delete all subscriptions for a specific thread.

        Args:
            thread_id (str): The ID of the thread.
        """
        source = Content.get_entity_from_type(thread_id, "CommentThread")
        if source is None:
            return

        Subscription.objects.filter(
            source_object_id=source.pk,
            source_content_type=source.content_type,
        ).delete()

    @staticmethod
    def unsubscribe_all(user_id: str) -> None:
        """
        Unsubscribe user from all content.

        Args:
            user_id (str): The ID of the user to unsubscribe from all content.
        """
        Subscription.objects.filter(subscriber__pk=user_id).delete()

    @staticmethod
    def get_subscription(
        subscriber_id: str, source_id: str, source_type: str
    ) -> dict[str, Any] | None:
        """
        Get a specific subscription by subscriber and source.

        Args:
            subscriber_id (str): The ID of the subscriber.
            source_id (str): The ID of the source.
            source_type (str): The type of the source.

        Returns:
            dict[str, Any] | None: The subscription data if found, None otherwise.
        """
        source = Content.get_entity_from_type(source_id, source_type)
        if not source:
            return None
        try:
            subscription = Subscription.objects.get(
                subscriber_id=User.objects.get(pk=int(subscriber_id)),
                source_object_id=source.pk,
                source_content_type=source.content_type,
            )
        except Subscription.DoesNotExist:
            return None
        return subscription.to_dict()

    @staticmethod
    def get_subscriptions(query: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Get subscriptions based on query filters.

        Args:
            query (dict[str, Any]): Query parameters including source_id and source_type.

        Returns:
            list[dict[str, Any]]: List of subscription data.
        """
        source = Content.get_entity_from_type(
            entity_id=query["source_id"], entity_type=query.get("source_type", "")
        )
        if not source:
            return []

        subscriptions = (
            Subscription.objects.filter(
                source_object_id=source.pk,
                source_content_type=source.content_type,
            )
            .distinct()
            .order_by("subscriber_id", "source_object_id")
        )

        return [subscription.to_dict() for subscription in subscriptions]

    class Meta:
        app_label = "forum"
        unique_together = ("subscriber", "source_content_type", "source_object_id")
        indexes = [
            models.Index(fields=["subscriber"]),
            models.Index(
                fields=["subscriber", "source_object_id", "source_content_type"]
            ),
            models.Index(fields=["subscriber", "source_content_type"]),
            models.Index(fields=["source_object_id", "source_content_type"]),
        ]


class MongoContent(models.Model):
    """MongoContent model class."""

    content_type: models.ForeignKey[ContentType] = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True
    )
    content_object_id: models.PositiveIntegerField[int, int] = (
        models.PositiveIntegerField(null=True)
    )
    content: GenericForeignKey = GenericForeignKey("content_type", "content_object_id")
    mongo_id: models.CharField[str, str] = models.CharField(max_length=50, unique=True)

    class Meta:
        app_label = "forum"


class Commentable:
    """Utility class for commentable-related queries (not a DB model)."""

    @staticmethod
    def get_counts_based_on_type(course_id: str) -> dict[str, Any]:
        """
        Get the counts of discussion and question threads for a given course.

        Args:
            course_id (str): The ID of the course.

        Returns:
            dict: A dictionary with commentable IDs as keys and counts of discussion and question threads as values.
        """
        result = (
            CommentThread.objects.filter(course_id=course_id)
            .values("commentable_id")
            .annotate(
                discussion_count=models.Count(
                    models.Case(
                        models.When(thread_type="discussion", then=1),
                        output_field=models.IntegerField(),
                    )
                ),
                question_count=models.Count(
                    models.Case(
                        models.When(thread_type="question", then=1),
                        output_field=models.IntegerField(),
                    )
                ),
            )
            .order_by()
        )
        commentable_counts = {}
        for commentable in result:
            topic_id = commentable["commentable_id"]
            commentable_counts[topic_id] = {
                "discussion": commentable["discussion_count"],
                "question": commentable["question_count"],
            }
        return commentable_counts
