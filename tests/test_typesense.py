"""
Unit tests for the typesense search backend.
"""

from unittest.mock import patch, MagicMock, Mock

import pytest
from typesense.exceptions import ObjectNotFound

from forum.search import typesense
from forum import constants


def test_quote_filter() -> None:
    """Verify quoting unsafe filter values works as expected."""
    assert typesense.quote_filter_value("foo || true") == "`foo || true`"
    assert typesense.quote_filter_value("foo` || true") == "`foo || true`"
    assert typesense.quote_filter_value("mal`formed word[,]") == "`malformed word[,]`"


def test_build_collection_name() -> None:
    assert typesense.collection_name() == "forum_unittest_prefix_forum"


def test_schemas() -> None:
    """
    A very basic test to check the schema functions don't crash.
    The contents are not checked.
    """
    assert isinstance(typesense.collection_schema(), dict)
    assert isinstance(typesense.expected_full_collection_schema(), dict)


def test_document_from_thread() -> None:
    doc_id = "MY_ID"
    data = {
        "course_id": "course-v1:OpenedX+DemoX+DemoCourse",
        "commentable_id": 4,
        "context": "course",
        "title": "My Thoughts!",
        "body": "<p><b>Thought one</b>: I like this course.</p>",
    }

    expected_document = {
        "id": "thread-MY_ID",
        "thread_id": "MY_ID",
        "course_id": "course-v1:OpenedX+DemoX+DemoCourse",
        "commentable_id": "4",
        "context": "course",
        "text": "My Thoughts!\nThought one: I like this course.",
    }

    assert typesense.document_from_thread(doc_id, data) == expected_document


def test_document_from_comment() -> None:
    doc_id = "MY_ID"
    data = {
        "course_id": "course-v1:OpenedX+DemoX+DemoCourse",
        "comment_thread_id": 6,
        "context": "course",
        "body": "<p><b>Another thought</b>: I also like this course.</p>",
    }

    expected_document = {
        "id": "comment-MY_ID",
        "thread_id": "6",
        "course_id": "course-v1:OpenedX+DemoX+DemoCourse",
        "commentable_id": "",
        "context": "course",
        "text": "Another thought: I also like this course.",
    }

    assert typesense.document_from_comment(doc_id, data) == expected_document


@patch("forum.search.typesense.get_typesense_client")
def test_search_threads(mock_get_client: Mock) -> None:
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_search = mock_client.collections[
        "forum_unittest_prefix_forum"
    ].documents.search
    mock_search.return_value = {
        "hits": [{"document": {"thread_id": "ONE"}}, {"document": {"thread_id": "TWO"}}]
    }

    backend = typesense.TypesenseThreadSearchBackend()
    assert sorted(
        backend.get_thread_ids(
            context="course",
            group_ids=[],
            search_text="thoughts",
            commentable_ids=["4", "7[`||"],
            course_id="course-v1:OpenedX+DemoX+DemoCourse",
        )
    ) == sorted(["ONE", "TWO"])

    # test build_search_paramaters() here too; important to verify it backtick escapes the values
    expected_params = {
        "q": "thoughts",
        "query_by": "text",
        "filter_by": "context:`course` && commentable_ids:[`4`, `7[||`] "
        "&& course_id:=`course-v1:OpenedX+DemoX+DemoCourse`",
        "per_page": constants.FORUM_MAX_DEEP_SEARCH_COMMENT_COUNT,
    }
    mock_search.assert_called_once_with(expected_params)

    # suggested text is not supported; always returns None
    assert backend.get_suggested_text("foo") is None


@patch("forum.search.typesense.get_typesense_client")
def test_index_comment_document(mock_get_client: Mock) -> None:
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_index = mock_client.collections["forum_unittest_prefix_forum"].documents.upsert

    doc_id = "MY_ID"
    data = {
        "course_id": "course-v1:OpenedX+DemoX+DemoCourse",
        "comment_thread_id": 6,
        "context": "course",
        "body": "<p><b>Another thought</b>: I also like this course.</p>",
    }
    expected_document = {
        "id": "comment-MY_ID",
        "thread_id": "6",
        "course_id": "course-v1:OpenedX+DemoX+DemoCourse",
        "commentable_id": "",
        "context": "course",
        "text": "Another thought: I also like this course.",
    }

    backend = typesense.TypesenseDocumentBackend()
    backend.index_document("comments", doc_id, data)
    mock_index.assert_called_once_with(expected_document)


@patch("forum.search.typesense.get_typesense_client")
def test_index_thread_document(mock_get_client: Mock) -> None:
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_index = mock_client.collections["forum_unittest_prefix_forum"].documents.upsert

    doc_id = "MY_ID"
    data = {
        "course_id": "course-v1:OpenedX+DemoX+DemoCourse",
        "commentable_id": 4,
        "context": "course",
        "title": "My Thoughts!",
        "body": "<p><b>Thought one</b>: I like this course.</p>",
    }

    expected_document = {
        "id": "thread-MY_ID",
        "thread_id": "MY_ID",
        "course_id": "course-v1:OpenedX+DemoX+DemoCourse",
        "commentable_id": "4",
        "context": "course",
        "text": "My Thoughts!\nThought one: I like this course.",
    }

    backend = typesense.TypesenseDocumentBackend()
    backend.index_document("comment_threads", doc_id, data)
    mock_index.assert_called_once_with(expected_document)


@patch("forum.search.typesense.get_typesense_client", MagicMock())
def test_index_invalid_type() -> None:
    backend = typesense.TypesenseDocumentBackend()
    with pytest.raises(NotImplementedError):
        backend.index_document("foo", "DOCID", {})


@patch("forum.search.typesense.get_typesense_client")
def test_delete_document(mock_get_client: Mock) -> None:
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_delete = (
        mock_client.collections["forum_unittest_prefix_forum"]
        .documents["comment-MYCOMMENTID"]
        .delete
    )

    backend = typesense.TypesenseDocumentBackend()
    backend.delete_document("comments", "MYCOMMENTID")
    mock_delete.assert_called_once()


@patch("forum.search.typesense.get_typesense_client")
def test_init_indexes_already_exist(mock_get_client: Mock) -> None:
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_collection = mock_client.collections["forum_unittest_prefix_forum"]
    mock_collection.retrieve.return_value = {"data": "irrelevant but index exists"}

    backend = typesense.TypesenseIndexBackend()
    backend.initialize_indices()

    mock_collection.delete.assert_not_called()
    mock_client.collections.create.assert_not_called()


@patch("forum.search.typesense.get_typesense_client")
def test_init_indexes_already_exist_force(mock_get_client: Mock) -> None:
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_collection = mock_client.collections["forum_unittest_prefix_forum"]
    mock_collection.retrieve.return_value = {"data": "irrelevant but index exists"}

    backend = typesense.TypesenseIndexBackend()
    backend.initialize_indices(force_new_index=True)

    mock_collection.delete.assert_called_once()
    mock_client.collections.create.assert_called_once()


@patch("forum.search.typesense.get_typesense_client")
def test_init_indexes_does_not_exist(mock_get_client: Mock) -> None:
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_collection = mock_client.collections["forum_unittest_prefix_forum"]
    mock_collection.retrieve.side_effect = ObjectNotFound

    backend = typesense.TypesenseIndexBackend()
    backend.initialize_indices()

    mock_collection.delete.assert_not_called()
    mock_client.collections.create.assert_called_once()


def test_index_noops() -> None:
    """
    These methods should have no effect and require no mocks.

    They are noops on the Typesense backend.
    """
    backend = typesense.TypesenseIndexBackend()
    backend.refresh_indices()
    assert backend.delete_unused_indices() == 0


def test_get_client() -> None:
    client1 = typesense.get_typesense_client()
    client2 = typesense.get_typesense_client()

    assert client1 is client2
    assert client1.config.api_key == "example-typesense-api-key"
