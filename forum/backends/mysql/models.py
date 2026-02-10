"""MySQL models for forum v2."""

# mypy: ignore-errors

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from django.contrib.auth.models import User  # pylint: disable=E5142
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import QuerySet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel
from opaque_keys.edx.django.models import CourseKeyField

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


class CourseStat(models.Model):
    """Course stats model."""

    course_id: models.CharField[str, str] = models.CharField(max_length=255)
    active_flags: models.IntegerField[int, int] = models.IntegerField(default=0)
    inactive_flags: models.IntegerField[int, int] = models.IntegerField(default=0)
    threads: models.IntegerField[int, int] = models.IntegerField(default=0)
    responses: models.IntegerField[int, int] = models.IntegerField(default=0)
    replies: models.IntegerField[int, int] = models.IntegerField(default=0)
    deleted_threads: models.IntegerField[int, int] = models.IntegerField(default=0)
    deleted_responses: models.IntegerField[int, int] = models.IntegerField(default=0)
    deleted_replies: models.IntegerField[int, int] = models.IntegerField(default=0)
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
            "deleted_threads": self.deleted_threads,
            "deleted_responses": self.deleted_responses,
            "deleted_replies": self.deleted_replies,
            "deleted_count": self.deleted_threads
            + self.deleted_responses
            + self.deleted_replies,
            "course_id": self.course_id,
            "last_activity_at": self.last_activity_at,
        }

    class Meta:
        app_label = "forum"
        unique_together = ("user", "course_id")


class Content(models.Model):
    """Content model."""

    index_name = ""

    author: models.ForeignKey[User, User] = models.ForeignKey(
        User, on_delete=models.CASCADE
    )
    author_username: models.CharField[Optional[str], str] = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Username at time of posting, preserved for historical accuracy",
    )
    retired_username: models.CharField[Optional[str], str] = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Username to display if author account was retired",
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
    is_spam: models.BooleanField[bool, bool] = models.BooleanField(
        default=False,
        help_text="Whether this content has been identified as spam by AI moderation",
    )
    is_deleted: models.BooleanField[bool, bool] = models.BooleanField(
        default=False,
        help_text="Whether this content has been soft deleted",
    )
    deleted_at: models.DateTimeField[Optional[datetime], datetime] = (
        models.DateTimeField(
            null=True,
            blank=True,
            help_text="When this content was soft deleted",
        )
    )
    deleted_by: models.ForeignKey[User, User] = models.ForeignKey(
        User,
        related_name="deleted_%(class)s",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="User who soft deleted this content",
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

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Set author_username on creation if not already set."""
        if not self.pk and not self.author_username:
            # On creation, store the current username
            if self.retired_username:
                self.author_username = self.retired_username
            elif self.author:
                self.author_username = self.author.username
        super().save(*args, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the content."""
        raise NotImplementedError

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
        """Return the number of comments in the thread (excluding deleted)."""
        return Comment.objects.filter(comment_thread=self, is_deleted=False).count()

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
            "author_username": self.author_username
            or self.retired_username
            or self.author.username,
            "updated_at": self.updated_at,
            "created_at": self.created_at,
            "last_activity_at": self.last_activity_at,
            "edit_history": edit_history,
            "group_id": self.group_id,
            "is_spam": self.is_spam,
            "is_deleted": self.is_deleted,
            "deleted_at": self.deleted_at,
            "deleted_by": str(self.deleted_by.pk) if self.deleted_by else None,
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
            models.Index(fields=["is_spam"]),
            models.Index(fields=["course_id", "is_spam"]),
            models.Index(fields=["author", "course_id", "is_spam"]),
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
            "author_username": self.author_username
            or self.retired_username
            or self.author.username,
            "sk": str(self.pk),
            "updated_at": self.updated_at,
            "created_at": self.created_at,
            "endorsement": endorsement if self.endorsement else None,
            "is_spam": self.is_spam,
            "is_deleted": self.is_deleted,
            "deleted_at": self.deleted_at,
            "deleted_by": str(self.deleted_by.pk) if self.deleted_by else None,
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
            models.Index(fields=["is_spam"]),
            models.Index(fields=["course_id", "is_spam"]),
            models.Index(fields=["author", "course_id", "is_spam"]),
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


class ModerationAuditLog(models.Model):
    """
    Unified audit log for all discussion moderation actions.

    Tracks both human moderator actions (bans, content removal) and
    AI moderation decisions (spam detection, auto-flagging).
    """

    # Moderation source - who initiated the action
    SOURCE_HUMAN = "human"
    SOURCE_AI = "ai"
    SOURCE_SYSTEM = "system"
    SOURCE_CHOICES = [
        (SOURCE_HUMAN, "Human Moderator"),
        (SOURCE_AI, "AI Classifier"),
        (SOURCE_SYSTEM, "System/Automated"),
    ]

    # Unified action types for both human and AI moderation
    # Human moderator actions on users
    ACTION_BAN = "ban_user"
    ACTION_BAN_REACTIVATE = "ban_reactivate"
    ACTION_UNBAN = "unban_user"
    ACTION_BAN_EXCEPTION = "ban_exception"
    ACTION_BULK_DELETE = "bulk_delete"
    # AI/Human actions on content
    ACTION_FLAGGED = "flagged"
    ACTION_SOFT_DELETED = "soft_deleted"
    ACTION_APPROVED = "approved"
    ACTION_NO_ACTION = "no_action"

    ACTION_CHOICES = [
        # Human moderator actions on users
        (ACTION_BAN, "Ban User"),
        (ACTION_BAN_REACTIVATE, "Ban Reactivated"),
        (ACTION_UNBAN, "Unban User"),
        (ACTION_BAN_EXCEPTION, "Ban Exception Created"),
        (ACTION_BULK_DELETE, "Bulk Delete"),
        # AI/Human actions on content
        (ACTION_FLAGGED, "Content Flagged"),
        (ACTION_SOFT_DELETED, "Content Soft Deleted"),
        (ACTION_APPROVED, "Content Approved"),
        (ACTION_NO_ACTION, "No Action Taken"),
    ]

    # AI classification types (only for AI moderation)
    CLASSIFICATION_SPAM = "spam"
    CLASSIFICATION_SPAM_OR_SCAM = "spam_or_scam"
    CLASSIFICATION_CHOICES = [
        (CLASSIFICATION_SPAM, "Spam"),
        (CLASSIFICATION_SPAM_OR_SCAM, "Spam or Scam"),
    ]

    # === Core Fields ===
    action_type: models.CharField[str, str] = models.CharField(
        max_length=50,
        choices=ACTION_CHOICES,
        default=ACTION_NO_ACTION,
        db_index=True,
        help_text="Type of moderation action taken",
    )
    source: models.CharField[str, str] = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default=SOURCE_AI,
        db_index=True,
        help_text="Who initiated the moderation action",
    )
    timestamp: models.DateTimeField[datetime, datetime] = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="When the moderation action was taken",
    )

    # === Target Fields ===
    # For user-targeted actions (bans/unbans)
    target_user: models.ForeignKey[Optional[User], Optional[User]] = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="audit_log_actions_received",
        db_index=True,
        help_text="Target user for user moderation actions (ban/unban)",
    )
    # For content-targeted actions (AI moderation)
    body: models.TextField[Optional[str], str] = models.TextField(
        null=True,
        blank=True,
        help_text="Content body that was moderated (for content moderation)",
    )
    original_author: models.ForeignKey[Optional[User], Optional[User]] = (
        models.ForeignKey(
            User,
            on_delete=models.CASCADE,
            null=True,
            blank=True,
            related_name="moderated_content",
            help_text="Original author of the moderated content",
        )
    )

    # === Actor Fields ===
    moderator: models.ForeignKey[Optional[User], Optional[User]] = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_log_actions_performed",
        db_index=True,
        help_text="Human moderator who performed or overrode the action",
    )

    # === Context Fields ===
    course_id: models.CharField[Optional[str], str] = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        help_text="Course ID for course-level moderation actions",
    )
    scope: models.CharField[Optional[str], str] = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="Scope of moderation (course/organization)",
    )
    reason: models.TextField[Optional[str], str] = models.TextField(
        null=True,
        blank=True,
        help_text="Reason provided for the moderation action",
    )

    # === AI-specific Fields (only populated for source='ai') ===
    classifier_output: models.JSONField[Optional[dict[str, Any]], dict[str, Any]] = (
        models.JSONField(
            null=True,
            blank=True,
            help_text="Full output from the AI classifier",
        )
    )
    classification: models.CharField[Optional[str], str] = models.CharField(
        max_length=20,
        choices=CLASSIFICATION_CHOICES,
        null=True,
        blank=True,
        help_text="AI classification result",
    )
    actions_taken: models.JSONField[Optional[list[str]], list[str]] = models.JSONField(
        null=True,
        blank=True,
        help_text="List of actions taken (for AI: ['flagged', 'soft_deleted'])",
    )
    confidence_score: models.FloatField[Optional[float], float] = models.FloatField(
        null=True,
        blank=True,
        help_text="AI confidence score if available",
    )
    reasoning: models.TextField[Optional[str], str] = models.TextField(
        null=True,
        blank=True,
        help_text="AI reasoning for the decision",
    )

    # === Override Fields (when human overrides AI) ===
    moderator_override: models.BooleanField[bool, bool] = models.BooleanField(
        default=False,
        help_text="Whether a human moderator overrode the AI decision",
    )
    override_reason: models.TextField[Optional[str], str] = models.TextField(
        null=True,
        blank=True,
        help_text="Reason for moderator override",
    )

    # === Flexible Metadata ===
    metadata: models.JSONField[Optional[dict[str, Any]], dict[str, Any]] = (
        models.JSONField(
            null=True,
            blank=True,
            help_text="Additional context (task IDs, counts, etc.)",
        )
    )

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the model."""
        data: dict[str, Any] = {
            "_id": str(self.pk),
            "action_type": self.action_type,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "moderator_id": str(self.moderator.pk) if self.moderator else None,
            "moderator_username": self.moderator.username if self.moderator else None,
            "course_id": self.course_id,
            "scope": self.scope,
            "reason": self.reason,
            "metadata": self.metadata,
        }

        # Add user moderation fields
        if self.target_user:
            data["target_user_id"] = str(self.target_user.pk)
            data["target_user_username"] = self.target_user.username

        # Add content moderation fields
        if self.body:
            data["body"] = self.body
        if self.original_author:
            data["original_author_id"] = str(self.original_author.pk)
            data["original_author_username"] = self.original_author.username

        # Add AI-specific fields
        if self.source == self.SOURCE_AI:
            data.update(
                {
                    "classifier_output": self.classifier_output,
                    "classification": self.classification,
                    "actions_taken": self.actions_taken,
                    "confidence_score": self.confidence_score,
                    "reasoning": self.reasoning,
                    "moderator_override": self.moderator_override,
                    "override_reason": self.override_reason,
                }
            )

        return data

    class Meta:
        app_label = "forum"
        verbose_name = "Moderation Audit Log"
        verbose_name_plural = "Moderation Audit Logs"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["timestamp"]),
            models.Index(fields=["action_type", "-timestamp"]),
            models.Index(fields=["source", "-timestamp"]),
            models.Index(fields=["target_user", "-timestamp"]),
            models.Index(fields=["original_author", "-timestamp"]),
            models.Index(fields=["moderator", "-timestamp"]),
            models.Index(fields=["course_id", "-timestamp"]),
            models.Index(fields=["classification"]),
        ]


# ==============================================================================
# DISCUSSION BAN MODELS
# ==============================================================================
# NOTE: These models were migrated from lms.djangoapps.discussion.models
#
# MIGRATION HISTORY:
# - Originally in lms.djangoapps.discussion.models
# - Tables created by forum/migrations/0006_add_discussion_ban_models.py
# - Old discussion app migration will be replaced with a deletion migration
# ==============================================================================


class DiscussionBan(TimeStampedModel):
    """
    Tracks users banned from course or organization discussions.

    Uses edX standard patterns:
    - TimeStampedModel for created/modified timestamps
    - CourseKeyField for course_id
    - Soft delete pattern with is_active flag
    """

    SCOPE_COURSE = "course"
    SCOPE_ORGANIZATION = "organization"
    SCOPE_CHOICES = [
        (SCOPE_COURSE, _("Course")),
        (SCOPE_ORGANIZATION, _("Organization")),
    ]

    # Core Fields
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="discussion_bans",
        db_index=True,
    )
    course_id = CourseKeyField(
        max_length=255,
        db_index=True,
        null=True,
        blank=True,
        help_text="Specific course for course-level bans, NULL for org-level bans",
    )
    org_key = models.CharField(
        max_length=255,
        db_index=True,
        null=True,
        blank=True,
        help_text="Organization name for org-level bans (e.g., 'HarvardX'), NULL for course-level",
    )
    scope = models.CharField(
        max_length=20,
        choices=SCOPE_CHOICES,
        default=SCOPE_COURSE,
        db_index=True,
    )
    is_active = models.BooleanField(default=True, db_index=True)

    # Metadata
    banned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="bans_issued",
    )
    reason = models.TextField()
    banned_at = models.DateTimeField(auto_now_add=True)
    unbanned_at = models.DateTimeField(null=True, blank=True)
    unbanned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bans_reversed",
    )

    class Meta:
        app_label = "forum"
        db_table = "discussion_user_ban"
        indexes = [
            models.Index(fields=["user", "is_active"], name="idx_user_active"),
            models.Index(fields=["course_id", "is_active"], name="idx_course_active"),
            models.Index(fields=["org_key", "is_active"], name="idx_org_active"),
            models.Index(fields=["scope", "is_active"], name="idx_scope_active"),
        ]
        constraints = [
            # Prevent duplicate course-level bans
            models.UniqueConstraint(
                fields=["user", "course_id"],
                condition=models.Q(is_active=True, scope="course"),
                name="unique_active_course_ban",
            ),
            # Prevent duplicate org-level bans
            models.UniqueConstraint(
                fields=["user", "org_key"],
                condition=models.Q(is_active=True, scope="organization"),
                name="unique_active_org_ban",
            ),
        ]
        verbose_name = _("Discussion Ban")
        verbose_name_plural = _("Discussion Bans")

    def __str__(self):
        if self.scope == self.SCOPE_COURSE:
            return f"Ban: {self.user.username} in {self.course_id} (course-level)"
        else:
            return f"Ban: {self.user.username} in {self.org_key} (org-level)"

    def clean(self):
        """Validate scope-based field requirements."""
        super().clean()
        if self.scope == self.SCOPE_COURSE:
            if not self.course_id:
                raise ValidationError(_("Course-level bans require course_id"))
        elif self.scope == self.SCOPE_ORGANIZATION:
            if not self.org_key:
                raise ValidationError(_("Organization-level bans require organization"))
            if self.course_id:
                raise ValidationError(
                    _("Organization-level bans should not have course_id set")
                )

    @classmethod
    def is_user_banned(cls, user, course_id, check_org=True):
        """
        Check if user is banned from discussions.

        Priority:
        1. Active course-level ban (most specific - overrides everything)
        2. Organization-level ban with exceptions (broader scope)

        Note: Inactive course-level bans do NOT prevent org-level bans from applying.
        Unbanning at course level only removes that specific course ban, not org bans.

        Args:
            user: User object
            course_id: CourseKey or string
            check_org: If True, also check organization-level bans

        Returns:
            bool: True if user has active ban
        """
        # pylint: disable=import-outside-toplevel
        from opaque_keys.edx.keys import CourseKey

        # Normalize course_id to CourseKey
        if isinstance(course_id, str):
            course_id = CourseKey.from_string(course_id)

        # Check for ACTIVE course-level ban first (highest priority)
        # Only active bans matter - inactive bans don't prevent org-level bans
        if cls.objects.filter(
            user=user, course_id=course_id, scope=cls.SCOPE_COURSE, is_active=True
        ).exists():
            return True

        # Check organization-level ban (lower priority)
        if check_org:
            # Try to get organization from CourseOverview, fallback to CourseKey
            try:
                # pylint: disable=import-outside-toplevel
                from openedx.core.djangoapps.content.course_overviews.models import (
                    CourseOverview,
                )

                course = CourseOverview.objects.get(id=course_id)
                org_name = course.org
            # pylint: disable=broad-exception-caught
            except (
                ImportError,
                AttributeError,
                Exception,
            ):
                # Fallback: extract org directly from course_id
                # ImportError: CourseOverview not available (test environment)
                # AttributeError: Missing settings.FEATURES
                # Exception: CourseOverview.DoesNotExist or other DB issues
                org_name = course_id.org

            # Check if org-level ban exists
            org_ban = cls.objects.filter(
                user=user,
                org_key=org_name,
                scope=cls.SCOPE_ORGANIZATION,
                is_active=True,
            ).first()

            if org_ban:
                # Check if there's an exception for this specific course
                if DiscussionBanException.objects.filter(
                    ban=org_ban, course_id=course_id
                ).exists():
                    # Exception exists - user is allowed in this course
                    return False
                # Org ban applies, no exception
                return True

        return False


class DiscussionBanException(TimeStampedModel):
    """
    Tracks course-level exceptions to organization-level bans.

    Allows moderators to unban a user from specific courses while
    maintaining an organization-wide ban for all other courses.

    Uses edX standard patterns:
    - TimeStampedModel for created/modified timestamps

    Example:
    - User banned from all HarvardX courses (org-level ban)
    - Exception created for HarvardX+CS50+2024
    - User can participate in CS50 but remains banned in all other HarvardX courses
    """

    # Core Fields
    ban = models.ForeignKey(
        "DiscussionBan",
        on_delete=models.CASCADE,
        related_name="exceptions",
        help_text="The organization-level ban this exception applies to",
    )
    course_id = CourseKeyField(
        max_length=255,
        db_index=True,
        help_text="Specific course where user is unbanned despite org-level ban",
    )

    # Metadata
    unbanned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="ban_exceptions_created",
    )
    reason = models.TextField(null=True, blank=True)

    class Meta:
        app_label = "forum"
        db_table = "discussion_ban_exception"
        constraints = [
            models.UniqueConstraint(
                fields=["ban", "course_id"], name="unique_ban_exception"
            ),
        ]
        indexes = [
            models.Index(fields=["ban", "course_id"], name="idx_ban_course"),
            models.Index(fields=["course_id"], name="idx_exception_course"),
        ]
        verbose_name = _("Discussion Ban Exception")
        verbose_name_plural = _("Discussion Ban Exceptions")

    def __str__(self):
        return f"Exception: {self.ban.user.username} allowed in {self.course_id}"

    def clean(self):
        """Validate that exception only applies to organization-level bans."""
        super().clean()
        if self.ban.scope != "organization":
            raise ValidationError(
                _("Exceptions can only be created for organization-level bans")
            )
