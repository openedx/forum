"""Content Class for mongo backend."""

from datetime import datetime
from typing import Any, Optional

from bson import ObjectId
from pymongo.cursor import Cursor

from forum.backends.mongodb.base_model import MongoBaseModel


class BaseContents(MongoBaseModel):
    """
    BaseContents class: same as Contents, but without "update" and "insert" methods,
    because child classes will have different signatures for these methods.
    """

    content_type: str = ""
    COLLECTION_NAME: str = "contents"

    def create_indexes(self) -> None:
        """
        The implementation creates the indexes in the mongodb for the contents collection.
        """
        self._collection.create_index(
            [
                ("_type", 1),
                ("course_id", 1),
                ("pinned", -1),
                ("created_at", -1),
            ],
            background=True,
        )
        self._collection.create_index(
            [
                ("_type", 1),
                ("course_id", 1),
                ("pinned", -1),
                ("comment_count", -1),
                ("created_at", -1),
            ],
            background=True,
        )
        self._collection.create_index(
            [
                ("_type", 1),
                ("course_id", 1),
                ("pinned", -1),
                ("votes.point", -1),
                ("created_at", -1),
            ],
            background=True,
        )
        self._collection.create_index(
            [
                ("_type", 1),
                ("course_id", 1),
                ("pinned", -1),
                ("last_activity_at", -1),
                ("created_at", -1),
            ],
            background=True,
        )
        self._collection.create_index(
            [
                ("comment_thread_id", 1),
                ("sk", 1),
            ],
            sparse=True,
        )
        self._collection.create_index(
            [
                ("comment_thread_id", 1),
                ("endorsed", 1),
            ],
            sparse=True,
        )
        self._collection.create_index(
            [
                ("commentable_id", 1),
            ],
            sparse=True,
            background=True,
        )

    @classmethod
    def mapping(cls) -> dict[str, Any]:
        """
        Implement this method in the child class
        """
        raise NotImplementedError

    @classmethod
    def doc_to_hash(cls, doc: dict[str, Any]) -> dict[str, Any]:
        """
        Implement this method in the child class
        """
        raise NotImplementedError

    def override_query(self, query: dict[str, Any]) -> dict[str, Any]:
        """
        Override the query with the _type field.
        """
        if self.content_type:
            query = {**query, "_type": self.content_type}
        return super().override_query(query)

    def get_list(self, **kwargs: Any) -> Cursor[dict[str, Any]]:
        """
        Retrieves a list of all content documents in the database based on provided filters.

        Args:
            kwargs: The filter arguments.

        Returns:
            A list of content documents.
        """
        resp_skip = kwargs.pop("resp_skip", 0)
        resp_limit = kwargs.pop("resp_limit", None)

        if self.content_type:
            kwargs["_type"] = self.content_type

        # Apply sorting first if provided
        sort = kwargs.pop("sort", None)
        query = self._collection.find(kwargs)
        if sort:
            query = query.sort("sk", sort)

        # Apply pagination after sorting
        query = query.skip(resp_skip)
        if resp_limit is not None:
            query = query.limit(resp_limit)

        return query

    @classmethod
    def get_votes_dict(cls, up: list[str], down: list[str]) -> dict[str, Any]:
        """
        Calculates and returns the vote summary for a thread.

        Args:
            up (list): A list of user IDs who upvoted the thread.
            down (list): A list of user IDs who downvoted the thread.

        Returns:
            dict: A dictionary containing the vote summary with the following keys:
                - "up" (list): The list of user IDs who upvoted.
                - "down" (list): The list of user IDs who downvoted.
                - "up_count" (int): The count of upvotes.
                - "down_count" (int): The count of downvotes.
                - "count" (int): The total number of votes (upvotes + downvotes).
                - "point" (int): The vote score (upvotes - downvotes).
        """
        up = up or []
        down = down or []
        votes = {
            "up": up,
            "down": down,
            "up_count": len(up),
            "down_count": len(down),
            "count": len(up) + len(down),
            "point": len(up) - len(down),
        }
        return votes

    def update_votes(self, content_id: str, votes: dict[str, Any]) -> int:
        """
        Updates a votes in the content document.

        Args:
        content_id: The id of the content model
        votes (Optional[dict[str, int]], optional): The votes for the thread.
        """
        update_data = {"votes": votes, "updated_at": datetime.now()}
        result = self._collection.update_one(
            {"_id": ObjectId(content_id)},
            {"$set": update_data},
        )
        return result.modified_count

    def update_count(self, content_id: str, query: dict[str, Any]) -> int:
        """
        Updates count of a field in the content document based on query.

        Args:
            content_id (str): The id of the content(Commentthread id or Comment id) model.
            query (dict[str, Any]): Query to update the count in a specific field.
        """
        result = self._collection.update_one(
            {"_id": ObjectId(content_id)},
            query,
        )
        return result.modified_count


class Contents(BaseContents):
    """
    Contents class for cs_comments_service contents collection
    """

    def insert(
        self,
        _id: str,
        author_id: str,
        abuse_flaggers: list[str],
        historical_abuse_flaggers: list[str],
        visible: bool,
    ) -> str:
        """
        Inserts a new content document into the database.

        Args:
            _id (str): The ID of the content.
            author_id (str): The ID of the author who created the content.
            abuse_flaggers (list[str]): A list of IDs of users who flagged the content as abusive.
            historical_abuse_flaggers (list[str]): A list of IDs of users who previously flagged the content as abusive.
            visible (bool): Whether the content is visible or not.

        Returns:
            str: The ID of the inserted document.
        """
        content_data = {
            "_id": ObjectId(_id),
            "author_id": author_id,
            "abuse_flaggers": abuse_flaggers,
            "historical_abuse_flaggers": historical_abuse_flaggers,
            "visible": visible,
        }
        result = self._collection.insert_one(content_data)
        return str(result.inserted_id)

    def update(
        self,
        _id: str,
        author_username: Optional[str] = None,
        abuse_flaggers: Optional[list[str]] = None,
        historical_abuse_flaggers: Optional[list[str]] = None,
        body: Optional[str] = None,
        title: Optional[str] = None,
        **kwargs: Any
    ) -> int:
        """
        Updates a contents document in the database based on the provided _id.

        Args:
            _id: The id of the contents document to update.
            **kwargs: The fields to update in the contents document.

        Returns:
            The number of documents modified.
        """
        fields = [
            ("author_username", author_username),
            ("abuse_flaggers", abuse_flaggers),
            ("historical_abuse_flaggers", historical_abuse_flaggers),
            ("body", body),
            ("title", title),
        ]
        update_data: dict[str, Any] = {
            field: value for field, value in fields if value is not None
        }

        result = self._collection.update_one(
            {"_id": ObjectId(_id)},
            {"$set": update_data},
        )
        return result.modified_count
