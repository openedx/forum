"""
Init file for tests.
"""

from typing import Any, Generator
from unittest.mock import patch

import mongomock
import pytest
from pymongo import MongoClient
from pymongo.database import Database

from test_utils.client import APIClient
from test_utils.mock_es_backend import (
    MockElasticsearchIndexBackend,
    MockElasticsearchDocumentBackend,
)


@pytest.fixture(name="api_client")
def fixture_api_client() -> APIClient:
    """Create an API client for testing."""
    return APIClient()


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
