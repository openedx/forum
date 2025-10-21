"""
Typesense backend for searching comments and threads.
"""

from typing import Any, Optional, cast

from bs4 import BeautifulSoup
from django.conf import settings
from django.core.paginator import Paginator

from typesense.client import Client
from typesense.types.collection import CollectionCreateSchema
from typesense.types.document import DocumentSchema, SearchParameters
from typesense.exceptions import ObjectNotFound

from forum.backends.mysql.models import Comment, CommentThread
from forum.constants import FORUM_MAX_DEEP_SEARCH_COMMENT_COUNT
from forum.search.base import (
    BaseDocumentSearchBackend,
    BaseIndexSearchBackend,
    BaseSearchBackend,
    BaseThreadSearchBackend,
)

_TYPESENSE_CLIENT: Client | None = None


def get_typesense_client() -> Client:
    """
    Return a singleton Typesense client instance.
    """
    global _TYPESENSE_CLIENT
    if _TYPESENSE_CLIENT is None:
        _TYPESENSE_CLIENT = Client(
            {
                "api_key": settings.TYPESENSE_API_KEY,
                "nodes": settings.TYPESENSE_URLS,
            }
        )
    return _TYPESENSE_CLIENT


def quote_filter_value(value: str) -> str:
    """
    Sanitize and safely quote a value for use in a Typesense filter.

    https://typesense.org/docs/guide/tips-for-filtering.html#escaping-special-characters
    """
    return "`" + value.replace("`", "") + "`"


def collection_name() -> str:
    """
    Generate the collection name to use in Typesense.
    """
    return settings.TYPESENSE_COLLECTION_PREFIX + "forum"


def collection_schema() -> CollectionCreateSchema:
    """
    The schema to use for creating the collection.
    """
    return {
        "name": collection_name(),
        # NOTE: there's always an implicit "id" field
        "fields": [
            {"name": "thread_id", "type": "string"},
            {"name": "course_id", "type": "string"},
            {"name": "commentable_id", "type": "string"},
            {"name": "context", "type": "string"},
            {"name": "text", "type": "string"},
        ],
    }


def expected_full_collection_schema() -> dict[str, Any]:
    """
    What is expected to be the full collection schema.

    Use this to validate the actual schema from the server.
    Note that Typesense may add new keys to the schema;
    this is ok, and validation should still pass.
    """
    field_defaults = {
        "facet": False,
        "index": True,
        "infix": False,
        "locale": "",
        "optional": False,
        "sort": False,
        "stem": False,
        "stem_dictionary": "",
        "store": True,
        "type": "string",
    }
    return {
        "default_sorting_field": "",
        "enable_nested_fields": False,
        "fields": [
            {
                **field_defaults,
                "name": "thread_id",
            },
            {
                **field_defaults,
                "name": "course_id",
            },
            {
                **field_defaults,
                "name": "commentable_id",
            },
            {
                **field_defaults,
                "name": "context",
            },
            {
                **field_defaults,
                "name": "text",
            },
        ],
        "name": collection_name(),
        "symbols_to_index": [],
        "token_separators": [],
    }


def document_from_thread(doc_id: str | int, data: dict[str, Any]) -> DocumentSchema:
    """
    Build a Typesense document from a thread's data.
    """
    return {
        "id": f"thread-{doc_id}",
        "thread_id": str(doc_id),
        "course_id": str(data.get("course_id", "")),
        "commentable_id": str(data.get("commentable_id", "")),
        "context": str(data.get("context", "")),
        "text": "{}\n{}".format(
            str(data.get("title", "")),
            (
                BeautifulSoup(data["body"], features="html.parser").get_text()
                if data.get("body")
                else ""
            ),
        ),
    }


def document_from_comment(doc_id: str | int, data: dict[str, Any]) -> DocumentSchema:
    """
    Build a Typesense document from a comment's data.
    """
    # NOTE: Comments have no commentable_id or title, and the context is hardcoded to "course".
    return {
        "id": f"comment-{doc_id}",
        "thread_id": str(data.get("comment_thread_id", "")),
        "course_id": str(data.get("course_id", "")),
        "commentable_id": "",
        "context": str(data.get("context", "")),
        "text": (
            BeautifulSoup(data["body"], features="html.parser").get_text()
            if data.get("body")
            else ""
        ),
    }


def build_search_parameters(
    *,
    search_text: str,
    course_id: str | None,
    context: str,
    commentable_ids: list[str] | None,
) -> SearchParameters:
    """
    Build Typesense search parameters for searching the index.
    """
    # `context` is always a single word,
    # so we can gain performance without losing accuracy by using the faster `:` (non-exact) operator.
    # See https://typesense.org/docs/29.0/api/search.html#filter-parameters for more information.
    filters = [f"context:{quote_filter_value(context)}"]

    if commentable_ids:
        safe_ids = ", ".join(quote_filter_value(value) for value in commentable_ids)
        filters.append(f"commentable_ids:[{safe_ids}]")

    if course_id:
        filters.append(f"course_id:={quote_filter_value(course_id)}")

    return {
        "q": search_text,
        "query_by": "text",
        "filter_by": " && ".join(filters),
        "per_page": FORUM_MAX_DEEP_SEARCH_COMMENT_COUNT,
    }


class TypesenseDocumentBackend(BaseDocumentSearchBackend):
    """
    Document backend implementation for Typesense.
    """

    def index_document(
        self, index_name: str, doc_id: str | int, document: dict[str, Any]
    ) -> None:
        """
        Index a document in Typesense.
        """
        client = get_typesense_client()

        if index_name == "comments":
            typesense_document = document_from_comment(doc_id, document)
        elif index_name == "comment_threads":
            typesense_document = document_from_thread(doc_id, document)
        else:
            raise NotImplementedError(f"unknown index name: {index_name}")

        client.collections[collection_name()].documents.upsert(typesense_document)

    def update_document(
        self, index_name: str, doc_id: str | int, update_data: dict[str, Any]
    ) -> None:
        """
        Same operation as index_document, because upsert is used.
        """
        return self.index_document(index_name, doc_id, update_data)

    def delete_document(self, index_name: str, doc_id: str | int) -> None:
        """
        Delete a document from Typesense.
        """
        client = get_typesense_client()
        if index_name == "comments":
            typesense_doc_id = f"comment-{doc_id}"
        elif index_name == "comment_threads":
            typesense_doc_id = f"thread-{doc_id}"
        else:
            raise NotImplementedError(f"unknown index name: {index_name}")

        client.collections[collection_name()].documents[typesense_doc_id].delete(
            delete_parameters={"ignore_not_found": True},
        )


class TypesenseIndexBackend(BaseIndexSearchBackend):
    """
    Manage indexes for the Typesense backend.

    Typesense calls these "collections". https://typesense.org/docs/29.0/api/collections.html
    """

    def initialize_indices(self, force_new_index: bool = False) -> None:
        """
        Initialize the indices in Typesense.

        If force_new_index is True, the indexes will be dropped before being recreated.
        """
        client = get_typesense_client()
        name = collection_name()
        exists: bool = True
        try:
            client.collections[name].retrieve()
        except ObjectNotFound:
            exists = False

        if force_new_index and exists:
            client.collections[name].delete()

        if force_new_index or not exists:
            client.collections.create(collection_schema())

    def rebuild_indices(
        self, batch_size: int = 500, extra_catchup_minutes: int = 5
    ) -> None:
        """
        Reindex everything in Typesense

        The Typesense collections are dropped and recreated,
        and data is reindexed from the MySQL database.

        Only MySQL-backed instances are supported.
        Note that the `extra_catchup_minutes` argument is ignored.
        """
        client = get_typesense_client()
        self.initialize_indices(force_new_index=True)

        for model, document_builder in [
            (CommentThread, document_from_thread),
            (Comment, document_from_comment),
        ]:
            paginator = Paginator(
                model.objects.order_by("pk").all(), per_page=batch_size
            )
            for page_number in paginator.page_range:
                page = paginator.get_page(page_number)
                documents = [
                    document_builder(obj.pk, obj.doc_to_hash())
                    for obj in page.object_list
                ]
                if documents:
                    response = client.collections[collection_name()].documents.import_(
                        documents, {"action": "upsert"}
                    )
                    if not all(result["success"] for result in response):
                        raise ValueError(
                            f"Errors while importing documents to Typesense collection: {response}"
                        )

    def validate_indices(self) -> None:
        """
        Check if the indices exist and are valid.

        Raise an exception if any do not exist or if any are not valid.
        Note that the validation is lengthy,
        because Typesense may add new keys to the schema.
        This is fine - we only want to assert that keys we know about are set as expected.
        There are also some fields in the retrieved schema we don't care about - eg. 'created_at'
        """
        client = get_typesense_client()
        # cast to a wider type, because we want to use it in a more flexible way than TypedDict normally allows.
        actual_schema = cast(
            dict[str, Any], client.collections[collection_name()].retrieve()
        )
        expected_schema = expected_full_collection_schema()
        errors: list[str] = []

        expected_field_names = set(
            map(lambda field: field["name"], expected_schema["fields"])
        )
        actual_field_names = set(
            map(lambda field: field["name"], actual_schema["fields"])
        )

        if missing_fields := expected_field_names - actual_field_names:
            errors.append(
                f"ERROR: '{collection_name()}' collection schema 'fields' has missing field(s): {missing_fields}."
            )

        if extra_fields := actual_field_names - expected_field_names:
            errors.append(
                f"ERROR: '{collection_name()}' collection schema 'fields' "
                f"has unexpected extra field(s): {extra_fields}."
            )

        if actual_field_names == expected_field_names:
            for expected_field, actual_field in zip(
                sorted(expected_schema["fields"], key=lambda field: field["name"]),
                sorted(actual_schema["fields"], key=lambda field: field["name"]),
            ):
                for key, expected_value in expected_field.items():
                    if expected_value != actual_field[key]:
                        errors.append(
                            f"ERROR: in collection '{collection_name()}' fields, field '{expected_field['name']}', "
                            f"key '{key}' failed to validate. "
                            f"Expected: '{expected_value}', actual '{actual_field[key]}'."
                        )

        for key, expected_value in expected_schema.items():
            if key == "fields":
                # we've already validated fields separately above
                continue

            if expected_value != actual_schema[key]:
                errors.append(
                    f"ERROR: in collection '{collection_name()}', key '{key}' failed to validate. "
                    f"Expected: '{expected_value}', actual '{actual_schema[key]}'."
                )

        if errors:
            for error in errors:
                print(error)
            raise AssertionError("\n".join(errors))

    def refresh_indices(self) -> None:
        """
        Noop on Typesense, as all write API operations are synchronous.

        See https://typesense.org/docs/guide/migrating-from-algolia.html#synchronous-write-apis for more information.
        """
        return None

    def delete_unused_indices(self) -> int:
        """
        Noop for this implementation.
        """
        return 0


class TypesenseThreadSearchBackend(BaseThreadSearchBackend):
    """
    Thread search backend implementation for Typesense.
    """

    def get_thread_ids(
        self,
        context: str,
        # This argument is unsupported. Anyway, its only role was to boost some results,
        # which did not have much effect because they are shuffled anyway downstream.
        group_ids: list[int],
        search_text: str,
        # This parameter is unsupported, but as far as we know it's not used anywhere.
        sort_criteria: Optional[list[dict[str, str]]] = None,
        commentable_ids: Optional[list[str]] = None,
        course_id: Optional[str] = None,
    ) -> list[str]:
        """
        Retrieve thread IDs based on search criteria.
        """
        client = get_typesense_client()

        params = build_search_parameters(
            search_text=search_text,
            course_id=course_id,
            context=context,
            commentable_ids=commentable_ids,
        )

        results = client.collections[collection_name()].documents.search(params)
        thread_ids: set[str] = {
            hit["document"]["thread_id"] for hit in results.get("hits", [])  # type: ignore
        }
        return list(thread_ids)

    def get_suggested_text(self, search_text: str) -> Optional[str]:
        """
        Retrieve text suggestions for a given search query.

        :param search_text: Text to search for suggestions
        :return: Suggested text or None
        """
        # Not implemented, so no suggestions.
        return None


class TypesenseBackend(BaseSearchBackend):
    """
    Typesense-powered search backend.
    """

    DOCUMENT_SEARCH_CLASS = TypesenseDocumentBackend
    INDEX_SEARCH_CLASS = TypesenseIndexBackend
    THREAD_SEARCH_CLASS = TypesenseThreadSearchBackend
