"""
Typesense backend for searching comments and threads.
"""

from typing import Any, Optional

from bs4 import BeautifulSoup
from django.conf import settings
from django.core.paginator import Paginator
from typesense import Client
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


class CommentsIndex:
    """
    Common data and operations relating to the comments index.
    """

    model = Comment

    @staticmethod
    def name() -> str:
        """
        Return the Typesense index name for the index.
        """
        return settings.TYPESENSE_COLLECTION_PREFIX + "comments"

    @classmethod
    def schema(cls) -> CollectionCreateSchema:
        return {
            "name": cls.name(),
            "fields": [
                {"name": "course_id", "type": "string"},
                {"name": "comment_thread_id", "type": "string"},
                {"name": "body", "type": "string"},
            ],
        }

    @staticmethod
    def build_document(doc_id: str | int, data: dict[str, Any]) -> DocumentSchema:
        """
        Build a Typesense document for this index.
        """
        # NOTE: Comments have no commentable_id or title, and the context is hardcoded to "course".
        return {
            "id": str(doc_id),
            "course_id": str(data.get("course_id", "")),
            "comment_thread_id": str(data.get("comment_thread_id", "")),
            "body": (
                BeautifulSoup(data["body"], features="html.parser").get_text()
                if data.get("body")
                else ""
            ),
        }

    @staticmethod
    def build_search_parameters(
        *, search_text: str, course_id: str | None
    ) -> SearchParameters:
        """
        Build Typesense search parameters for this index.
        """
        return {
            "q": search_text,
            "query_by": "body",
            "filter_by": (
                f"course_id:={quote_filter_value(course_id)}" if course_id else ""
            ),
            "per_page": FORUM_MAX_DEEP_SEARCH_COMMENT_COUNT,
        }


class CommentThreadsIndex:
    """
    Common data and operations relating to the comment threads index.
    """

    model = CommentThread

    @staticmethod
    def name() -> str:
        """
        Return the Typesense index name for the index.
        """
        return settings.TYPESENSE_COLLECTION_PREFIX + "comment_threads"

    @classmethod
    def schema(cls) -> CollectionCreateSchema:
        return {
            "name": cls.name(),
            "fields": [
                {"name": "course_id", "type": "string"},
                {"name": "commentable_id", "type": "string"},
                {"name": "context", "type": "string"},
                {"name": "title", "type": "string"},
                {"name": "body", "type": "string"},
            ],
        }

    @staticmethod
    def build_document(doc_id: str | int, data: dict[str, Any]) -> DocumentSchema:
        """
        Build a Typesense document for this index.
        """
        return {
            "id": str(doc_id),
            "course_id": str(data.get("course_id", "")),
            "commentable_id": str(data.get("commentable_id", "")),
            "context": str(data.get("context", "")),
            "title": str(data.get("title", "")),
            "body": (
                BeautifulSoup(data["body"], features="html.parser").get_text()
                if data.get("body")
                else ""
            ),
        }

    @staticmethod
    def build_search_parameters(
        *,
        search_text: str,
        course_id: str | None,
        context: str,
        commentable_ids: list[str] | None,
    ) -> SearchParameters:
        """
        Build Typesense search parameters for this index.
        """
        # Context is always a single word, so we can use the faster `:` operator, without sacrificing accuracy.
        filters = [f"context:{quote_filter_value(context)}"]
        if commentable_ids:
            safe_ids = ", ".join(quote_filter_value(value) for value in commentable_ids)
            filters.append(f"commentable_ids:[{safe_ids}]")
        if course_id:
            filters.append(f"course_id:={quote_filter_value(course_id)}")

        return {
            "q": search_text,
            "query_by": "title,body",
            "filter_by": " && ".join(filters),
            "per_page": FORUM_MAX_DEEP_SEARCH_COMMENT_COUNT,
        }


INDICES: dict[str, type[CommentsIndex] | type[CommentThreadsIndex]] = {
    "comments": CommentsIndex,
    "comment_threads": CommentThreadsIndex,
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
        index = INDICES[index_name]
        typesense_document = index.build_document(doc_id, document)
        client.collections[index.name()].documents.upsert(typesense_document)

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
        index = INDICES[index_name]
        client.collections[index.name()].documents[str(doc_id)].delete(
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
        for index in INDICES.values():
            exists: bool = True
            try:
                client.collections[index.name()].retrieve()
            except ObjectNotFound:
                exists = False

            if force_new_index and exists:
                client.collections[index.name()].delete()

            if force_new_index or not exists:
                client.collections.create(index.schema())

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
        for index in INDICES.values():
            paginator = Paginator(index.model.objects.all(), per_page=batch_size)
            for page_number in paginator.page_range:
                page = paginator.get_page(page_number)
                documents = [
                    index.build_document(obj.pk, obj.doc_to_hash())
                    for obj in page.object_list
                ]
                if documents:
                    client.collections[index.name()].documents.import_(
                        documents, {"action": "upsert"}
                    )

    def validate_indices(self) -> None:
        """
        Check if the indices exist and are valid.

        Raise an exception if any do not exist or if any are not valid.
        """
        client = get_typesense_client()
        for index in INDICES.values():
            collection = client.collections[index.name()].retrieve()
            # TODO: collection returns more information than the initial create schema,
            # so we need a better comparison here; this is currently broken
            if collection != index.schema():
                print(f"Expected schema: {index.schema()}")
                print(f"Found schema: {collection}")
                raise AssertionError(
                    f"Collection {index.name()} exists, but schema does not match expected."
                )

    def refresh_indices(self) -> None:
        """
        Noop on Typesense, as all write API operations are synchronous.

        See https://typesense.org/docs/guide/migrating-from-algolia.html#synchronous-write-apis for more information.
        """
        return None

    def delete_unused_indices(self) -> int:
        """
        Noop on Typesense.
        """
        return 0


def quote_filter_value(value: str) -> str:
    """
    Sanitize and safely quote a value for use in a Typesense filter.

    https://typesense.org/docs/guide/tips-for-filtering.html#escaping-special-characters
    """
    return "`" + value.replace("`", "") + "`"


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
        thread_ids: set[str] = set()

        # All comments have "course" as their context, and none of them have a commentable_id.
        if context == "course" and not commentable_ids:
            comment_results = client.collections[CommentsIndex.name()].documents.search(
                CommentsIndex.build_search_parameters(
                    search_text=search_text, course_id=course_id
                )
            )
            for hit in comment_results.get("hits", []):
                thread_ids.add(hit["document"]["comment_thread_id"])

        thread_results = client.collections[
            CommentThreadsIndex.name()
        ].documents.search(
            CommentThreadsIndex.build_search_parameters(
                search_text=search_text,
                course_id=course_id,
                context=context,
                commentable_ids=commentable_ids,
            )
        )
        for hit in thread_results.get("hits", []):
            thread_ids.add(hit["document"]["id"])

        return list(thread_ids)

    def get_suggested_text(self, search_text: str) -> Optional[str]:
        """
        Retrieve text suggestions for a given search query.

        :param search_text: Text to search for suggestions
        :return: Suggested text or None
        """
        # TODO: https://typesense.org/docs/guide/query-suggestions.html
        # TODO: if this is implemented, do we need to also implement get_thread_ids_with_corrected_text?
        return None


class TypesenseBackend(BaseSearchBackend):
    """
    Typesense-powered search backend.
    """

    DOCUMENT_SEARCH_CLASS = TypesenseDocumentBackend
    INDEX_SEARCH_CLASS = TypesenseIndexBackend
    THREAD_SEARCH_CLASS = TypesenseThreadSearchBackend
