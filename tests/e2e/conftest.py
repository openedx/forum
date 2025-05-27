"""
Init file for tests.
"""

import logging
import time
import typing as t

import pytest
from pymongo.errors import ServerSelectionTimeoutError

from forum.mongo import get_database
from test_utils.client import APIClient

log = logging.getLogger(__name__)

MONGO_TIMEOUT = 60
MONGO_SLEEP_INTERVAL = 5


@pytest.fixture(name="api_client")
def fixture_api_client() -> APIClient:
    """Create an API client for testing."""
    return APIClient()


def wait_for_mongodb() -> None:
    """Wait for MongoDB to start."""
    db = get_database()
    timeout = MONGO_TIMEOUT
    while timeout > 0:
        try:
            db.command("ping")
            log.info("Connected to the MongoDB")
            return
        except ServerSelectionTimeoutError:
            log.info("Waiting for mongodb to connect")
            time.sleep(MONGO_SLEEP_INTERVAL)
            timeout -= MONGO_SLEEP_INTERVAL
    raise Exception("Elasticsearch did not start in time")


@pytest.fixture(autouse=True)
def mongo_cleanup() -> None:
    """Cleanup MongoDB collections after each test."""
    wait_for_mongodb()
    db = get_database()

    # Clean up collections after each test case
    for collection_name in db.list_collection_names():
        db.drop_collection(collection_name)


@pytest.fixture(autouse=True)
def patch_default_mongo_database() -> None:
    """Override the patch statement."""


@pytest.fixture(autouse=True)
def mock_elasticsearch_document_backend() -> None:
    """Mock again the mocked backend to restore the actual backend."""


@pytest.fixture(autouse=True)
def mock_elasticsearch_index_backend() -> None:
    """Mock again the mocked backend to restore the actual backend."""


@pytest.fixture(name="user_data")
def create_test_user(patched_mysql_backend: t.Any) -> tuple[str, str]:
    """Create a user."""
    backend = patched_mysql_backend()

    user_id = "1"
    username = "test_user"
    backend.find_or_create_user(user_id, username=username)
    return user_id, username
