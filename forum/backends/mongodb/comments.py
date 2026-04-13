"""Comment Class for mongo backend."""

from datetime import datetime
from typing import Any, Optional

from bson import ObjectId
from edx_django_utils.monitoring import set_custom_attribute  # type: ignore[import-untyped]

from forum.backends.mongodb.contents import BaseContents
from forum.backends.mongodb.threads import CommentThread
from forum.backends.mongodb.users import Users
from forum.utils import get_handler_by_name


class Comment(BaseContents):
    """
    Comment class for cs_comments_service content model
    """

    index_name = "comments"
    content_type = "Comment"

    def override_query(self, query: dict[str, Any]) -> dict[str, Any]:
        query = {**query, "_type": self.content_type}
        return super().override_query(query)

    @classmethod
    def mapping(cls) -> dict[str, Any]:
        """
        Mapping function for the Thread class
        """
        return {
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
        }

    @classmethod
    def doc_to_hash(cls, doc: dict[str, Any]) -> dict[str, Any]:
        """
        Converts comment document to the dict
        """
        return {
            "body": doc.get("body"),
            "course_id": doc.get("course_id"),
            "comment_thread_id": str(doc.get("comment_thread_id")),
            "commentable_id": doc.get("commentable_id"),
            "group_id": doc.get("group_id"),
            "context": doc.get("context", "course"),
            "created_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
            "title": doc.get("title"),
            "is_deleted": doc.get("is_deleted", False),
            "deleted_at": doc.get("deleted_at"),
            "deleted_by": doc.get("deleted_by"),
        }

    def insert(
        self,
        body: str,
        course_id: str,
        author_id: str,
        comment_thread_id: str,
        parent_id: Optional[str] = None,
        author_username: Optional[str] = None,
        anonymous: bool = False,
        anonymous_to_peers: bool = False,
        depth: int = 0,
        abuse_flaggers: Optional[list[str]] = None,
        historical_abuse_flaggers: Optional[list[str]] = None,
        visible: bool = True,
        is_spam: bool = False,
    ) -> str:
        """
        Inserts a new comment document into the database.

        Args:
            body (str): The body content of the comment.
            course_id (str): The ID of the course the comment is associated with.
            comment_thread_id (str): The ID of the parent comment thread.
            author_id (str): The ID of the author who created the comment.
            author_username (str): The username of the author.
            anonymous (bool, optional): Whether the comment is posted anonymously. Defaults to False.
            anonymous_to_peers (bool, optional): Whether the comment is anonymous to peers. Defaults to False.
            depth (int, optional): The depth of the comment in the thread hierarchy. Defaults to 0.
            abuse_flaggers (Optional[list[str]], optional): Users who flagged the comment. Defaults to None.
            historical_abuse_flaggers (Optional[list[str]], optional): Users historically flagged the comment.
            visible (bool, optional): Whether the comment is visible. Defaults to True.
            is_spam (bool, optional): Whether the comment has been flagged as spam by AI moderation. Defaults to False.
        Returns:
            str: The ID of the inserted document.
        """
        # Track comment insertion
        set_custom_attribute("forum.backend.operation", "insert_comment")
        set_custom_attribute("forum.thread_id", comment_thread_id)
        set_custom_attribute("forum.course_id", course_id)
        set_custom_attribute("forum.author_id", author_id)
        set_custom_attribute("forum.comment_depth", str(depth))
        if parent_id:
            set_custom_attribute("forum.parent_comment_id", parent_id)
            set_custom_attribute("forum.is_child_comment", True)
        else:
            set_custom_attribute("forum.is_child_comment", False)

        date = datetime.now()
        comment_data = {
            "votes": self.get_votes_dict(up=[], down=[]),
            "visible": visible,
            "abuse_flaggers": abuse_flaggers or [],
            "historical_abuse_flaggers": historical_abuse_flaggers or [],
            "is_spam": is_spam,
            "parent_ids": [ObjectId(parent_id)] if parent_id else [],
            "at_position_list": [],
            "body": body,
            "course_id": course_id,
            "_type": self.content_type,
            "endorsed": False,
            "anonymous": anonymous,
            "anonymous_to_peers": anonymous_to_peers,
            "author_id": author_id,
            "comment_thread_id": ObjectId(comment_thread_id),
            "child_count": 0,
            "depth": depth,
            "author_username": author_username or self.get_author_username(author_id),
            "created_at": date,
            "updated_at": date,
        }
        if parent_id:
            comment_data["parent_id"] = ObjectId(parent_id)

        comment_data["endorsement"] = None

        result = self._collection.insert_one(comment_data)

        if parent_id:
            self.update_child_count_in_parent_comment(parent_id, 1)

        self.update_comment_count_in_comment_thread(comment_thread_id, 1)

        # Notify Comment inserted
        get_handler_by_name("comment_inserted").send(
            sender=self.__class__, comment_id=str(result.inserted_id)
        )

        self.update_sk(str(result.inserted_id), parent_id)
        return str(result.inserted_id)

    def update(
        self,
        comment_id: str,
        body: Optional[str] = None,
        course_id: Optional[str] = None,
        anonymous: Optional[bool] = None,
        anonymous_to_peers: Optional[bool] = None,
        comment_thread_id: Optional[ObjectId] = None,
        at_position_list: Optional[list[str]] = None,
        visible: Optional[bool] = None,
        author_id: Optional[str] = None,
        author_username: Optional[str] = None,
        votes: Optional[dict[str, int]] = None,
        abuse_flaggers: Optional[list[str]] = None,
        historical_abuse_flaggers: Optional[list[str]] = None,
        endorsed: Optional[bool] = None,
        child_count: Optional[int] = None,
        depth: Optional[int] = None,
        closed: Optional[bool] = None,
        editing_user_id: Optional[str] = None,
        edit_reason_code: Optional[str] = None,
        endorsement_user_id: Optional[str] = None,
        sk: Optional[str] = None,
        is_spam: Optional[bool] = None,
        is_deleted: Optional[bool] = None,
        deleted_at: Optional[datetime] = None,
        deleted_by: Optional[str] = None,
    ) -> int:
        """
        Updates a comment document in the database.

        Args:
            comment_id (ObjectId): The ID of the comment to update.
            body (Optional[str], optional): The body content of the comment.
            course_id (Optional[str], optional): The ID of the course the comment is associated with.
            anonymous (Optional[bool], optional): Whether the comment is posted anonymously.
            anonymous_to_peers (Optional[bool], optional): Whether the comment is anonymous to peers.
            comment_thread_id (Optional[ObjectId], optional): The ID of the parent comment thread.
            at_position_list (Optional[list[str]], optional): A list of positions for @mentions.
            visible (Optional[bool], optional): Whether the comment is visible.
            author_id (Optional[str], optional): The ID of the author who created the comment.
            author_username (Optional[str], optional): The username of the author.
            votes (Optional[dict[str, int]], optional): The votes for the comment.
            abuse_flaggers (Optional[list[str]], optional): A list of users who flagged the comment for abuse.
            historical_abuse_flaggers (Optional[list[str]], optional): Users who historically flagged the comment.
            endorsed (Optional[bool], optional): Whether the comment is endorsed.
            child_count (Optional[int], optional): The number of child comments.
            depth (Optional[int], optional): The depth of the comment in the thread hierarchy.

        Returns:
            int: The number of documents modified.
        """
        fields = [
            ("body", body),
            ("course_id", course_id),
            ("anonymous", anonymous),
            ("anonymous_to_peers", anonymous_to_peers),
            ("comment_thread_id", comment_thread_id),
            ("at_position_list", at_position_list),
            ("visible", visible),
            ("author_id", author_id),
            ("author_username", author_username),
            ("votes", votes),
            ("abuse_flaggers", abuse_flaggers),
            ("historical_abuse_flaggers", historical_abuse_flaggers),
            ("endorsed", endorsed),
            ("child_count", child_count),
            ("depth", depth),
            ("closed", closed),
            ("sk", sk),
            ("is_spam", is_spam),
            ("is_deleted", is_deleted),
            ("deleted_at", deleted_at),
            ("deleted_by", deleted_by),
        ]
        update_data: dict[str, Any] = {
            field: value for field, value in fields if value is not None
        }
        if endorsed and endorsement_user_id:
            update_data["endorsement"] = {
                "user_id": endorsement_user_id,
                "time": datetime.now(),
            }
        else:
            update_data["endorsement"] = None

        if editing_user_id:
            edit_history = []
            original_body = ""
            if comment := Comment().get(comment_id):
                edit_history = comment.get("edit_history", [])
                original_body = comment.get("body", "")
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

        update_data["updated_at"] = datetime.now()
        result = self._collection.update_one(
            {"_id": ObjectId(comment_id)},
            {"$set": update_data},
        )

        # Notify Comment updated
        get_handler_by_name("comment_updated").send(
            sender=self.__class__, comment_id=comment_id
        )

        return result.modified_count

    def delete(  # type: ignore[override]
        self, _id: str, mode: str = "hard", deleted_by: Optional[str] = None
    ) -> tuple[int, int]:
        """
        Deletes a comment from the database based on the id.

        Args:
            _id: The ID of the comment.
            mode: 'hard' for permanent deletion, 'soft' for marking as deleted.
            deleted_by: User ID of who deleted the comment (used in soft delete).

        Returns:
            The number of comments deleted.
        """
        # Track comment deletion
        set_custom_attribute("forum.backend.operation", "delete_comment")
        set_custom_attribute("forum.comment_id", _id)
        set_custom_attribute("forum.delete_mode", mode)
        if deleted_by:
            set_custom_attribute("forum.deleted_by", deleted_by)

        comment = self.get(_id)
        if not comment:
            return 0, 0

        parent_comment_id = comment.get("parent_id")
        child_comments_deleted_count = 0
        if not parent_comment_id:
            child_comments_deleted_count = self.delete_child_comments(
                _id, mode=mode, deleted_by=deleted_by
            )

        if mode == "soft":
            # Soft delete: mark as deleted
            self.update(
                _id,
                is_deleted=True,
                deleted_at=datetime.now(),
                deleted_by=deleted_by,
            )
            result_count = 1
        else:
            # Hard delete: permanently remove
            result = self._collection.delete_one({"_id": ObjectId(_id)})
            result_count = result.deleted_count
        if mode == "hard":
            if parent_comment_id:
                self.update_child_count_in_parent_comment(parent_comment_id, -1)

        no_of_comments_delete = result_count + child_comments_deleted_count
        comment_thread_id = comment["comment_thread_id"]

        self.update_comment_count_in_comment_thread(
            comment_thread_id, -(int(no_of_comments_delete))
        )

        # Notify Comments deleted
        get_handler_by_name("comment_deleted").send(
            sender=self.__class__, comment_id=_id
        )

        return result_count, child_comments_deleted_count

    def get_author_username(self, author_id: str) -> str | None:
        """Return username for the respective author_id(user_id)"""
        user = Users().get(author_id)
        return user.get("username") if user else None

    def delete_child_comments(
        self, _id: str, mode: str = "hard", deleted_by: Optional[str] = None
    ) -> int:
        """
        Delete child comments from the database based on the id.

        Args:
            _id: The ID of the parent comment whose child comments will be deleted.
            mode: 'hard' for permanent deletion, 'soft' for marking as deleted.
            deleted_by: User ID of who deleted the comments (used in soft delete).

        Returns:
            The number of child comments deleted.
        """
        if mode == "soft":
            child_comments_to_delete = self.find(
                {"parent_id": ObjectId(_id), "is_deleted": {"$ne": True}}
            )
        else:
            child_comments_to_delete = self.find({"parent_id": ObjectId(_id)})

        child_comment_ids_to_delete = [
            child_comment.get("_id") for child_comment in child_comments_to_delete
        ]

        if mode == "soft":
            # Soft delete: mark all child comments as deleted
            deleted_at = datetime.now()
            for child_comment_id in child_comment_ids_to_delete:
                self.update(
                    str(child_comment_id),
                    is_deleted=True,
                    deleted_at=deleted_at,
                    deleted_by=deleted_by,
                )
            child_comments_deleted_count = len(child_comment_ids_to_delete)
        else:
            # Hard delete: permanently remove
            child_comments_deleted = self._collection.delete_many(
                {"_id": {"$in": child_comment_ids_to_delete}}
            )
            child_comments_deleted_count = child_comments_deleted.deleted_count

        for child_comment_id in child_comment_ids_to_delete:
            get_handler_by_name("comment_deleted").send(
                sender=self.__class__, comment_id=child_comment_id
            )

        return child_comments_deleted_count

    def update_child_count_in_parent_comment(self, parent_id: str, count: int) -> None:
        """
        Update(increment/decrement) child_count in parent comment.

        Args:
            parent_id: The ID of the parent comment whose child_count will be updated.
            count: It can be any number.
                   If positive, this function will increase child_count by the count.
                   If negative, this function will decrease child_count by the count.

        Returns:
            None.
        """
        update_child_count_query = {"$inc": {"child_count": count}}
        self.update_count(parent_id, update_child_count_query)

    def update_comment_count_in_comment_thread(
        self, comment_thread_id: str, count: int
    ) -> None:
        """
        Update(increment/decrement) comment_count in comment thread.

        Args:
            comment_thread_id: The ID of the comment thread
                                whose comment_count will be updated.
            count: It can be any number.
                    If positive, this function will increase comment_count by the count.
                    If negative, this function will decrease comment_count by the count.

        Returns:
            None.
        """
        update_comment_count_query = {
            "$inc": {"comment_count": count},
            "$set": {"last_activity_at": datetime.now()},
        }
        CommentThread().update_count(comment_thread_id, update_comment_count_query)

    def get_sk(self, _id: str, parent_id: Optional[str]) -> str:
        """Returns sk field."""
        if parent_id is not None:
            return f"{parent_id}-{_id}"
        return f"{_id}"

    def update_sk(self, _id: str, parent_id: Optional[str]) -> None:
        """Updates sk field."""
        sk = self.get_sk(_id, parent_id)
        self.update(_id, sk=sk)

    def restore_comment(
        self, comment_id: str, restored_by: Optional[str] = None
    ) -> bool:
        """
        Restores a soft-deleted comment by setting is_deleted=False and clearing deletion metadata.
        Also updates thread comment count and user course stats.

        Args:
            comment_id: The ID of the comment to restore
            restored_by: The ID of the user performing the restoration (optional)

        Returns:
            bool: True if comment was restored, False if not found
        """

        # Get the comment first to check if it exists and get metadata
        comment = self.get(comment_id)
        if not comment:
            return False

        # Only restore if it's actually deleted
        if not comment.get("is_deleted", False):
            return True  # Already restored

        update_data: dict[str, Any] = {
            "is_deleted": False,
            "deleted_at": None,
            "deleted_by": None,
        }

        if restored_by:
            update_data["restored_by"] = restored_by
            update_data["restored_at"] = datetime.now().isoformat()

        result = self._collection.update_one(
            {"_id": ObjectId(comment_id)}, {"$set": update_data}
        )

        if result.matched_count > 0:
            # Update thread comment count
            comment_thread_id = comment.get("comment_thread_id")
            if comment_thread_id:
                # Count child comments that are not deleted
                child_count = 0
                if not comment.get("parent_id"):  # If this is a parent comment
                    for _ in self.find(
                        {
                            "parent_id": ObjectId(comment_id),
                            "is_deleted": {"$eq": False},
                        }
                    ):
                        child_count += 1

                # Increment comment count in thread (1 for this comment + its non-deleted children)
                self.update_comment_count_in_comment_thread(
                    comment_thread_id, 1 + child_count
                )

            # Update user course stats
            author_id = comment.get("author_id")
            course_id = comment.get("course_id")
            parent_comment_id = comment.get("parent_id")

            if author_id and course_id:

                # Check if comment is anonymous
                if not (comment.get("anonymous") or comment.get("anonymous_to_peers")):
                    from forum.backends.mongodb.api import (  # pylint: disable=import-outside-toplevel
                        MongoBackend,
                    )

                    if parent_comment_id:
                        # This is a reply - increment replies count and decrement deleted_replies
                        MongoBackend.update_stats_for_course(
                            author_id, course_id, replies=1, deleted_replies=-1
                        )
                    else:
                        # This is a response - increment responses count, decrement deleted_responses
                        # Also increment replies by child count and decrement deleted_replies by child_count
                        MongoBackend.update_stats_for_course(
                            author_id,
                            course_id,
                            responses=1,
                            deleted_responses=-1,
                            replies=child_count,
                            deleted_replies=-child_count,
                        )

            return True

        return False

    def get_user_deleted_comment_count(
        self, user_id: str, course_ids: list[str]
    ) -> int:
        """
        Returns count of deleted comments for user in the given course_ids.

        Args:
            user_id: The ID of the user
            course_ids: List of course IDs to search in

        Returns:
            int: Count of deleted comments
        """
        query_params = {
            "course_id": {"$in": course_ids},
            "author_id": str(user_id),
            "_type": self.content_type,
            "is_deleted": True,
        }
        return self._collection.count_documents(query_params)

    def restore_user_deleted_comments(
        self, user_id: str, course_ids: list[str], restored_by: Optional[str] = None
    ) -> int:
        """
        Restores (undeletes) comments of user in the given course_ids by setting is_deleted=False.

        Args:
            user_id: The ID of the user whose comments to restore
            course_ids: List of course IDs to restore comments in
            restored_by: The ID of the user performing the restoration (optional)

        Returns:
            int: Number of comments restored
        """
        query_params = {
            "course_id": {"$in": course_ids},
            "author_id": str(user_id),
            "is_deleted": {"$eq": True},
        }

        comments_restored = 0
        comments = self.get_list(**query_params)

        for comment in comments:
            comment_id = comment.get("_id")
            if comment_id:
                if self.restore_comment(str(comment_id), restored_by=restored_by):
                    comments_restored += 1

        return comments_restored

    def delete_user_comments(
        self, user_id: str, course_ids: list[str], deleted_by: Optional[str] = None
    ) -> int:
        """
        Deletes (soft deletes) all non-deleted comments of user in the given course_ids.

        Args:
            user_id: The ID of the user whose comments to delete
            course_ids: List of course IDs to delete comments from
            deleted_by: The ID of the user performing the deletion (optional)

        Returns:
            int: Number of comments deleted
        """
        from forum import api as forum_api  # pylint: disable=import-outside-toplevel

        query_params = {
            "course_id": {"$in": course_ids},
            "author_id": str(user_id),
            "is_deleted": {"$ne": True},
        }

        comments_deleted = 0
        comments = self.get_list(**query_params)

        for comment in comments:
            comment_id = comment.get("_id")
            course_id = comment.get("course_id")
            if comment_id:
                # Use forum_api.delete_comment which supports deleted_by parameter
                forum_api.delete_comment(
                    comment_id, course_id=course_id, deleted_by=deleted_by
                )
                comments_deleted += 1

        return comments_deleted
