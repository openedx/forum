"""
Init file for tests.
"""

from typing import Any, Generator
from unittest.mock import patch

import mongomock
import pytest
from django.contrib.auth.models import User  # pylint: disable=E5142
from pymongo import MongoClient
from pymongo.database import Database

from forum.backends.mysql.api import MySQLBackend
from test_utils.client import APIClient
from test_utils.mock_es_backend import (
    MockElasticsearchIndexBackend,
    MockElasticsearchDocumentBackend,
)


# Kept clear of MySQLBackend.generate_id()'s 1..1_000_000 range so the service
# account can never collide with a user a test invents.
SERVICE_USER_ID = 9_000_001


@pytest.fixture(name="api_client")
def fixture_api_client(db: Any) -> APIClient:  # pylint: disable=unused-argument
    """
    Create an API client authenticated as a trusted backend service.

    The forum HTTP API is service-to-service: it reads the acting user from a
    ``user_id`` parameter, so the caller is what gets authenticated. Tests
    therefore speak to it as a staff service account, the same way a real
    caller would. ``tests/test_permissions.py`` covers the unauthenticated and
    non-staff cases.
    """
    client = APIClient()
    service_user = User.objects.create(
        pk=SERVICE_USER_ID, username="forum-service", is_staff=True
    )
    client.force_login(service_user)
    return client


@pytest.fixture(autouse=True)
def mock_elasticsearch_document_backend() -> Generator[Any, Any, Any]:
    """Mock the dummy elastic search."""
    with patch(
        "forum.search.es.ElasticsearchBackend.DOCUMENT_SEARCH_CLASS",
        MockElasticsearchDocumentBackend,
    ):
        yield


@pytest.fixture(autouse=True)
def mock_elasticsearch_index_backend() -> Generator[Any, Any, Any]:
    """Mock the dummy elastic search."""
    with patch(
        "forum.search.es.ElasticsearchBackend.INDEX_SEARCH_CLASS",
        MockElasticsearchIndexBackend,
    ):
        yield


@pytest.fixture
def patched_get_backend() -> type[MySQLBackend]:
    """Return MySQLBackend for tests."""
    return MySQLBackend


@pytest.fixture(name="patched_mongodb")
def patch_mongo_migration_database(monkeypatch: pytest.MonkeyPatch) -> Database[Any]:
    """Mock default mongodb database for tests."""
    client: MongoClient[Any] = mongomock.MongoClient()
    db = client["test_forum_db"]
    monkeypatch.setattr(
        "forum.management.commands.forum_migrate_course_from_mongodb_to_mysql.get_database",
        lambda *args: db,
    )
    monkeypatch.setattr(
        "forum.management.commands.forum_delete_course_from_mongodb.get_database",
        lambda *args: db,
    )
    monkeypatch.setattr(
        "forum.mongo.get_database",
        lambda *args: db,
    )
    return db
