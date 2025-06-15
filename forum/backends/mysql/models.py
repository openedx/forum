"""MySQL models for forum v2."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from django.contrib.auth.models import User  # pylint: disable=E5142
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import QuerySet, F
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

    @classmethod
    def find_or_create(
        cls,
        user_id: str,
        username: Optional[str] = None,
        default_sort_key: Optional[str] = "date",
    ) -> str:
        """Find or create a forum user."""
        try:
            user = User.objects.get(pk=user_id)
            cls.objects.get_or_create(
                user=user,
                defaults={"default_sort_key": default_sort_key or "date"}
            )
            if username and username != user.username:
                user.username = username
                user.save()
            return str(user.pk)
        except User.DoesNotExist:
            return ""


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

    @classmethod
    def find_or_create(cls, user_id: str, course_id: str) -> dict[str, Any]:
        """Find or create course stats for a user."""
        user = User.objects.get(pk=user_id)
        course_stat, _ = cls.objects.get_or_create(
            user=user,
            course_id=course_id,
            defaults={
                "active_flags": 0,
                "inactive_flags": 0,
                "threads": 0,
                "responses": 0,
                "replies": 0,
            }
        )
        return course_stat.to_dict()

    @classmethod
    def update_stats(cls, user_id: str, course_id: str, **kwargs: Any) -> None:
        """Update stats for a course."""
        user = User.objects.get(pk=user_id)
        course_stat, _ = cls.objects.get_or_create(
            user=user,
            course_id=course_id,
            defaults={
                "active_flags": 0,
                "inactive_flags": 0,
                "threads": 0,
                "responses": 0,
                "replies": 0,
            }
        )

        for key, value in kwargs.items():
            if hasattr(course_stat, key):
                setattr(course_stat, key, F(key) + value)

        course_stat.save()
        cls.build_course_stats(user_id, course_id)

    @classmethod
    def build_course_stats(cls, user_id: str, course_id: str) -> None:
        """Build course stats for a user."""
        user = User.objects.get(pk=user_id)
        course_stat = cls.objects.get(user=user, course_id=course_id)

        # Get thread count
        thread_count = CommentThread.objects.filter(
            author=user,
            course_id=course_id
        ).count()

        # Get response and reply counts
        comments = Comment.objects.filter(
            author=user,
            course_id=course_id
        )
        response_count = comments.filter(parent__isnull=True).count()
        reply_count = comments.filter(parent__isnull=False).count()

        # Get active and inactive flags
        content_types = [
            ContentType.objects.get_for_model(CommentThread),
            ContentType.objects.get_for_model(Comment)
        ]

        active_flags = AbuseFlagger.objects.filter(
            content_type__in=content_types,
            content__author=user,
            content__course_id=course_id
        ).count()

        inactive_flags = HistoricalAbuseFlagger.objects.filter(
            content_type__in=content_types,
            content__author=user,
            content__course_id=course_id
        ).count()

        # Update the stats
        course_stat.threads = thread_count
        course_stat.responses = response_count
        course_stat.replies = reply_count
        course_stat.active_flags = active_flags
        course_stat.inactive_flags = inactive_flags
        course_stat.last_activity_at = timezone.now()
        course_stat.save()

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the model."""
        return {
            "_id": str(self.pk),
            "course_id": self.course_id,
            "active_flags": self.active_flags,
            "inactive_flags": self.inactive_flags,
            "threads": self.threads,
            "responses": self.responses,
            "replies": self.replies,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
        }

    class Meta:
        app_label = "forum"
        unique_together = ("user", "course_id")
        indexes = [
            models.Index(fields=["user", "course_id"]),
            models.Index(fields=["course_id"]),
            models.Index(fields=["last_activity_at"]),
        ]


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
            votes["count"] = votes["up_count"] + votes["down_count"]
        return votes

    def flag_abuse(self, user: User) -> None:
        """Flag content as abuse."""
        if user.pk not in self.abuse_flaggers:
            AbuseFlagger.objects.create(
                user=user,
                content=self,
                flagged_at=timezone.now()
            )
            if len(self.abuse_flaggers) == 1:  # First flag
                CourseStat.update_stats(
                    self.author.pk,
                    self.course_id,
                    active_flags=1
                )

    def unflag_abuse(self, user: User) -> None:
        """Unflag content as abuse."""
        has_no_historical_flags = len(self.historical_abuse_flaggers) == 0
        if user.pk in self.abuse_flaggers:
            AbuseFlagger.objects.filter(
                user=user,
                content_object_id=self.pk,
                content_type=self.content_type,
            ).delete()
            self._update_stats_after_unflag(has_no_historical_flags)

    def unflag_all_abuse(self) -> None:
        """Unflag all abuse flags."""
        has_no_historical_flags = len(self.historical_abuse_flaggers) == 0
        historical_abuse_flaggers = list(
            set(self.historical_abuse_flaggers) | set(self.abuse_flaggers)
        )

        # Create historical records
        for flagger_id in historical_abuse_flaggers:
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

        # Delete current flags
        AbuseFlagger.objects.filter(
            content_object_id=self.pk,
            content_type=self.content_type
        ).delete()

        self._update_stats_after_unflag(has_no_historical_flags)

    def _update_stats_after_unflag(self, has_no_historical_flags: bool) -> None:
        """Update stats after unflagging."""
        first_historical_flag = (
            has_no_historical_flags and not self.historical_abuse_flaggers
        )
        if first_historical_flag:
            CourseStat.update_stats(
                self.author.pk,
                self.course_id,
                inactive_flags=1
            )

        if not self.abuse_flaggers:
            CourseStat.update_stats(
                self.author.pk,
                self.course_id,
                active_flags=-1
            )

    def update_vote(self, user: User, vote_type: str, is_deleted: bool = False) -> bool:
        """Update vote for content."""
        if is_deleted:
            UserVote.objects.filter(
                user=user,
                content_type=self.content_type,
                content_object_id=self.pk
            ).delete()
            return True

        vote_value = 1 if vote_type == "up" else -1
        validate_upvote_or_downvote(vote_value)

        vote, created = UserVote.objects.get_or_create(
            user=user,
            content_type=self.content_type,
            content_object_id=self.pk,
            defaults={"vote": vote_value}
        )

        if not created and vote.vote != vote_value:
            vote.vote = vote_value
            vote.save()

        return True

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the content."""
        raise NotImplementedError

    def doc_to_hash(self) -> dict[str, Any]:
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
    commentable_id: models.CharField[str, str] = models.CharField(max_length=255)

    @property
    def comment_count(self) -> int:
        """Get the total number of comments in the thread."""
        return self.comment_set.count()

    @classmethod
    def get(cls, thread_id: str) -> CommentThread:
        """Get a thread by ID."""
        try:
            return cls.objects.get(pk=thread_id)
        except cls.DoesNotExist as exc:
            raise ValueError("Thread not found") from exc

    def pin(self) -> None:
        """Pin the thread."""
        self.pinned = True
        self.save()

    def unpin(self) -> None:
        """Unpin the thread."""
        self.pinned = False
        self.save()

    def close(self, closed_by: User, reason_code: Optional[str] = None) -> None:
        """Close the thread."""
        self.closed = True
        self.closed_by = closed_by
        self.close_reason_code = reason_code
        self.save()

    def reopen(self) -> None:
        """Reopen the thread."""
        self.closed = False
        self.closed_by = None
        self.close_reason_code = None
        self.save()

    def update_last_activity(self) -> None:
        """Update the last activity timestamp."""
        self.last_activity_at = timezone.now()
        self.save()

    @classmethod
    def get_filtered_threads(
        cls,
        course_id: str,
        group_ids: Optional[list[int]] = None,
        thread_type: Optional[str] = None,
        author_id: Optional[str] = None,
        flagged: bool = False,
        unanswered: bool = False,
        unresponded: bool = False,
    ) -> QuerySet[CommentThread]:
        """Get filtered threads based on various criteria."""
        queryset = cls.objects.filter(course_id=course_id)

        if group_ids:
            queryset = queryset.filter(group_id__in=group_ids)

        if thread_type:
            queryset = queryset.filter(thread_type=thread_type)

        if author_id:
            queryset = queryset.filter(author_id=author_id)

        if flagged:
            queryset = queryset.filter(
                pk__in=AbuseFlagger.objects.filter(
                    content_type=ContentType.objects.get_for_model(cls)
                ).values_list("content_object_id", flat=True)
            )

        if unanswered and thread_type == "question":
            queryset = queryset.filter(endorsed=False)

        if unresponded:
            queryset = queryset.filter(comment_count=0)

        return queryset

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the thread."""
        data = {
            "_id": str(self.pk),
            "anonymous": self.anonymous,
            "anonymous_to_peers": self.anonymous_to_peers,
            "at_position_list": [],
            "author_id": str(self.author.pk),
            "author_username": self.author.username,
            "body": self.body,
            "closed": self.closed,
            "close_reason_code": self.close_reason_code,
            "closed_by_id": str(self.closed_by.pk) if self.closed_by else None,
            "comment_count": self.comment_count,
            "commentable_id": self.commentable_id,
            "course_id": self.course_id,
            "created_at": self.created_at.isoformat(),
            "group_id": self.group_id,
            "pinned": self.pinned,
            "thread_type": self.thread_type,
            "title": self.title,
            "type": self.type,
            "updated_at": self.updated_at.isoformat(),
            "votes": self.get_votes,
            "abuse_flaggers": self.abuse_flaggers,
            "historical_abuse_flaggers": self.historical_abuse_flaggers,
        }
        return data

    def doc_to_hash(self) -> dict[str, Any]:
        """Return a dictionary representation for search indexing."""
        return {
            "_id": str(self.pk),
            "anonymous": self.anonymous,
            "anonymous_to_peers": self.anonymous_to_peers,
            "at_position_list": [],
            "author_id": str(self.author.pk),
            "author_username": self.author.username,
            "body": self.body,
            "closed": self.closed,
            "commentable_id": self.commentable_id,
            "course_id": self.course_id,
            "created_at": self.created_at.isoformat(),
            "group_id": self.group_id,
            "title": self.title,
            "type": self.type,
            "updated_at": self.updated_at.isoformat(),
            "comment_count": self.comment_count,
            "votes_point": self.get_votes["point"],
            "abuse_flagged": bool(self.abuse_flaggers),
            "historical_abuse_flagged": bool(self.historical_abuse_flaggers),
        }

    class Meta:
        app_label = "forum"
        indexes = [
            models.Index(fields=["course_id"]),
            models.Index(fields=["commentable_id"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["thread_type"]),
            models.Index(fields=["pinned"]),
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
        """Get the sort key for the comment."""
        if not self.sort_key:
            if self.parent:
                parent_sort_key = self.parent.get_sort_key()
                child_count = Comment.objects.filter(parent=self.parent).count()
                self.sort_key = f"{parent_sort_key}.{child_count:06d}"
            else:
                thread_comment_count = Comment.objects.filter(
                    comment_thread=self.comment_thread,
                    parent__isnull=True
                ).count()
                self.sort_key = f"{thread_comment_count:06d}"
            self.save()
        return self.sort_key

    def get_parent_ids(self) -> list[str]:
        """Get list of parent comment IDs."""
        parent_ids = []
        current = self
        while current.parent:
            parent_ids.append(str(current.parent.pk))
            current = current.parent
        return parent_ids

    @classmethod
    def get(cls, comment_id: str) -> Comment:
        """Get a comment by ID."""
        try:
            return cls.objects.get(pk=comment_id)
        except cls.DoesNotExist as exc:
            raise ValueError("Comment not found") from exc

    def update_child_count(self, increment: int = 1) -> None:
        """Update child count."""
        self.child_count = F("child_count") + increment
        self.save()
        if self.parent:
            self.parent.update_child_count(increment)

    def endorse(self, user: User) -> None:
        """Endorse the comment."""
        self.endorsed = True
        self.endorsement = {
            "user_id": str(user.pk),
            "time": timezone.now().isoformat()
        }
        self.save()

    def unendorse(self) -> None:
        """Remove endorsement from the comment."""
        self.endorsed = False
        self.endorsement = {}
        self.save()

    @classmethod
    def get_comments_by_thread(
        cls,
        thread_id: str,
        page: int = 1,
        per_page: int = 20,
        with_responses: bool = False,
        sort_order: str = "asc"
    ) -> dict[str, Any]:
        """Get paginated comments for a thread."""
        queryset = cls.objects.filter(comment_thread_id=thread_id)

        if not with_responses:
            queryset = queryset.filter(parent__isnull=True)

        total = queryset.count()

        # Sort by sort_key
        order_by = "sort_key" if sort_order == "asc" else "-sort_key"
        queryset = queryset.order_by(order_by)

        # Paginate
        start = (page - 1) * per_page
        end = start + per_page
        comments = queryset[start:end]

        return {
            "collection": [comment.to_dict() for comment in comments],
            "page": page,
            "num_pages": (total + per_page - 1) // per_page,
            "total": total,
        }

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the comment."""
        data = {
            "_id": str(self.pk),
            "anonymous": self.anonymous,
            "anonymous_to_peers": self.anonymous_to_peers,
            "author_id": str(self.author.pk),
            "author_username": self.author.username,
            "body": self.body,
            "course_id": self.course_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "endorsed": self.endorsed,
            "endorsement": self.endorsement,
            "child_count": self.child_count,
            "children": [],  # Populated by serializer if needed
            "depth": self.depth,
            "parent_id": str(self.parent.pk) if self.parent else None,
            "thread_id": str(self.comment_thread.pk),
            "type": self.type,
            "retired_username": self.retired_username,
            "votes": self.get_votes,
            "abuse_flaggers": self.abuse_flaggers,
            "historical_abuse_flaggers": self.historical_abuse_flaggers,
            "parent_ids": self.get_parent_ids(),
        }
        return data

    def doc_to_hash(self) -> dict[str, Any]:
        """Return a dictionary representation for search indexing."""
        return {
            "_id": str(self.pk),
            "anonymous": self.anonymous,
            "anonymous_to_peers": self.anonymous_to_peers,
            "author_id": str(self.author.pk),
            "author_username": self.author.username,
            "body": self.body,
            "course_id": self.course_id,
            "created_at": self.created_at.isoformat(),
            "endorsed": self.endorsed,
            "endorsement": self.endorsement,
            "comment_thread_id": str(self.comment_thread.pk),
            "parent_id": str(self.parent.pk) if self.parent else None,
            "votes_point": self.get_votes["point"],
            "abuse_flagged": bool(self.abuse_flaggers),
            "historical_abuse_flagged": bool(self.historical_abuse_flaggers),
            "depth": self.depth,
        }

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Override save to handle depth and child count."""
        if not self.pk:  # New comment
            if self.parent:
                self.depth = self.parent.depth + 1
                self.parent.update_child_count(1)
            self.comment_thread.update_last_activity()
        super().save(*args, **kwargs)

    class Meta:
        app_label = "forum"
        indexes = [
            models.Index(fields=["comment_thread"]),
            models.Index(fields=["parent"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["sort_key"]),
            models.Index(fields=["endorsed"]),
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

    @classmethod
    def find_or_create(cls, user_id: str, course_id: str) -> dict[str, Any]:
        """Find or create read state for a user and course."""
        user = User.objects.get(pk=user_id)
        read_state, _ = cls.objects.get_or_create(
            user=user,
            course_id=course_id
        )
        return read_state.to_dict()

    @classmethod
    def get_read_states(
        cls,
        thread_ids: list[str],
        user_id: str,
        course_id: str
    ) -> dict[str, list[Any]]:
        """Get read states for threads."""
        user = User.objects.get(pk=user_id)
        read_state = cls.objects.filter(user=user, course_id=course_id).first()

        if not read_state:
            return {
                "read": [],
                "unread": thread_ids,
                "last_read_times": {}
            }

        last_read_times = LastReadTime.objects.filter(
            read_state=read_state,
            comment_thread_id__in=thread_ids
        ).select_related('comment_thread')

        read_thread_ids = []
        unread_thread_ids = []
        last_read_times_dict = {}

        for thread_id in thread_ids:
            last_read = next(
                (lrt for lrt in last_read_times if str(lrt.comment_thread.pk) == thread_id),
                None
            )

            if last_read:
                read_thread_ids.append(thread_id)
                last_read_times_dict[thread_id] = last_read.timestamp.isoformat()
            else:
                unread_thread_ids.append(thread_id)

        return {
            "read": read_thread_ids,
            "unread": unread_thread_ids,
            "last_read_times": last_read_times_dict
        }

    def mark_thread_read(self, thread_id: str) -> None:
        """Mark a thread as read."""
        thread = CommentThread.objects.get(pk=thread_id)
        LastReadTime.objects.update_or_create(
            read_state=self,
            comment_thread=thread,
            defaults={"timestamp": timezone.now()}
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the model."""
        return {
            "_id": str(self.pk),
            "course_id": self.course_id,
            "user_id": str(self.user.pk),
            "last_read_times": {
                str(lrt.comment_thread.pk): lrt.timestamp.isoformat()
                for lrt in self.last_read_times.all()
            }
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
            models.Index(fields=["read_state", "comment_thread"]),
            models.Index(fields=["timestamp"]),
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

    @classmethod
    def get_user_voted_ids(cls, user_id: str, vote_type: str) -> list[str]:
        """Get content IDs that a user has voted on."""
        vote_value = 1 if vote_type == "up" else -1
        return list(
            cls.objects.filter(
                user_id=user_id,
                vote=vote_value
            ).values_list("content_object_id", flat=True)
        )

    def clean(self) -> None:
        """Validate the vote."""
        super().clean()
        validate_upvote_or_downvote(self.vote)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Override save to validate vote."""
        self.full_clean()
        super().save(*args, **kwargs)

    class Meta:
        app_label = "forum"
        unique_together = ("user", "content_type", "content_object_id")
        indexes = [
            models.Index(fields=["user", "content_type", "content_object_id"]),
            models.Index(fields=["content_type", "content_object_id"]),
            models.Index(fields=["vote"]),
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
