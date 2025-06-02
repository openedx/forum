"""
Meilisearch end-to-end tests.
"""

import typing as t

from django.test import override_settings
import pytest

from forum.backends.mysql.api import MySQLBackend as patched_mysql_backend
import forum.search.meilisearch

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def configure_meilisearch_search_backend() -> t.Generator[t.Any, t.Any, t.Any]:
    """Configure Django to use Meilisearch as a search backend."""
    with override_settings(
        FORUM_SEARCH_BACKEND="forum.search.meilisearch.MeilisearchBackend"
    ):
        yield


@pytest.fixture(autouse=True)
def meilisearch_cleanup() -> None:
    """
    Cleanup all Meilisearch indexes after each test.
    """
    client = forum.search.meilisearch.MeilisearchIndexBackend().meilisearch_client
    for index in client.get_indexes()["results"]:
        task_info = client.delete_index(index.uid)
        client.wait_for_task(task_info.task_uid, timeout_in_ms=5000)


def test_initialize_indexes() -> None:
    index_backend = forum.search.meilisearch.MeilisearchIndexBackend()
    index_backend.initialize_indices()
    indexes = sorted(
        [r.uid for r in index_backend.meilisearch_client.get_indexes()["results"]]
    )
    assert [
        "comment_threads",
        "comments",
    ] == indexes


def test_insert_document(user_data: tuple[str, str]) -> None:
    index_backend = forum.search.meilisearch.MeilisearchIndexBackend()
    index_backend.initialize_indices()

    backend = patched_mysql_backend()
    user_id, _ = user_data
    comment_thread_id = backend.create_thread(
        {
            "title": "title",
            "body": "Hello World!",
            "pinned": False,
            "author_id": user_id,
            "course_id": "course-v1:Arbisoft+SE002+2024_S2",
            "commentable_id": "66b4e0440dead7001deb948b",
            "author_username": "Faraz",
        }
    )

    thread_backend = forum.search.meilisearch.MeilisearchThreadSearchBackend()
    index_backend.refresh_indices()
    thread_ids = thread_backend.get_thread_ids("course", [], "hello")

    assert [comment_thread_id] == thread_ids
