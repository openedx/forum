"""
Init file for tests.
"""

import logging

import pytest

from forum.backends.mysql.api import MySQLBackend as patched_mysql_backend

log = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def mock_elasticsearch_document_backend() -> None:
    """Mock again the mocked backend to restore the actual backend."""


@pytest.fixture(autouse=True)
def mock_elasticsearch_index_backend() -> None:
    """Mock again the mocked backend to restore the actual backend."""


@pytest.fixture(name="user_data")
def create_test_user() -> tuple[str, str]:
    """Create a user."""
    backend = patched_mysql_backend()

    user_id = "1"
    username = "test_user"
    backend.find_or_create_user(user_id, username=username)
    return user_id, username
