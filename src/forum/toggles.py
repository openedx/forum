"""Forum v2 feature toggles."""

# pylint: disable=E0401
from openedx.core.djangoapps.waffle_utils import CourseWaffleFlag  # type: ignore[import-not-found]

DISCUSSION_WAFFLE_FLAG_NAMESPACE = "discussions"

# .. toggle_name: discussions.enable_ai_moderation
# .. toggle_implementation: CourseWaffleFlag
# .. toggle_default: False
# .. toggle_description: Waffle flag to enable AI moderation for discussions.
# .. toggle_use_cases: temporary, open_edx
# .. toggle_creation_date: 2025-10-29
# .. toggle_target_removal_date: 2026-06-29
ENABLE_AI_MODERATION = CourseWaffleFlag(
    f"{DISCUSSION_WAFFLE_FLAG_NAMESPACE}.enable_ai_moderation", __name__
)

# .. toggle_name: discussions.enable_ai_auto_delete_spam
# .. toggle_implementation: CourseWaffleFlag
# .. toggle_default: False
# .. toggle_description: Waffle flag to enable AI auto delete spam for discussions.
# .. toggle_use_cases: temporary, open_edx
# .. toggle_creation_date: 2026-02-05
# .. toggle_target_removal_date: 2026-06-29
ENABLE_AI_AUTO_DELETE_SPAM = CourseWaffleFlag(
    f"{DISCUSSION_WAFFLE_FLAG_NAMESPACE}.enable_ai_auto_delete_spam", __name__
)


def is_ai_auto_delete_spam_enabled(course_key):  # type: ignore[no-untyped-def]
    """
    Check if AI auto delete spam is enabled for the given course.
    """
    return ENABLE_AI_AUTO_DELETE_SPAM.is_enabled(course_key)


def is_ai_moderation_enabled(course_key):  # type: ignore[no-untyped-def]
    """
    Check if AI moderation is enabled for the given course.
    """
    return ENABLE_AI_MODERATION.is_enabled(course_key)
