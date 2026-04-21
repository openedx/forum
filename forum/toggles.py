"""Forum v2 feature toggles."""

# pylint: disable=E0401
from openedx.core.djangoapps.waffle_utils import CourseWaffleFlag  # type: ignore[import-not-found]

FORUM_V2_WAFFLE_FLAG_NAMESPACE = "forum_v2"


# .. toggle_name: forum_v2.enable_mysql_backend
# .. toggle_implementation: CourseWaffleFlag
# .. toggle_default: False
# .. toggle_description: Waffle flag to use the MySQL backend instead of Mongo backend.
# .. toggle_use_cases: temporary, open_edx
# .. toggle_creation_date: 2024-10-18
# .. toggle_target_removal_date: 2025-06-18
ENABLE_MYSQL_BACKEND = CourseWaffleFlag(
    f"{FORUM_V2_WAFFLE_FLAG_NAMESPACE}.enable_mysql_backend", __name__
)
