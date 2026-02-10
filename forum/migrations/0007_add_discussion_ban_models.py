"""Migration to add discussion ban models to forum app."""

# mypy: ignore-errors

from typing import Any

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import model_utils.fields
import opaque_keys.edx.django.models


def populate_source_with_ai(
    apps: Any, schema_editor: Any
) -> None:  # pylint: disable=unused-argument
    """
    Populate existing ModerationAuditLog records with source='ai'.

    This migration updates all existing records in production to have source='ai'.
    After AlterField runs, the field will exist with default='ai', but any records
    that were created before this migration might have source='human' (the old default).
    This function updates those records to 'ai'.

    Note: This assumes the 'source' field already exists in the database.
    If migration 0005 didn't create it, AlterField will add it with default='ai'.
    """
    ModerationAuditLog = apps.get_model("forum", "ModerationAuditLog")

    try:
        ModerationAuditLog.objects.exclude(source="ai").update(source="ai")
    except Exception:  # pylint: disable=broad-exception-caught
        pass


def reverse_populate_source(
    apps: Any, schema_editor: Any
) -> None:  # pylint: disable=unused-argument
    """
    Reverse migration: Set source back to 'human' for records that were updated.

    Note: This is a best-effort reversal. We can't perfectly restore the original
    state since we don't know which records were originally 'human' vs 'ai'.
    We set them all back to 'human' as a safe default.
    """
    ModerationAuditLog = apps.get_model("forum", "ModerationAuditLog")

    ModerationAuditLog.objects.filter(source="ai").update(source="human")


class Migration(migrations.Migration):
    """Migration to add discussion ban and moderation models."""

    dependencies = [
        ("forum", "0006_comment_deleted_at_comment_deleted_by_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DiscussionBan",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created",
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="created",
                    ),
                ),
                (
                    "modified",
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="modified",
                    ),
                ),
                (
                    "course_id",
                    opaque_keys.edx.django.models.CourseKeyField(
                        blank=True,
                        db_index=True,
                        help_text="Specific course for course-level bans, NULL for org-level bans",
                        max_length=255,
                        null=True,
                    ),
                ),
                (
                    "org_key",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        help_text="Organization name for org-level bans (e.g., 'HarvardX'), NULL for course-level",
                        max_length=255,
                        null=True,
                    ),
                ),
                (
                    "scope",
                    models.CharField(
                        choices=[
                            ("course", "Course"),
                            ("organization", "Organization"),
                        ],
                        db_index=True,
                        default="course",
                        max_length=20,
                    ),
                ),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("reason", models.TextField()),
                ("banned_at", models.DateTimeField(auto_now_add=True)),
                ("unbanned_at", models.DateTimeField(blank=True, null=True)),
                (
                    "banned_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="bans_issued",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "unbanned_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="bans_reversed",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="discussion_bans",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Discussion Ban",
                "verbose_name_plural": "Discussion Bans",
                "db_table": "discussion_user_ban",
            },
        ),
        migrations.CreateModel(
            name="DiscussionBanException",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created",
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="created",
                    ),
                ),
                (
                    "modified",
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="modified",
                    ),
                ),
                (
                    "course_id",
                    opaque_keys.edx.django.models.CourseKeyField(
                        db_index=True,
                        help_text="Specific course where user is unbanned despite org-level ban",
                        max_length=255,
                    ),
                ),
                ("reason", models.TextField(blank=True, null=True)),
                (
                    "ban",
                    models.ForeignKey(
                        help_text="The organization-level ban this exception applies to",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="exceptions",
                        to="forum.discussionban",
                    ),
                ),
                (
                    "unbanned_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ban_exceptions_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Discussion Ban Exception",
                "verbose_name_plural": "Discussion Ban Exceptions",
                "db_table": "discussion_ban_exception",
            },
        ),
        migrations.AddConstraint(
            model_name="discussionbanexception",
            constraint=models.UniqueConstraint(
                fields=("ban", "course_id"), name="unique_ban_exception"
            ),
        ),
        migrations.AddIndex(
            model_name="discussionbanexception",
            index=models.Index(fields=["ban", "course_id"], name="idx_ban_course"),
        ),
        migrations.AddIndex(
            model_name="discussionbanexception",
            index=models.Index(fields=["course_id"], name="idx_exception_course"),
        ),
        migrations.AddIndex(
            model_name="discussionban",
            index=models.Index(fields=["user", "is_active"], name="idx_user_active"),
        ),
        migrations.AddIndex(
            model_name="discussionban",
            index=models.Index(
                fields=["course_id", "is_active"], name="idx_course_active"
            ),
        ),
        migrations.AddIndex(
            model_name="discussionban",
            index=models.Index(fields=["org_key", "is_active"], name="idx_org_active"),
        ),
        migrations.AddIndex(
            model_name="discussionban",
            index=models.Index(fields=["scope", "is_active"], name="idx_scope_active"),
        ),
        migrations.AddConstraint(
            model_name="discussionban",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_active", True), ("scope", "course")),
                fields=("user", "course_id"),
                name="unique_active_course_ban",
            ),
        ),
        migrations.AddConstraint(
            model_name="discussionban",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_active", True), ("scope", "organization")),
                fields=("user", "org_key"),
                name="unique_active_org_ban",
            ),
        ),
        migrations.RemoveIndex(
            model_name="moderationauditlog",
            name="forum_moder_origina_c51089_idx",
        ),
        migrations.RemoveIndex(
            model_name="moderationauditlog",
            name="forum_moder_moderat_c62a1c_idx",
        ),
        migrations.AddField(
            model_name="moderationauditlog",
            name="action_type",
            field=models.CharField(
                choices=[
                    ("ban_user", "Ban User"),
                    ("ban_reactivate", "Ban Reactivated"),
                    ("unban_user", "Unban User"),
                    ("ban_exception", "Ban Exception Created"),
                    ("bulk_delete", "Bulk Delete"),
                    ("flagged", "Content Flagged"),
                    ("soft_deleted", "Content Soft Deleted"),
                    ("approved", "Content Approved"),
                    ("no_action", "No Action Taken"),
                ],
                db_index=True,
                default="no_action",
                help_text="Type of moderation action taken",
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name="moderationauditlog",
            name="course_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Course ID for course-level moderation actions",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="moderationauditlog",
            name="metadata",
            field=models.JSONField(
                blank=True,
                help_text="Additional context (task IDs, counts, etc.)",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="moderationauditlog",
            name="reason",
            field=models.TextField(
                blank=True,
                help_text="Reason provided for the moderation action",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="moderationauditlog",
            name="scope",
            field=models.CharField(
                blank=True,
                help_text="Scope of moderation (course/organization)",
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="moderationauditlog",
            name="target_user",
            field=models.ForeignKey(
                blank=True,
                help_text="Target user for user moderation actions (ban/unban)",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="audit_log_actions_received",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="moderationauditlog",
            name="actions_taken",
            field=models.JSONField(
                blank=True,
                help_text="List of actions taken (for AI: ['flagged', 'soft_deleted'])",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="moderationauditlog",
            name="body",
            field=models.TextField(
                blank=True,
                help_text="Content body that was moderated (for content moderation)",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="moderationauditlog",
            name="classification",
            field=models.CharField(
                blank=True,
                choices=[("spam", "Spam"), ("spam_or_scam", "Spam or Scam")],
                help_text="AI classification result",
                max_length=20,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="moderationauditlog",
            name="classifier_output",
            field=models.JSONField(
                blank=True, help_text="Full output from the AI classifier", null=True
            ),
        ),
        migrations.AlterField(
            model_name="moderationauditlog",
            name="moderator",
            field=models.ForeignKey(
                blank=True,
                help_text="Human moderator who performed or overrode the action",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="audit_log_actions_performed",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="moderationauditlog",
            name="original_author",
            field=models.ForeignKey(
                blank=True,
                help_text="Original author of the moderated content",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="moderated_content",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="moderationauditlog",
            name="reasoning",
            field=models.TextField(
                blank=True, help_text="AI reasoning for the decision", null=True
            ),
        ),
        migrations.AlterField(
            model_name="moderationauditlog",
            name="timestamp",
            field=models.DateTimeField(
                db_index=True,
                default=django.utils.timezone.now,
                help_text="When the moderation action was taken",
            ),
        ),
        migrations.AddField(
            model_name="moderationauditlog",
            name="source",
            field=models.CharField(
                choices=[
                    ("human", "Human Moderator"),
                    ("ai", "AI Classifier"),
                    ("system", "System/Automated"),
                ],
                db_index=True,
                default="ai",
                help_text="Who initiated the moderation action",
                max_length=20,
            ),
        ),
        migrations.AddIndex(
            model_name="moderationauditlog",
            index=models.Index(
                fields=["action_type", "-timestamp"],
                name="forum_moder_action__32bd31_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="moderationauditlog",
            index=models.Index(
                fields=["source", "-timestamp"], name="forum_moder_source_cf1224_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="moderationauditlog",
            index=models.Index(
                fields=["target_user", "-timestamp"],
                name="forum_moder_target__cadf75_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="moderationauditlog",
            index=models.Index(
                fields=["original_author", "-timestamp"],
                name="forum_moder_origina_6bb4d3_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="moderationauditlog",
            index=models.Index(
                fields=["moderator", "-timestamp"],
                name="forum_moder_moderat_2c467c_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="moderationauditlog",
            index=models.Index(
                fields=["course_id", "-timestamp"],
                name="forum_moder_course__9cbd6e_idx",
            ),
        ),
        migrations.RunPython(
            populate_source_with_ai,
            reverse_populate_source,
        ),
    ]
