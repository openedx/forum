"""
AI Moderation utilities for forum content.
"""

import hashlib
import logging
from typing import Any, Dict, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
from django.utils import timezone
from django.utils.module_loading import import_string
from opaque_keys.edx.keys import CourseKey
from rest_framework.serializers import ValidationError

from forum.ai_moderation.backends.base import (
    SPAM_CLASSIFICATIONS,
    BaseModerationBackend,
    CLASSIFICATION_NOT_SPAM,
)
from forum.ai_moderation.defaults import (
    DEFAULT_FLAGGED_CACHE_PREFIX,
    DEFAULT_FLAGGED_CACHE_TTL,
    DEFAULT_REASONING,
)
from forum.backends.mysql.models import ModerationAuditLog
from forum.utils import ForumV2RequestError

User = get_user_model()
log = logging.getLogger(__name__)


def _get_author_from_content(content_instance: Any) -> Any:
    """
    Get author from content instance.

    Args:
        content_instance: Dict containing all content related data
    Returns:
        Author object or user ID
    """
    author_id = content_instance.get("author_id")
    if author_id:
        try:
            return User.objects.get(pk=author_id)
        except (User.DoesNotExist, ValueError, TypeError):
            # If we can't get the User object, return the ID as fallback
            return author_id
    return None


def create_moderation_audit_log(
    content_instance: Any,
    moderation_result: Dict[str, Any],
    actions_taken: list[str],
    original_author: Any,
) -> None:
    """
    Create an audit log entry for AI moderation decisions.

    Only creates audit logs for spam content to reduce database load.

    Args:
        content_instance: The content object (Thread or Comment, dict or model)
        moderation_result: Full result from AI moderation
        actions_taken: List of actions taken (e.g., ['flagged'], ['flagged', 'soft_deleted'])
        original_author: User who created the content
    """
    if original_author is None:
        original_author = _get_author_from_content(content_instance)

    content_id = str(content_instance.get("_id"))
    content_body = content_instance.get("body", "")

    enhanced_moderation_result = moderation_result.copy()
    enhanced_moderation_result.update(
        {
            "content_id": content_id,
            "metadata": {
                "_id": content_id,
                "title": content_instance.get("title", ""),
                "body": (
                    content_instance.get("body", "")[:200] + "..."
                    if len(content_instance.get("body", "")) > 200
                    else content_instance.get("body", "")
                ),
                "course_id": content_instance.get("course_id", ""),
                "created_at": str(content_instance.get("created_at", "")),
            },
        }
    )

    try:
        audit_log = ModerationAuditLog(
            timestamp=timezone.now(),
            body=content_body,  # Store full body content
            classifier_output=enhanced_moderation_result,
            reasoning=moderation_result.get("reasoning", DEFAULT_REASONING),
            classification=moderation_result.get("classification", "spam"),
            actions_taken=actions_taken,
            confidence_score=moderation_result.get("confidence_score"),
            original_author=original_author,
        )
        audit_log.save()
    except (ValueError, TypeError, AttributeError) as db_error:
        log.error(f"Failed to create database audit log: {db_error}")


class AIModerationService:
    """
    Service for AI-based content moderation.

    Waffle Flag "discussions.enable_ai_moderation" controls whether AI moderation is active.

    Content is classified by the moderation backend named in the
    AI_MODERATION_BACKEND setting. There is no default: forum defines the
    interface and leaves the choice of provider to the deployment. This service
    is provider agnostic -- everything it does with a verdict, from caching to
    flagging to soft deletion to audit logging, is the same whichever backend
    produced it.
    """

    def __init__(self) -> None:
        """Initialize the AI moderation service."""
        self._moderation_backend: Optional[BaseModerationBackend] = None
        self._moderation_backend_path: Optional[str] = None

    @property
    def ai_moderation_user_id(self) -> Optional[Any]:
        """User the moderation actions are attributed to."""
        return getattr(settings, "AI_MODERATION_USER_ID", None)

    @property
    def flagged_cache_ttl(self) -> int:
        """How long a spam verdict stays cached, in seconds."""
        return getattr(
            settings, "AI_MODERATION_FLAGGED_CACHE_TTL", DEFAULT_FLAGGED_CACHE_TTL
        )

    @property
    def flagged_cache_prefix(self) -> str:
        """Key prefix for cached spam verdicts."""
        return getattr(
            settings, "AI_MODERATION_FLAGGED_CACHE_PREFIX", DEFAULT_FLAGGED_CACHE_PREFIX
        )

    @property
    def moderation_backend_path(self) -> Optional[str]:
        """Dotted path of the configured moderation backend, if one is configured."""
        return getattr(settings, "AI_MODERATION_BACKEND", None)

    @property
    def moderation_backend(self) -> BaseModerationBackend:
        """
        The configured moderation backend.

        Loaded on first use rather than in __init__ so that the module level
        service instance does not freeze the setting at import time, and cached
        until the configured path changes.

        Raises:
            ImproperlyConfigured: if AI_MODERATION_BACKEND is unset, or does not
                name a usable BaseModerationBackend.
        """
        backend_path = self.moderation_backend_path
        if not backend_path:
            raise ImproperlyConfigured(
                "AI_MODERATION_BACKEND is not configured. Forum provides the "
                "moderation interface but no provider: set this to the dotted path "
                "of a BaseModerationBackend subclass."
            )
        if (
            self._moderation_backend is None
            or self._moderation_backend_path != backend_path
        ):
            self._moderation_backend = self._load_moderation_backend(backend_path)
            self._moderation_backend_path = backend_path
        return self._moderation_backend

    @staticmethod
    def _load_moderation_backend(backend_path: str) -> BaseModerationBackend:
        """Import and instantiate the moderation backend at ``backend_path``."""
        try:
            backend_class = import_string(backend_path)
        except ImportError as e:
            raise ImproperlyConfigured(
                f"AI_MODERATION_BACKEND '{backend_path}' could not be imported: {e}"
            ) from e

        backend = backend_class()
        if not isinstance(backend, BaseModerationBackend):
            raise ImproperlyConfigured(
                f"AI_MODERATION_BACKEND '{backend_path}' is not a subclass of "
                f"{BaseModerationBackend.__module__}.{BaseModerationBackend.__name__}"
            )
        return backend

    def _classify(self, content: str) -> Optional[Dict[str, Any]]:
        """
        Ask the configured backend to classify content.

        Returns the moderation result, or None if the backend is unusable or
        failed. Moderation runs inline with posting, so no backend problem is
        allowed to propagate out of here.
        """
        try:
            return self.moderation_backend.classify(content)
        except ImproperlyConfigured as e:
            log.error(f"AI moderation backend is not usable: {e}")
            return None
        except Exception:  # pylint: disable=broad-except
            log.exception(
                f"AI moderation backend '{self.moderation_backend_path}' "
                f"raised an unexpected error"
            )
            return None

    def _cache_key_for_content(self, content: str) -> str:
        """Return the cache key for a given message content."""
        normalized = (content or "").strip()
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return f"{self.flagged_cache_prefix}:{digest}"

    def _get_cached_flagged_result(self, content: str) -> Optional[Dict[str, Any]]:
        """Return cached moderation result for flagged content, if present."""
        try:
            cached = cache.get(self._cache_key_for_content(content))
        except Exception:  # pylint: disable=broad-except, no-else-return
            log.exception("AI moderation cache read failed")
            return None
        return cached if isinstance(cached, dict) else None

    def _set_cached_flagged_result(
        self, content: str, moderation_result: Dict[str, Any]
    ) -> None:
        """Store moderation result for flagged content in cache."""
        try:
            cache.set(
                self._cache_key_for_content(content),
                moderation_result,
                timeout=self.flagged_cache_ttl,
            )
        except Exception:  # pylint: disable=broad-except
            log.exception("AI moderation cache write failed")

    def moderate_and_flag_content(
        self,
        content: str,
        content_instance: Any,
        course_id: Optional[str] = None,
        backend: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Moderate content and flag as spam and flag abuse if detected.

        Args:
            content: The text content to check
            content_instance: The content model instance (Thread or Comment)
            course_id: Optional course ID for waffle flag checking
            backend: Forum storage backend used for the database operations.
                This is not the AI moderation backend, which is chosen by the
                AI_MODERATION_BACKEND setting.

        Returns:
            Dictionary with moderation results and actions taken
        """
        result = {
            "is_spam": False,
            "reasoning": "AI moderation disabled or unavailable",
            "classification": CLASSIFICATION_NOT_SPAM,
            "actions_taken": ["no_action"],
            "flagged": False,
        }
        # Check if AI moderation is enabled
        # pylint: disable=import-outside-toplevel
        from forum.toggles import (
            is_ai_moderation_enabled,
            is_ai_auto_delete_spam_enabled,
        )

        course_key = CourseKey.from_string(course_id) if course_id else None
        if not is_ai_moderation_enabled(course_key):  # type: ignore[no-untyped-call]
            return result

        # If we've already flagged this exact content before, reuse the cached result
        moderation_result = self._get_cached_flagged_result(content)
        if moderation_result is None:
            moderation_result = self._classify(content)

        if moderation_result is None:
            result["reasoning"] = "AI moderation API failed"
            log.warning("AI moderation API failed")
            return result

        classification = moderation_result.get(
            "classification", CLASSIFICATION_NOT_SPAM
        )
        reasoning = moderation_result.get("reasoning", DEFAULT_REASONING)
        is_spam = classification in SPAM_CLASSIFICATIONS

        # Cache only flagged (spam) results to avoid repeated classifier calls
        if is_spam:
            self._set_cached_flagged_result(content, moderation_result)

        result.update(
            {
                "is_spam": is_spam,
                "reasoning": reasoning,
                "classification": classification,
                "moderation_result": moderation_result,
            }
        )

        if is_spam:
            # Flag content as spam and abuse first
            try:
                content_instance["is_spam"] = True

                self._mark_as_spam_and_moderate(content_instance, backend)
                result["actions_taken"] = ["flagged"]
                result["flagged"] = True
            except ImproperlyConfigured as e:
                log.error(f"Cannot act on AI moderation verdict: {e}")
                result["actions_taken"] = ["no_action"]
            except (AttributeError, ValueError, TypeError) as e:
                log.error(f"Failed to flag content as spam: {e}")
                result["actions_taken"] = ["no_action"]

            # Only attempt deletion if flagging succeeded
            if is_ai_auto_delete_spam_enabled(course_key) and result["flagged"]:  # type: ignore[no-untyped-call]
                try:
                    self._delete_content(content_instance)
                    result["actions_taken"] = result["actions_taken"] + ["soft_deleted"]  # type: ignore[operator]
                except (ForumV2RequestError, ObjectDoesNotExist, ValidationError) as e:
                    log.error(f"Failed to delete content after flagging: {e}")
        else:
            result["actions_taken"] = ["no_action"]

        # Only create audit log for spam content (or API failures, handled above)
        if is_spam:
            create_moderation_audit_log(
                content_instance,
                moderation_result,
                result["actions_taken"],  # type: ignore[arg-type]
                _get_author_from_content(content_instance),
            )
        return result

    def _mark_as_spam_and_moderate(self, content_instance: Any, backend: Any) -> None:
        """Flag content as abuse using backend methods."""
        content_id = str(content_instance.get("_id"))
        content_type = str(content_instance.get("_type"))
        extra_data = {
            "entity_type": (
                "CommentThread" if content_type == "CommentThread" else "Comment"
            )
        }
        if not self.ai_moderation_user_id:
            raise ImproperlyConfigured(
                "AI_MODERATION_USER_ID setting is not configured, so there is no user "
                "to attribute AI moderation actions to."
            )
        backend.flag_content_as_spam(content_type, content_id)
        backend.flag_as_abuse(str(self.ai_moderation_user_id), content_id, **extra_data)

    def _delete_content(self, content_instance: Any) -> None:
        """
        Delete content using API layer delete functions.

        Uses the API layer which handles all business logic including:
        - Content validation
        - Deletion
        - Stats updates
        - Subscription cleanup (for threads)
        - Anonymous content handling

        Args:
            content_instance: Dict containing content data including _id, _type, and course_id
        """
        # Import here to avoid circular dependency (api modules import from ai_moderation)
        # pylint: disable=import-outside-toplevel,cyclic-import
        from forum.api.comments import delete_comment
        from forum.api.threads import delete_thread

        content_id = str(content_instance.get("_id"))
        content_type = str(content_instance.get("_type"))
        course_id = content_instance.get("course_id")

        # Use API layer functions which handle all business logic
        # Exceptions propagate to caller for proper error handling
        if content_type == "CommentThread":
            delete_thread(content_id, course_id=course_id)
            log.info(f"AI Moderation Deleted CommentThread: {content_id}")
        elif content_type == "Comment":
            delete_comment(content_id, course_id=course_id)
            log.info(f"AI Moderation Deleted Comment: {content_id}")


# Global instance
ai_moderation_service = AIModerationService()


def moderate_and_flag_spam(
    content: str,
    content_instance: Any,
    course_id: Optional[str] = None,
    backend: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Moderate content and flag as spam if detected.

    Args:
        content: The text content to moderate
        content_instance: The content model instance
        course_id: Optional course ID for waffle flag checking
        backend: Backend instance for database operations

    Returns:
        Dictionary with moderation results and actions taken

    TODO:-
     - Add content check for images
    """
    return ai_moderation_service.moderate_and_flag_content(
        content, content_instance, course_id, backend
    )
