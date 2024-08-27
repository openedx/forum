"""Users Class for mongo backend."""

from typing import Any, Optional

from forum.models.base_model import MongoBaseModel


class Users(MongoBaseModel):
    """
    Users class for cs_comments_service user model
    """

    COLLECTION_NAME: str = "users"

    def get(self, _id: str) -> Optional[dict[str, Any]]:
        """
        Get the user based on the id
        """
        return self._collection.find_one({"_id": _id})

    def insert(
        self,
        external_id: str,
        username: Optional[str] = None,
        email: Optional[str] = None,
        default_sort_key: str = "date",
        read_states: Optional[list[dict[str, Any]]] = None,
        course_stats: Optional[list[dict[str, Any]]] = None,
    ) -> str:
        """
        Inserts a new user document into the database.

        Args:
            external_id: The external ID of the user.
            username: The username of the user.
            email: The email of the user.
            default_sort_key: The default sort key for the user.
            read_states: The read states of the user.
            course_stats: The course statistics of the user.

        Returns:
            The ID of the inserted document.

        """
        user_data: dict[str, Any] = {
            "_id": external_id,
            "external_id": external_id,
            "username": username,
            "email": email,
            "default_sort_key": default_sort_key,
            "read_states": read_states,
            "course_stats": course_stats,
        }
        insert_data = {k: v for k, v in user_data.items() if v is not None}
        result = self._collection.insert_one(insert_data)
        return str(result.inserted_id)

    def delete(self, _id: Any) -> int:
        """
        Deletes a user document from the database based on the id.

        Args:
            _id: The ID of the user.

        Returns:
            The number of documents deleted.

        """
        result = self._collection.delete_one({"_id": _id})
        return result.deleted_count

    def update(
        self,
        external_id: str,
        username: Optional[str] = None,
        email: Optional[str] = None,
        default_sort_key: Optional[str] = None,
        read_states: Optional[list[dict[str, Any]]] = None,
        course_stats: Optional[list[dict[str, Any]]] = None,
        active_flags: Optional[int] = None,
    ) -> int:
        """
        Updates a user document in the database based on the external_id.

        Args:
            external_id: The external ID of the user.
            **kwargs: Keyword arguments to update the user document.
            Supported keys:
                - username: The new username of the user.
                - email: The new email of the user.
                - default_sort_key: The new default sort key for the user.
                - read_states: The new read states of the user.
                - course_stats: The new course statistics of the user.
                - active_flags: The new active flags of the user.

        Returns:
            The number of documents modified.

        """
        fields = [
            ("username", username),
            ("email", email),
            ("default_sort_key", default_sort_key),
            ("read_states", read_states),
            ("course_stats", course_stats),
            ("active_flags", active_flags),
        ]
        update_data: dict[str, Any] = {
            field: value for field, value in fields if value is not None
        }

        result = self._collection.update_one(
            {"external_id": external_id},
            {"$set": update_data},
        )
        return result.modified_count
