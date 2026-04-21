"""Backend module for forum."""

from forum.backends.mysql.api import MySQLBackend


def get_backend(  # pylint: disable=unused-argument
    course_id: str | None = None,
) -> "type[MySQLBackend]":
    """Return the MySQL backend."""
    return MySQLBackend
