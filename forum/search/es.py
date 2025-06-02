"""
Elasticsearch client utilities.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Iterator, Optional

from django.conf import settings
from elasticsearch import Elasticsearch, exceptions, helpers

from forum.backends.mysql.models import CommentThread
from forum.backends.mysql import MODEL_INDICES as mysql_model_indices
from forum.constants import FORUM_MAX_DEEP_SEARCH_COMMENT_COUNT
from forum.models import Content
from forum.search import base

__all__ = ["ElasticsearchBackend"]

log = logging.getLogger(__name__)


class ElasticsearchClientMixin:
    """
    Provide a Elasticsearch client API based on a singleton.
    """

    ELASTIC_SEARCH_INSTANCE: Optional[Elasticsearch] = None

    @property
    def client(self) -> Elasticsearch:
        """
        Elasticsearch client singleton.
        """
        if self.ELASTIC_SEARCH_INSTANCE is None:
            self.ELASTIC_SEARCH_INSTANCE = Elasticsearch(
                settings.FORUM_ELASTIC_SEARCH_CONFIG
            )
        return self.ELASTIC_SEARCH_INSTANCE


class ElasticsearchModelMixin:
    """
    Provides convenient model and index name properties.
    """

    @property
    def mysql_models(self) -> tuple[type[Content], ...]:
        return mysql_model_indices

    @property
    def index_names(self) -> list[str]:
        """
        Retrieve the base index names for the configured models.

        Returns:
            list[str]: List of base index names.
        """
        return [model.index_name for model in self.mysql_models]

    def get_mysql_model_from_index_name(self, index_name: str) -> type[Content]:
        for model in self.mysql_models:
            if index_name.startswith(model.index_name):
                return model
        raise Exception("Invalid model name")


class ElasticsearchDocumentBackend(
    base.BaseDocumentSearchBackend, ElasticsearchClientMixin
):
    """
    Elasticsearch-based backend for document management.
    """

    def update_document(
        self, index_name: str, doc_id: str | int, update_data: dict[str, Any]
    ) -> None:
        """
        Update a single document in the specified index.

        Args:
            index_name (str): The name of the index containing the document.
            doc_id (str): The ID of the document to update.
            update_data (dict): The data to update in the document.
        """
        try:
            self.client.update(index=index_name, id=doc_id, body={"doc": update_data})
            log.info(f"Document {doc_id} in index {index_name} updated successfully.")
        except exceptions.NotFoundError:
            log.error(f"Document {doc_id} not found in index {index_name}.")
        except exceptions.RequestError as e:
            log.error(f"Error updating document {doc_id} in index {index_name}: {e}")

    def delete_document(self, index_name: str, doc_id: str | int) -> None:
        """
        Delete a single document from the specified index.

        Args:
            index_name (str): The name of the index containing the document.
            doc_id (str): The ID of the document to delete.
        """
        try:
            self.client.delete(index=index_name, id=doc_id)
            log.info(f"Document {doc_id} in index {index_name} deleted successfully.")
        except exceptions.NotFoundError:
            log.error(f"Document {doc_id} not found in index {index_name}.")
        except exceptions.RequestError as e:
            log.error(f"Error deleting document {doc_id} from index {index_name}: {e}")

    def index_document(
        self, index_name: str, doc_id: str | int, document: dict[str, Any]
    ) -> None:
        """
        Index a single document in the specified Elasticsearch index.

        Args:
            index_name (str): The name of the index to add the document to.
            doc_id (str): The ID of the document.
            document (dict): The document to be indexed.
        """
        try:
            self.client.index(index=index_name, id=doc_id, body=document)
            log.info(f"Document {doc_id} indexed in {index_name}")
        except exceptions.RequestError as e:
            log.error(f"Error indexing document {doc_id} in {index_name}: {e}")


class ElasticsearchIndexBackend(
    base.BaseIndexSearchBackend, ElasticsearchModelMixin, ElasticsearchClientMixin
):
    """
    Search forum threads.
    """

    MAPPINGS: dict[str, dict[str, Any]] = {
        "comments": {
            "dynamic": "false",
            "properties": {
                "body": {
                    "type": "text",
                    "store": True,
                    "term_vector": "with_positions_offsets",
                },
                "course_id": {"type": "keyword"},
                "comment_thread_id": {"type": "keyword"},
                "commentable_id": {"type": "keyword"},
                "group_id": {"type": "keyword"},
                "context": {"type": "keyword"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
                "title": {"type": "keyword"},
            },
        },
        "comment_threads": {
            "dynamic": "false",
            "properties": {
                "title": {
                    "type": "text",
                    "boost": 5.0,
                    "store": True,
                    "term_vector": "with_positions_offsets",
                },
                "body": {
                    "type": "text",
                    "store": True,
                    "term_vector": "with_positions_offsets",
                },
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
                "last_activity_at": {"type": "date"},
                "comment_count": {"type": "integer"},
                "votes_point": {"type": "integer"},
                "context": {"type": "keyword"},
                "course_id": {"type": "keyword"},
                "commentable_id": {"type": "keyword"},
                "author_id": {"type": "keyword"},
                "group_id": {"type": "integer"},
                "id": {"type": "keyword"},
                "thread_id": {"type": "keyword"},
            },
        },
    }

    def rebuild_indices(
        self, batch_size: int = 500, extra_catchup_minutes: int = 5
    ) -> None:
        """
        Rebuild the indices by creating new indices, importing data, and managing aliases.

        Args:
            batch_size (int): Number of documents to process in each batch.
            extra_catchup_minutes (int): Extra minutes to adjust the start time for catch-up.
        """
        initial_start_time = datetime.now()

        # Create new indices and switch aliases
        index_names = self.create_indices()

        for index_name in index_names:
            current_batch = 1
            mysql_model = self.get_mysql_model_from_index_name(index_name)
            for response in self._import_to_es_from_mysql(
                mysql_model, index_name, batch_size
            ):
                self.batch_import_post_process(response, current_batch)
                current_batch += 1

        adjusted_start_time = initial_start_time - timedelta(
            minutes=extra_catchup_minutes
        )
        self.catchup_indices(index_names, adjusted_start_time, batch_size)

        # Update aliases to point to new indices
        for index_name in index_names:
            model = self.get_index_model_rel(index_name)
            self.move_alias(model.index_name, index_name, force_delete=True)

        self.delete_unused_indices()

        log.info("Rebuild indices complete.")

    def get_index_model_rel(self, index_name: str) -> Content:
        """
        Retrieve the model corresponding to the given index name.

        Args:
            index_name (str): Name of the index.

        Returns:
            model: The model associated with the index name.
        """
        for model in self.mysql_models:
            if index_name.startswith(model.index_name):
                return model()
        raise ValueError("Invalid index name")

    def catchup_indices(
        self, index_names: list[str], start_time: datetime, batch_size: int = 100
    ) -> None:
        """
        Catch up the indices by importing documents updated after the specified start time.

        Args:
            index_names (list[str]): List of index names to catch up.
            start_time (datetime): The starting time for catching up.
            batch_size (int): Number of documents to process in each batch.
        """
        for index_name in index_names:
            current_batch = 1
            mysql_model = self.get_mysql_model_from_index_name(index_name)
            mysql_query: dict[str, Any] = {"updated_at__gte": start_time}
            for response in self._import_to_es_from_mysql(
                mysql_model, index_name, batch_size, mysql_query
            ):
                self.batch_import_post_process(response, current_batch)
                current_batch += 1
        log.info(f"Catch up from {start_time} complete.")

    def create_indices(self) -> list[str]:
        """
        Create new indices for each model with the current timestamp in the index name.

        Returns:
            list[str]: List of newly created index names.
        """
        index_names = []
        time_now = datetime.now().strftime("%Y%m%d%H%M%S")

        for model in self.mysql_models:
            index_name = f"{model.index_name}_{time_now}"
            index_names.append(index_name)
            self.client.indices.create(
                index=index_name,
                body={"mappings": self.MAPPINGS[model.index_name]},
            )
        log.info(f"New indices {index_names} are created.")
        return index_names

    def delete_index(self, name: str) -> None:
        """
        Delete the specified index.

        Args:
            name (str): The name of the index to delete.
        """
        self.client.indices.delete(index=name)
        log.info(f"Deleted index: {name}.")

    def delete_unused_indices(self) -> int:
        """
        Delete all Elasticsearch indices that are not the latest for each model type.

        This method fetches all indices matching the patterns from the models, determines the latest index
        for each model type, and deletes all other indices.

        Returns:
            int: The number of indices deleted.
        """
        # Fetch all indices related to models
        all_indices = [
            index
            for pattern in self.index_names
            for index in self.client.indices.get(f"{pattern}*")
        ]

        # Determine the latest indices
        latest_indices: dict[str, Any] = {}
        for index_name in all_indices:
            base_name = self.get_base_index_name(index_name)
            match = re.search(r"\d{14}", index_name)
            if match:
                timestamp = datetime.strptime(match.group(), "%Y%m%d%H%M%S")
                if (
                    base_name not in latest_indices
                    or timestamp > latest_indices[base_name][1]
                ):
                    latest_indices[base_name] = (index_name, timestamp)

        # Delete all indices except the latest ones
        indices_to_delete = set(all_indices) - {
            name for name, _ in latest_indices.values()
        }
        if indices_to_delete:
            self.client.indices.delete(index=",".join(indices_to_delete))
            log.info(f"Deleted unused indices: {indices_to_delete}")

        return len(indices_to_delete)

    def batch_import_post_process(
        self, response: tuple[int, Any], batch_number: int
    ) -> None:
        """
        Process the response from a batch import operation.

        Args:
            response (tuple[int, list[dict]]): tuple containing the count of successful imports and a list of errors.
            batch_number (int): The current batch number being processed.
        """
        success_count, errors = response
        for item in errors:
            if "error" in item["index"]:
                log.error(f"Error indexing. Response was: {response}")
        log.info(
            f"Imported {success_count} documents to the batch {batch_number} into the index"
        )

    def move_alias(
        self, alias_name: str, index_name: str, force_delete: bool = False
    ) -> None:
        """
        Move an alias to point to a new index, optionally deleting an existing index with the same name.

        Args:
            alias_name (str): The alias name to move.
            index_name (str): The new index name to point the alias to.
            force_delete (bool): If True, deletes any existing index with the alias name before moving the alias.

        Raises:
            ValueError: If the alias name matches the index name or if the index doesn't exist.
        """
        if alias_name == index_name:
            raise ValueError(
                f"Can't point alias [{alias_name}] to an index of the same name."
            )
        if not self.exists_index(index_name):
            raise ValueError(f"Can't point alias to non-existent index [{index_name}].")

        if self.exists_index(alias_name) and not self.exists_alias(alias_name):
            if force_delete:
                self.delete_index(alias_name)
            else:
                raise ValueError(
                    f"Can't create alias [{alias_name}] because there is already an "
                    f"auto-generated index of the same name. Try again with force_delete=True to first "
                    f"delete this pre-existing index."
                )

        actions = [{"add": {"index": index_name, "alias": alias_name}}]

        try:
            response = self.client.indices.get_alias(name=alias_name)
            if response:
                actions.insert(
                    0,
                    {
                        "remove": {
                            "index": ",".join(response.keys()),
                            "alias": alias_name,
                        }
                    },
                )
        except exceptions.NotFoundError as e:
            log.warning(f"Alias not found for {alias_name}: {e}")

        self.client.indices.update_aliases(body={"actions": actions})
        log.info(f"Alias [{alias_name}] now points to index [{index_name}].")

    def refresh_indices(self) -> None:
        """
        Refresh the indices associated with the current active aliases.

        Raises:
            ValueError: If no indices are available to refresh.
        """
        active_index_names = self.get_active_index_names()
        if active_index_names:
            self.client.indices.refresh(index=active_index_names)
        else:
            raise ValueError("No indices to refresh")

    def initialize_indices(self, force_new_index: bool = False) -> None:
        """
        Initialize the indices by creating new indices or reusing existing ones based on aliases.

        Args:
            force_new_index (bool): If True, forces the creation of new indices regardless of existing ones.
        """
        if force_new_index or not self.exists_aliases(self.index_names):
            index_names = self.create_indices()
            for index_name in index_names:
                model = self.get_index_model_rel(index_name)
                self.move_alias(model.index_name, index_name, force_delete=True)
        else:
            log.info("Skipping initialization. Indices already exist.")

    def validate_indices(self) -> None:
        """
        Validate that the indices have the correct mappings and properties.

        Raises:
            ValueError: If indices do not exist, or mappings/properties are missing or incorrect.
        """
        actual_mappings = self.client.indices.get_mapping(index=self.index_names)

        if not actual_mappings:
            raise ValueError("Indices do not exist!")

        for index_name in actual_mappings:
            model = self.get_index_model_rel(index_name)
            expected_mapping = self.MAPPINGS[model.index_name]
            actual_mapping = actual_mappings[index_name]["mappings"]

            if not expected_mapping.items() <= actual_mapping.items():
                raise ValueError(f"Mapping mismatch for index {index_name}!")

        log.info("Index validation complete.")

    def exists_index(self, name: str) -> bool:
        """
        Check if an index exists.

        Args:
            name (str): The name of the index to check.

        Returns:
            bool: True if the index exists, False otherwise.
        """
        return self.client.indices.exists(index=name)

    def exists_alias(self, name: str) -> bool:
        """
        Check if an alias exists.

        Args:
            name (str): The name of the alias to check.

        Returns:
            bool: True if the alias exists, False otherwise.
        """
        return self.client.indices.exists_alias(name=name)

    def exists_aliases(self, names: list[str]) -> bool:
        """
        Check if all aliases in the provided list exist.

        Args:
            names (list[str]): List of alias names to check.

        Returns:
            bool: True if all aliases exist, False otherwise.
        """
        return all(self.exists_alias(name) for name in names)

    def _import_to_es_from_mysql(
        self,
        model: Any,
        index_name: str,
        batch_size: int = 500,
        query: dict[str, Any] | None = None,
    ) -> Iterator[tuple[int, Any]]:
        """
        Import documents from the MySQL database into Elasticsearch.

        Args:
            model (Content): The model representing the documents.
            index_name (str): The name of the index to import into.
            batch_size (int): Number of documents to import in each batch.
            query (dict[str, Any], optional): Query to filter documents for import.

        Yields:
            Iterator[tuple[int, Any]]: Number of successful imports and any errors.
        """
        queryset = model.objects.all()
        if query:
            queryset = queryset.filter(**query)

        actions = []
        for doc in queryset.iterator(chunk_size=batch_size):
            action = {
                "_index": index_name,
                "_id": str(doc.id),
                "_source": model.doc_to_hash(doc),
            }
            actions.append(action)
            if len(actions) >= batch_size:
                yield helpers.bulk(self.client, actions)
                actions = []
        if actions:
            yield helpers.bulk(self.client, actions)

    def get_active_index_names(self) -> str:
        """
        Retrieve the names of the indices currently associated with the aliases.

        Returns:
            str: Comma-separated list of active index names.
        """
        return ",".join(
            [
                list(self.client.indices.get_alias(name=index_name).keys())[0]
                for index_name in self.index_names
                if self.exists_alias(index_name)
            ]
        )

    def get_base_index_name(self, index_name: str) -> str:
        """
        Extract the base name of an index by removing the timestamp.

        Args:
            index_name (str): The full index name.

        Returns:
            str: The base name of the index.
        """
        return re.sub(r"_\d{14}$", "", index_name)


class ElasticsearchThreadSearchBackend(
    base.BaseThreadSearchBackend, ElasticsearchClientMixin, ElasticsearchModelMixin
):
    """
    Base class to perform thread search.
    """

    def get_suggested_text(self, search_text: str) -> Optional[str]:
        """
        Retrieve text suggestions for a given search query.

        :param search_text: Text to search for suggestions
        :return: Suggested text or None
        """
        suggestion_fields = ["body", "title"]
        suggest_body: dict[str, Any] = {
            "suggest": {
                f"{field}_suggestions": {
                    "text": search_text,
                    "phrase": {"field": field},
                }
                for field in suggestion_fields
            }
        }
        response: dict[str, Any] = self.client.search(
            index=self.index_names, body=suggest_body
        )
        return self._extract_suggestion(
            response, [f"{field}_suggestions" for field in suggestion_fields]
        )

    @staticmethod
    def _extract_suggestion(
        response: dict[str, Any], suggestion_types: list[str]
    ) -> Optional[str]:
        """
        Extract suggestions from the Elasticsearch response.
        """
        for suggestion_type in suggestion_types:
            suggestions: list[dict[str, Any]] = response.get("suggest", {}).get(
                suggestion_type, []
            )
            options = suggestions and suggestions[0].get("options", [])
            if options:
                return options[0]["text"]
        return None

    def build_must_clause(
        self,
        search_text: str,
        commentable_ids: Optional[list[str]] = None,
        course_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Build the 'must' clause for thread-specific Elasticsearch queries based on input parameters.
        """
        must: list[dict[str, Any]] = []
        commentable_ids = commentable_ids or []

        if len(commentable_ids) == 1:
            must.append({"term": {"commentable_id": commentable_ids[0]}})
        elif len(commentable_ids) > 1:
            must.append({"terms": {"commentable_id": commentable_ids}})
        if course_id:
            must.append({"term": {"course_id": course_id}})

        must.append(
            {
                "multi_match": {
                    "query": search_text,
                    "fields": ["title", "body"],
                    "operator": "AND",
                }
            }
        )

        return must

    def build_filter_clause(
        self,
        context: str,
        group_ids: Optional[list[int]] = None,
    ) -> list[dict[str, Any]]:
        """
        Build the 'filter' clause for thread-specific Elasticsearch queries based on context and group parameters.
        """
        filter_clause: list[dict[str, Any]] = []

        filter_clause.extend(
            [
                {"bool": {"must_not": {"exists": {"field": "context"}}}},
                {"term": {"context": context}},
            ]
        )

        if group_ids and len(group_ids) > 1:
            filter_clause.extend(
                [
                    {"bool": {"must_not": {"exists": {"field": "group_id"}}}},
                    {"terms": {"group_id": group_ids}},
                ]
            )

        elif group_ids and len(group_ids) == 1:
            filter_clause.extend(
                [
                    {"bool": {"must_not": {"exists": {"field": "group_id"}}}},
                    {"term": {"group_id": group_ids[0]}},
                ]
            )

        return filter_clause

    def get_thread_ids(
        self,
        context: str,
        group_ids: list[int],
        search_text: str,
        sort_criteria: Optional[list[dict[str, str]]] = None,
        commentable_ids: Optional[list[str]] = None,
        course_id: Optional[str] = None,
    ) -> list[str]:
        """
        Retrieve thread IDs based on search criteria.
        """
        must_clause: list[dict[str, Any]] = self.build_must_clause(
            search_text, commentable_ids, course_id
        )
        filter_clause: list[dict[str, Any]] = self.build_filter_clause(
            context, group_ids
        )
        search_body = {
            "size": FORUM_MAX_DEEP_SEARCH_COMMENT_COUNT,
            "sort": sort_criteria or [{"updated_at": "desc"}],
            "query": {
                "bool": {"must": must_clause or [], "should": filter_clause or []}
            },
        }
        response = self.client.search(index=self.index_names, body=search_body)
        if response:
            return list(
                {
                    (
                        hit["_id"]
                        if CommentThread.index_name in hit.get("_index")
                        else hit.get("_source", {}).get("comment_thread_id")
                    )
                    for hit in response.get("hits", {}).get("hits")
                }
            )

        return []


class ElasticsearchBackend(base.BaseSearchBackend):
    """
    Helper class for managing Forum indices.
    """

    DOCUMENT_SEARCH_CLASS = ElasticsearchDocumentBackend
    INDEX_SEARCH_CLASS = ElasticsearchIndexBackend
    THREAD_SEARCH_CLASS = ElasticsearchThreadSearchBackend
