"""Backend module for forum."""

from forum.backends.mysql.api import MySQLBackend


def get_backend(
    course_id: str | None = None,
) -> "type[MySQLBackend]":
    """Return the MySQL backend."""
    return MySQLBackend
