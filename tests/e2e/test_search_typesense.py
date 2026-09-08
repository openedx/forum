"""
Typesense end-to-end tests.

These run against a real Typesense server, which the mocked unit tests in
tests/test_typesense.py cannot substitute for: both of the bugs these tests
cover were rejections from the server, invisible to a mock.
"""

import typing as t

from django.test import override_settings
import pytest

from forum.search import typesense

pytestmark = pytest.mark.django_db

COURSE_ID = "course-v1:Arbisoft+SE002+2024_S2"


@pytest.fixture(autouse=True)
def configure_typesense_search_backend() -> t.Generator[t.Any, t.Any, t.Any]:
    """Configure Django to use Typesense as a search backend."""
    with override_settings(
        FORUM_SEARCH_BACKEND="forum.search.typesense.TypesenseBackend"
    ):
        yield


@pytest.fixture(autouse=True)
def typesense_cleanup() -> None:
    """Start each test from an empty collection."""
    typesense.TypesenseIndexBackend().initialize_indices(force_new_index=True)


def index_threads(threads: list[dict[str, t.Any]]) -> None:
    """Bulk-index thread documents, then confirm Typesense accepted every one."""
    client = typesense.get_typesense_client()
    response = client.collections[typesense.collection_name()].documents.import_(
        [typesense.document_from_thread(thread["id"], thread) for thread in threads],
        {"action": "upsert"},
    )
    assert all(result["success"] for result in response), response


def test_initialize_indices() -> None:
    index_backend = typesense.TypesenseIndexBackend()
    index_backend.initialize_indices()
    # raises AssertionError if the collection on the server does not match the schema
    index_backend.validate_indices()


def test_insert_document(
    patched_get_backend: t.Any, user_data: tuple[str, str]
) -> None:
    index_backend = typesense.TypesenseIndexBackend()
    index_backend.initialize_indices()

    backend = patched_get_backend()
    user_id, _ = user_data
    comment_thread_id = backend.create_thread(
        {
            "title": "title",
            "body": "Hello World!",
            "pinned": False,
            "author_id": user_id,
            "course_id": COURSE_ID,
            "commentable_id": "66b4e0440dead7001deb948b",
            "author_username": "Faraz",
        }
    )

    index_backend.refresh_indices()
    thread_backend = typesense.TypesenseThreadSearchBackend()
    assert thread_backend.get_thread_ids("course", [], "hello") == [comment_thread_id]


def test_search_filtered_by_commentable_id() -> None:
    """
    Scoping a search to discussion topics has to filter on the field name the
    collection actually declares, or Typesense rejects the search with HTTP 400.
    """
    index_threads(
        [
            {
                "id": index,
                "course_id": COURSE_ID,
                "commentable_id": commentable_id,
                "context": "course",
                "title": "searchable thread",
                "body": "<p>Hello World!</p>",
            }
            for index, commentable_id in enumerate(["week-1", "week-1", "week-2"])
        ]
    )

    thread_backend = typesense.TypesenseThreadSearchBackend()
    assert sorted(
        thread_backend.get_thread_ids(
            "course",
            [],
            "searchable",
            commentable_ids=["week-1"],
            course_id=COURSE_ID,
        )
    ) == ["0", "1"]


def test_deep_search_past_the_per_page_limit() -> None:
    """
    A deep search asks for FORUM_MAX_DEEP_SEARCH_COMMENT_COUNT hits, which is far
    more than Typesense will return in one page — it rejects any per_page above
    250 with HTTP 422. All of the matches still have to come back.
    """
    thread_count = typesense.TYPESENSE_MAX_PER_PAGE * 2 + 1
    index_threads(
        [
            {
                "id": index,
                "course_id": COURSE_ID,
                "commentable_id": "week-1",
                "context": "course",
                "title": "searchable thread",
                "body": f"<p>Hello World {index}!</p>",
            }
            for index in range(thread_count)
        ]
    )

    thread_backend = typesense.TypesenseThreadSearchBackend()
    thread_ids = thread_backend.get_thread_ids(
        "course", [], "searchable", commentable_ids=["week-1"], course_id=COURSE_ID
    )
    assert len(thread_ids) == thread_count
