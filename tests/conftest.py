"""
Init file for tests.
"""

from typing import Any, Generator
from unittest.mock import patch

import mongomock
import pytest
from pymongo import MongoClient
from pymongo.database import Database

from forum.backends.mysql.api import MySQLBackend
from forum.backends.mongodb.api import MongoBackend
from test_utils.client import APIClient
from test_utils.mock_es_backend import (
    MockElasticsearchIndexBackend,
    MockElasticsearchDocumentBackend,
)


@pytest.fixture(autouse=True)
def patch_default_mongo_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock default mongodb database for tests."""
    client: MongoClient[Any] = mongomock.MongoClient()
    monkeypatch.setattr(
        "forum.backends.mongodb.base_model.MongoBaseModel.MONGODB_DATABASE",
        client["test_forum_db"],
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


@pytest.fixture(params=[MongoBackend, MySQLBackend])
def patched_get_backend(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Generator[Any, Any, Any]:
    """Return the patched get_backend function for both Mongo and MySQL backends."""
    backend_class = request.param
    monkeypatch.setattr(
        "forum.backend.is_mysql_backend_enabled",
        lambda course_id: backend_class != MongoBackend,
    )
    yield backend_class


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


@pytest.fixture(autouse=True)
def patched_mongo_backend(monkeypatch: pytest.MonkeyPatch) -> Generator[Any, Any, Any]:
    """Return the patched mongo_backend function for Mongo backend."""
    monkeypatch.setattr(
        "forum.backend.is_mysql_backend_enabled",
        lambda course_id: False,
    )
    yield MongoBackend


@pytest.fixture(autouse=True)
def patched_mysql_backend(monkeypatch: pytest.MonkeyPatch) -> Generator[Any, Any, Any]:
    """Return the patched mysql function for MySQL backend."""
    monkeypatch.setattr(
        "forum.backend.is_mysql_backend_enabled",
        lambda course_id: True,
    )
    yield MySQLBackend
