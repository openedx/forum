"""Content Class for mongo backend."""

from datetime import datetime
from typing import Any, Optional

from bson import ObjectId

from forum.backends.mongodb.contents import BaseContents
from forum.backends.mongodb.users import Users
from forum.utils import get_handler_by_name


class CommentThread(BaseContents):
    """
    CommentThread class for cs_comments_service content model
    """

    index_name = "comment_threads"
    content_type = "CommentThread"

    def delete(self, _id: str) -> int:
        """Delete CommentThread"""
        result = super().delete(_id)
        get_handler_by_name("comment_thread_deleted").send(
            sender=self.__class__, comment_thread_id=_id
        )
        Users().delete_read_state_by_thread_id(_id)
        return result

    @classmethod
    def mapping(cls) -> dict[str, Any]:
        """
        Mapping function for the Thread class
        """
        return {
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
        }

    @classmethod
    def doc_to_hash(cls, doc: dict[str, Any]) -> dict[str, Any]:
        """
        Converts thread document to the dict
        """
        return {
            "id": str(doc.get("_id")),
            "title": doc.get("title"),
            "body": doc.get("body"),
            "created_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
            "last_activity_at": doc.get("last_activity_at"),
            "comment_count": doc.get("comment_count"),
            "votes_point": doc.get("votes", {}).get("point"),
            "context": doc.get("context"),
            "course_id": doc.get("course_id"),
            "commentable_id": doc.get("commentable_id"),
            "author_id": doc.get("author_id"),
            "group_id": doc.get("group_id"),
            "thread_id": str(doc.get("_id")),
        }

    def insert(
        self,
        title: str,
        body: str,
        course_id: str,
        commentable_id: str,
        author_id: str,
        author_username: Optional[str] = None,
        anonymous: bool = False,
        anonymous_to_peers: bool = False,
        thread_type: str = "discussion",
        context: str = "course",
        pinned: bool = False,
        visible: bool = True,
        abuse_flaggers: Optional[list[str]] = None,
        historical_abuse_flaggers: Optional[list[str]] = None,
        group_id: Optional[int] = None,
    ) -> str:
        """
        Inserts a new thread document into the database.

        Args:
            title (str): The title of the thread.
            body (str): The body content of the thread.
            course_id (str): The ID of the course the thread is associated with.
            commentable_id (str): The ID of the commentable entity.
            author_id (str): The ID of the author who created the thread.
            author_username (str): The username of the author.
            anonymous (bool, optional): Whether the thread is posted anonymously. Defaults to False.
            anonymous_to_peers (bool, optional): Whether the thread is anonymous to peers. Defaults to False.
            thread_type (str, optional): The type of the thread, either 'question' or 'discussion'.
            context (str, optional): The context of the thread, either 'course' or 'standalone'.
            pinned (bool): Whether the thread is pinned. Defaults to False.
            visible (bool): Whether the thread is visible. Defaults to True.
            abuse_flaggers: A list of users who flagged the thread for abuse.
            historical_abuse_flaggers: A list of users who historically flagged the thread for abuse.

        Raises:
            ValueError: If `thread_type` is not 'question' or 'discussion'.
            ValueError: If `context` is not 'course' or 'standalone'.

        Returns:
            str: The ID of the inserted document.
        """
        if thread_type not in ["question", "discussion"]:
            raise ValueError("Invalid thread_type")

        if context not in ["course", "standalone"]:
            raise ValueError("Invalid context")

        if abuse_flaggers is None:
            abuse_flaggers = []
        if historical_abuse_flaggers is None:
            historical_abuse_flaggers = []

        date = datetime.now()
        thread_data = {
            "votes": self.get_votes_dict(up=[], down=[]),
            "thread_type": thread_type,
            "context": context,
            "comment_count": 0,
            "at_position_list": [],
            "title": title,
            "body": body,
            "course_id": course_id,
            "commentable_id": commentable_id,
            "_type": self.content_type,
            "anonymous": anonymous,
            "anonymous_to_peers": anonymous_to_peers,
            "closed": False,
            "author_id": author_id,
            "author_username": author_username or self.get_author_username(author_id),
            "created_at": date,
            "updated_at": date,
            "last_activity_at": date,
            "pinned": pinned,
            "visible": visible,
            "abuse_flaggers": abuse_flaggers,
            "historical_abuse_flaggers": historical_abuse_flaggers,
        }
        if group_id:
            thread_data["group_id"] = group_id

        result = self._collection.insert_one(thread_data)
        thread_id = str(result.inserted_id)

        # Notify Thread inserted
        get_handler_by_name("comment_thread_inserted").send(
            sender=self.__class__, comment_thread_id=thread_id
        )
        return thread_id

    def update(
        self,
        thread_id: str,
        thread_type: Optional[str] = None,
        title: Optional[str] = None,
        body: Optional[str] = None,
        course_id: Optional[str] = None,
        anonymous: Optional[bool] = None,
        anonymous_to_peers: Optional[bool] = None,
        commentable_id: Optional[str] = None,
        at_position_list: Optional[list[str]] = None,
        closed: Optional[bool] = None,
        context: Optional[str] = None,
        author_id: Optional[str] = None,
        author_username: Optional[str] = None,
        votes: Optional[dict[str, int]] = None,
        abuse_flaggers: Optional[list[str]] = None,
        historical_abuse_flaggers: Optional[list[str]] = None,
        closed_by: Optional[str] = None,
        pinned: Optional[bool] = None,
        comments_count: Optional[int] = None,
        endorsed: Optional[bool] = None,
        edit_history: Optional[list[dict[str, Any]]] = None,
        original_body: Optional[str] = None,
        editing_user_id: Optional[str] = None,
        edit_reason_code: Optional[str] = None,
        close_reason_code: Optional[str] = None,
        closed_by_id: Optional[str] = None,
        group_id: Optional[int] = None,
        skip_timestamp_update: bool = False,
    ) -> int:
        """
        Updates a thread document in the database.

        Args:
            thread_id: ID of thread to update.
            thread_type: The type of the thread, either 'question' or 'discussion'.
            title: The title of the thread.
            body: The body content of the thread.
            course_id: The ID of the course the thread is associated with.
            anonymous: Whether the thread is posted anonymously.
            anonymous_to_peers: Whether the thread is anonymous to peers.
            commentable_id: The ID of the commentable entity.
            at_position_list: A list of positions for @mentions.
            closed: Whether the thread is closed.
            context: The context of the thread, either 'course' or 'standalone'.
            author_id: The ID of the author who created the thread.
            author_username: The username of the author.
            votes: The votes for the thread.
            abuse_flaggers: A list of users who flagged the thread for abuse.
            historical_abuse_flaggers: A list of users who historically flagged the thread for abuse.
            closed_by: The ID of the user who closed the thread.
            pinned: Whether the thread is pinned.
            comments_count: The number of comments on the thread.
            endorsed: Whether the thread is endorsed.
            skip_timestamp_update: Whether to skip updating the timestamp (default: False).

        Returns:
            int: The number of documents modified.
        """
        fields = [
            ("thread_type", thread_type),
            ("title", title),
            ("body", body),
            ("course_id", course_id),
            ("anonymous", anonymous),
            ("anonymous_to_peers", anonymous_to_peers),
            ("commentable_id", commentable_id),
            ("at_position_list", at_position_list),
            ("closed", closed),
            ("context", context),
            ("author_id", author_id),
            ("author_username", author_username),
            ("votes", votes),
            ("abuse_flaggers", abuse_flaggers),
            ("historical_abuse_flaggers", historical_abuse_flaggers),
            ("closed_by", closed_by),
            ("pinned", pinned),
            ("comment_count", comments_count),
            ("endorsed", endorsed),
            ("close_reason_code", close_reason_code),
            ("closed_by_id", closed_by_id),
            ("group_id", group_id),
        ]
        update_data: dict[str, Any] = {
            field: value for field, value in fields if value is not None
        }
        if not closed and (close_reason_code and closed_by_id):
            update_data["closed_by_id"] = None
            update_data["close_reason_code"] = None

        if editing_user_id:
            edit_history = [] if edit_history is None else edit_history
            edit_history.append(
                {
                    "author_id": editing_user_id,
                    "original_body": original_body,
                    "reason_code": edit_reason_code,
                    "editor_username": self.get_author_username(editing_user_id),
                    "created_at": datetime.now(),
                }
            )
            update_data["edit_history"] = edit_history

        if not skip_timestamp_update:
            date = datetime.now()
            update_data["updated_at"] = date
        result = self._collection.update_one(
            {"_id": ObjectId(thread_id)},
            {"$set": update_data},
        )

        # Notify thread updated
        get_handler_by_name("comment_thread_updated").send(
            sender=self.__class__, comment_thread_id=thread_id
        )
        return result.modified_count

    def get_author_username(self, author_id: str) -> str | None:
        """Return username for the respective author_id(user_id)"""
        user = Users().get(author_id)
        return user.get("username") if user else None
