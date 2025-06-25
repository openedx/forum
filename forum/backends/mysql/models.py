"""MySQL models for forum v2."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from django.contrib.auth.models import User  # pylint: disable=E5142
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import QuerySet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

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
    
    def to_hash(self, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """
        Converts forum user data to a hash, optionally enriched with subscription,
        voting, and authored content statistics based on the input parameters.
        """

        user = self.user
        if params is None:
            params = {}

        user_data = self.to_dict()
        hash_data = {
            "username": user_data["username"],
            "external_id": user_data["external_id"],
            "id": user_data["external_id"],
        }

        if params.get("complete"):
            subscribed_thread_ids = find_subscribed_threads(user.pk)
            upvoted_ids = list(
                UserVote.objects.filter(user__pk=user.pk, vote=1)
                .values_list("content_object_id", flat=True)
            )
            downvoted_ids = list(
                UserVote.objects.filter(user__pk=user.pk, vote=-1)
                .values_list("content_object_id", flat=True)
            )

            hash_data.update({
                "subscribed_thread_ids": subscribed_thread_ids,
                "subscribed_commentable_ids": [],
                "subscribed_user_ids": [],
                "follower_ids": [],
                "id": str(user.pk),
                "upvoted_ids": upvoted_ids,
                "downvoted_ids": downvoted_ids,
                "default_sort_key": user_data["default_sort_key"],
            })

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
            if params.get("group_ids"):
                group_threads = threads.filter(group_id__in=params["group_ids"] + [None])
                group_thread_ids = [str(thread.pk) for thread in group_threads]
                threads_count = len(group_thread_ids)

                comment_thread_ids = [
                    str(comment.comment_thread.pk)
                    for comment in comments
                    if comment.comment_thread and (
                        comment.comment_thread.group_id in params["group_ids"] or
                        comment.comment_thread.group_id is None
                    )
                ]
                comments_count = len(comment_thread_ids)
            else:
                thread_ids = [str(thread.pk) for thread in threads]
                threads_count = len(thread_ids)
                comment_thread_ids = [
                    str(comment.comment_thread.pk)
                    for comment in comments
                    if comment.comment_thread
                ]
                comments_count = len(comment_thread_ids)

            hash_data.update({
                "threads_count": threads_count,
                "comments_count": comments_count,
            })

        return hash_data


    def replace_username(self, text: str) -> str:
        """
        Replace the placeholder [[username]] in the given text with the user's actual username.

        Args:
            text (str): The text containing the placeholder.

        Returns:
            str: The text with the username placeholder replaced.
        """
        return text.replace("[[username]]", self.user.username)


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

    @staticmethod
    def update_stats_for_course(user_id: str, course_id: str, **kwargs: Any) -> None:
        from django.db.models import F
        user = User.objects.get(pk=user_id)
        course_stat, created = CourseStat.objects.get_or_create(
            user=user, course_id=course_id
        )
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
        CourseStat.build_course_stats(user_id, course_id)

    @staticmethod
    def build_course_stats(author_id: str, course_id: str) -> None:
        from datetime import timedelta
        from django.db.models import Count, Max
        from django.utils import timezone
        from django.contrib.contenttypes.models import ContentType
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
                content_object_id__in=comment_ids, content_type=ContentType.objects.get_for_model(Comment)
            )
            .values("content_object_id")
            .annotate(count=Count("content_object_id"))
            .count()
        )

        active_flags_threads = (
            AbuseFlagger.objects.filter(
                content_object_id__in=threads_ids,
                content_type=ContentType.objects.get_for_model(CommentThread),
            )
            .values("content_object_id")
            .annotate(count=Count("content_object_id"))
            .count()
        )

        active_flags = active_flags_comments + active_flags_threads

        inactive_flags_comments = (
            HistoricalAbuseFlagger.objects.filter(
                content_object_id__in=comment_ids, content_type=ContentType.objects.get_for_model(Comment)
            )
            .values("content_object_id")
            .annotate(count=Count("content_object_id"))
            .count()
        )

        inactive_flags_threads = (
            HistoricalAbuseFlagger.objects.filter(
                content_object_id__in=threads_ids,
                content_type=ContentType.objects.get_for_model(CommentThread),
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

    def flag_as_abuse(self, user: User) -> bool:
        """
        Flag this content as abuse by a specific user.
        Returns True if it was the first flag added.
        """
        if user.pk not in self.abuse_flaggers:
            AbuseFlagger.objects.create(
                user=user,
                content=self,
                flagged_at=timezone.now()
            )
            return True
        return False

    def unflag_as_abuse(self, user: User) -> bool:
        """
        Unflag this content as abuse by a specific user.
        Returns True if the user had flagged it before.
        """
        if user.pk in self.abuse_flaggers:
            AbuseFlagger.objects.filter(
                user=user,
                content_object_id=self.pk,
                content_type=self.content_type
            ).delete()
            return True
        return False

    @staticmethod
    def get_abuse_flagged_count(thread_ids: list[str]) -> dict[str, int]:
        """
        Retrieves the count of abuse-flagged comments for each thread in the provided list of thread IDs.

        Args:
            thread_ids (list[str]): List of thread IDs to check for abuse flags.

        Returns:
            dict[str, int]: A dictionary mapping thread IDs to their corresponding abuse-flagged comment count.
        """
        abuse_flagger_count_subquery = (
            AbuseFlagger.objects.filter(
                content_type=ContentType.objects.get_for_model(Comment),
                content_object_id=OuterRef("pk"),
            )
            .values("content_object_id")
            .annotate(count=Count("pk"))
            .values("count")
        )

        abuse_flagged_comments = (
            Comment.objects.filter(
                comment_thread__pk__in=thread_ids,
            )
            .annotate(
                abuse_flaggers_count=Subquery(
                    abuse_flagger_count_subquery, output_field=IntegerField()
                )
            )
            .filter(abuse_flaggers_count__gt=0)
        )

        result = {}
        for comment in abuse_flagged_comments:
            thread_pk = str(comment.comment_thread.pk)
            if thread_pk not in result:
                result[thread_pk] = 0
            result[thread_pk] += getattr(comment, "abuse_flaggers_count")

        return result

    def update_vote(self, user: User, vote_type: str = "", is_deleted: bool = False) -> bool:
        """
        Update a vote on this content.

        :param user: The user performing the vote.
        :param vote_type: Either 'up' or 'down'.
        :param is_deleted: If True, remove the user's vote.
        :return: True if the operation was successful, False otherwise.
        """
        user_vote = self.votes.filter(user__pk=user.pk).first()
        if not is_deleted:
            if vote_type not in ["up", "down"]:
                raise ValueError("Invalid vote_type, use ('up' or 'down')")
            if not user_vote:
                vote = 1 if vote_type == "up" else -1
                user_vote = UserVote.objects.create(
                    user=user,
                    content=self,
                    vote=vote,
                    content_type=self.content_type,
                )
            user_vote.vote = 1 if vote_type == "up" else -1
            user_vote.save()
            return True
        elif user_vote:
            user_vote.delete()
            return True
        return False

    def update_stats_after_unflag(self, user_id: str, has_no_historical_flags: bool) -> None:
        """
        Update the stats for the course after unflagging this content.
        """
        from forum.backends.mysql.api import MySQLBackend

        first_historical_flag = has_no_historical_flags and not self.historical_abuse_flaggers
        if first_historical_flag:
            MySQLBackend.update_stats_for_course(user_id, self.course_id, inactive_flags=1)
        if not self.abuse_flaggers:
            MySQLBackend.update_stats_for_course(user_id, self.course_id, active_flags=-1)

    def unflag_all_as_abuse(self) -> None:
        """Unflag all users from this content and archive them in historical flags."""
        all_flagger_ids = set(self.historical_abuse_flaggers) | set(self.abuse_flaggers)
        for flagger_id in all_flagger_ids:
            if not HistoricalAbuseFlagger.objects.filter(
                content_type=self.content_type,
                content_object_id=self.pk,
                user_id=flagger_id,
            ).exists():
                HistoricalAbuseFlagger.objects.create(
                    content=self,
                    user_id=flagger_id,
                    flagged_at=timezone.now(),
                )
        AbuseFlagger.objects.filter(
            content_object_id=self.pk, content_type=self.content_type
        ).delete()

    def upvote(self, user: User) -> bool:
        """Upvote this content by the given user."""
        return self.update_vote(user, vote_type="up", is_deleted=False)

    def downvote(self, user: User) -> bool:
        """Downvote this content by the given user."""
        return self.update_vote(user, vote_type="down", is_deleted=False)

    def remove_vote(self, user: User) -> bool:
        """Remove any vote by the given user on this content."""
        return self.update_vote(user, is_deleted=True)

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the content."""
        raise NotImplementedError

    def doc_to_hash(self) -> dict[str, Any]:
        """Return a dictionary representation of the content."""
        raise NotImplementedError

    @staticmethod
    def get_read_states(thread_ids: list[str], user_id: str, course_id: str) -> dict[str, list[Any]]:
        """
        Retrieves the read state and unread comment count for each thread in the provided list.

        Args:
            thread_ids (list[str]): List of thread IDs to check read state for.
            user_id (str): The ID of the user whose read states are being retrieved.
            course_id (str): The course ID associated with the threads.

        Returns:
            dict[str, list[Any]]: A dictionary mapping thread IDs to [is_read, unread_comment_count].
        """
        read_states = {}
        if not user_id:
            return read_states

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return read_states

        threads = CommentThread.objects.filter(pk__in=thread_ids)
        read_state = ReadState.objects.filter(user=user, course_id=course_id).first()
        if not read_state:
            return read_states

        read_dates = read_state.last_read_times

        for thread in threads:
            read_date = read_dates.filter(comment_thread=thread).first()
            if not read_date:
                continue

            last_activity_at = thread.last_activity_at
            is_read = read_date.timestamp >= last_activity_at
            unread_comment_count = (
                Comment.objects.filter(
                    comment_thread=thread, created_at__gte=read_date.timestamp
                )
                .exclude(author__pk=user_id)
                .count()
            )
            read_states[str(thread.pk)] = [is_read, unread_comment_count]

        return read_states

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

    def set_pin_state(self, action: str) -> None:
        """
        Pin or unpin the thread based on the action parameter.

        Args:
            action (str): The action to perform ("pin" or "unpin").
        """
        self.pinned = action == "pin"
        self.save()
    
    @staticmethod
    def filter_standalone_threads(comment_ids: list[str]) -> list[str]:
        """Filter out standalone threads from the list of threads."""
        comments = Comment.objects.filter(pk__in=comment_ids)
        filtered_threads = [
            comment.comment_thread
            for comment in comments
            if comment.comment_thread.context != "standalone"
        ]
        return [str(thread.pk) for thread in filtered_threads]

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
    def get_user_voted_ids(user_id: str) -> tuple[list[str], list[str]]:
        """
        Retrieve a tuple of two lists:
        - List of content object IDs the user upvoted
        - List of content object IDs the user downvoted

        Args:
            user_id (str): The user ID

        Returns:
            tuple: (list of upvoted IDs, list of downvoted IDs)
        """
        upvoted_ids = list(
            UserVote.objects.filter(user__pk=user_id, vote=1)
            .values_list("content_object_id", flat=True)
        )
        downvoted_ids = list(
            UserVote.objects.filter(user__pk=user_id, vote=-1)
            .values_list("content_object_id", flat=True)
        )
        return upvoted_ids, downvoted_ids

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

def get_username_from_id(user_id: str) -> Optional[str]:
    """
    Retrieve the username associated with a given user ID.

    Args:
        user_id (str): The unique identifier of the user.

    Returns:
        Optional[str]: The username of the user if found, or None if not.
    """
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return None
    return user.username


from typing import Optional
def find_subscribed_threads(user_id: str, course_id: Optional[str] = None) -> list[str]:
    """
    Find threads that a user is subscribed to in a specific course.

    Args:
        user_id (str): The ID of the user.
        course_id (str): The ID of the course.

    Returns:
        list: A list of thread ids that the user is subscribed to in the course.
    """
    from forum.backends.mysql.models import Subscription, CommentThread
    from django.contrib.contenttypes.models import ContentType

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