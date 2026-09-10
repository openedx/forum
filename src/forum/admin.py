"""Admin module for forum."""

from django.contrib import admin
from forum.models import (
    ForumUser,
    CourseStat,
    CommentThread,
    Comment,
    EditHistory,
    AbuseFlagger,
    HistoricalAbuseFlagger,
    ReadState,
    LastReadTime,
    UserVote,
    Subscription,
    MongoContent,
    ModerationAuditLog,
)


@admin.register(ForumUser)
class ForumUserAdmin(admin.ModelAdmin):  # type: ignore
    """Admin interface for ForumUser model."""

    list_display = ("user", "default_sort_key")
    search_fields = ("user__username", "user__email")


@admin.register(CourseStat)
class CourseStatAdmin(admin.ModelAdmin):  # type: ignore
    """Admin interface for CourseStat model."""

    list_display = (
        "user",
        "course_id",
        "active_flags",
        "inactive_flags",
        "threads",
        "responses",
        "replies",
        "last_activity_at",
    )
    search_fields = ("user__username", "course_id")
    list_filter = ("course_id",)


@admin.register(CommentThread)
class CommentThreadAdmin(admin.ModelAdmin):  # type: ignore
    """Admin interface for CommentThread model."""

    list_display = (
        "title",
        "author",
        "course_id",
        "thread_type",
        "context",
        "closed",
        "pinned",
        "is_spam",
        "created_at",
        "updated_at",
    )
    search_fields = ("title", "body", "author__username", "course_id")
    list_filter = ("thread_type", "context", "closed", "pinned", "is_spam")


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):  # type: ignore
    """Admin interface for Comment model."""

    list_display = (
        "comment_thread",
        "author",
        "body",
        "created_at",
        "updated_at",
        "endorsed",
        "anonymous",
        "is_spam",
    )
    search_fields = ("body", "author__username", "comment_thread__title")
    list_filter = ("endorsed", "anonymous", "is_spam")


@admin.register(EditHistory)
class EditHistoryAdmin(admin.ModelAdmin):  # type: ignore
    """Admin interface for EditHistory model."""

    list_display = ("editor", "content_object_id", "created_at", "reason_code")
    search_fields = ("editor__username", "original_body")
    list_filter = ("reason_code",)


@admin.register(AbuseFlagger)
class AbuseFlaggerAdmin(admin.ModelAdmin):  # type: ignore
    """Admin interface for AbuseFlagger model."""

    list_display = ("user", "content_object_id", "flagged_at")
    search_fields = ("user__username",)
    list_filter = ("content_type",)


@admin.register(HistoricalAbuseFlagger)
class HistoricalAbuseFlaggerAdmin(admin.ModelAdmin):  # type: ignore
    """Admin interface for HistoricalAbuseFlagger model."""

    list_display = ("user", "content_object_id", "flagged_at")
    search_fields = ("user__username",)
    list_filter = ("content_type",)


@admin.register(ReadState)
class ReadStateAdmin(admin.ModelAdmin):  # type: ignore
    """Admin interface for ReadState model."""

    list_display = ("user", "course_id")
    search_fields = ("user__username", "course_id")


@admin.register(LastReadTime)
class LastReadTimeAdmin(admin.ModelAdmin):  # type: ignore
    """Admin interface for LastReadTime model."""

    list_display = ("read_state", "comment_thread", "timestamp")
    search_fields = ("read_state__user__username", "comment_thread__title")


@admin.register(UserVote)
class UserVoteAdmin(admin.ModelAdmin):  # type: ignore
    """Admin interface for UserVote model."""

    list_display = ("user", "content_object_id", "vote")
    search_fields = ("user__username",)
    list_filter = ("vote",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):  # type: ignore
    """Admin interface for Subscription model."""

    list_display = (
        "subscriber",
        "source_object_id",
        "source_content_type",
        "created_at",
        "updated_at",
    )
    search_fields = ("subscriber__username",)
    list_filter = ("source_content_type",)


@admin.register(MongoContent)
class MongoContentAdmin(admin.ModelAdmin):  # type: ignore
    """Admin interface for MongoContent model."""

    list_display = ("mongo_id", "content_object_id", "content_type")
    search_fields = ("mongo_id",)


@admin.register(ModerationAuditLog)
class ModerationAuditLogAdmin(admin.ModelAdmin):  # type: ignore
    """Admin interface for ModerationAuditLog model."""

    list_display = (
        "timestamp",
        "classification",
        "actions_taken",
        "body_preview",
        "original_author",
        "moderator_override",
        "confidence_score",
    )
    list_filter = (
        "classification",
        "moderator_override",
        "timestamp",
    )
    search_fields = (
        "original_author__username",
        "moderator__username",
        "reasoning",
        "override_reason",
        "body",
    )
    readonly_fields = (
        "timestamp",
        "body",
        "classifier_output",
        "reasoning",
        "classification",
        "actions_taken",
        "confidence_score",
        "original_author",
    )
    fieldsets = (
        (
            "Moderation Decision",
            {
                "fields": (
                    "timestamp",
                    "classification",
                    "actions_taken",
                    "confidence_score",
                    "reasoning",
                )
            },
        ),
        ("Content Information", {"fields": ("body",)}),
        ("Author Information", {"fields": ("original_author",)}),
        (
            "Human Override",
            {
                "fields": (
                    "moderator_override",
                    "moderator",
                    "override_reason",
                )
            },
        ),
        (
            "Technical Details",
            {
                "fields": ("classifier_output",),
                "classes": ("collapse",),
            },
        ),
    )

    def body_preview(self, obj):  # type: ignore
        """Return a truncated preview of the body for list display."""
        if obj.body:
            return obj.body[:100] + "..." if len(obj.body) > 100 else obj.body
        return "-"

    body_preview.short_description = "Body Preview"  # type: ignore

    # pylint: disable=unused-argument
    def has_add_permission(self, request):  # type: ignore[no-untyped-def]
        """Disable adding audit logs manually."""
        return False

    # pylint: disable=unused-argument
    def has_delete_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        """Disable deleting audit logs to maintain integrity."""
        return False

    def get_queryset(self, request):  # type: ignore
        """Optimize queryset with related objects."""
        return (
            super()
            .get_queryset(request)
            .select_related("original_author", "moderator")
            .order_by("-timestamp")
        )
