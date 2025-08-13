"""Backend module for forum."""

from typing import Callable, Optional

from forum.backends.mongodb.api import MongoBackend
from forum.backends.mysql.api import MySQLBackend


def is_mysql_backend_enabled(course_id: str | None) -> bool:
    """
    Return True if mysql backend is enabled for the course.
    """
    try:
        # pylint: disable=import-outside-toplevel
        from forum.toggles import ENABLE_MYSQL_BACKEND
        from opaque_keys import InvalidKeyError
        from opaque_keys.edx.keys import CourseKey
    except ImportError:
        return True

    course_key: "CourseKey" | None = None
    if isinstance(course_id, CourseKey):
        course_key = course_id  # type: ignore[unreachable]
    elif isinstance(course_id, str):
        try:
            course_key = CourseKey.from_string(course_id)
        except InvalidKeyError:
            pass

    return ENABLE_MYSQL_BACKEND.is_enabled(course_key)


def get_backend(
    course_id: Optional[str] = None,
) -> Callable[[], MongoBackend | MySQLBackend]:
    """Return a factory function that lazily loads the backend API based on course_id."""

    def _get_backend() -> MongoBackend | MySQLBackend:
        if is_mysql_backend_enabled(course_id):
            return MySQLBackend()
        return MongoBackend()

    return _get_backend
