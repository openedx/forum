"""Forum backend interface class."""

from typing import Any, Optional


class AbstractBackend:
    """Abstract backend interface class."""

    @classmethod
    def update_stats_for_course(
        cls, user_id: str, course_id: str, **kwargs: Any
    ) -> None:
        """Update statistics for a course."""
        raise NotImplementedError

    @classmethod
    def flag_as_abuse(
        cls, user_id: str, entity_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        """Flag an entity as abuse."""
        raise NotImplementedError

    @classmethod
    def update_stats_after_unflag(
        cls, user_id: str, entity_id: str, has_no_historical_flags: bool, **kwargs: Any
    ) -> None:
        """Update statistics after unflagging an entity."""
        raise NotImplementedError

    @classmethod
    def un_flag_as_abuse(
        cls, user_id: str, entity_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        """Unflag an entity as abuse."""
        raise NotImplementedError

    @classmethod
    def un_flag_all_as_abuse(cls, entity_id: str, **kwargs: Any) -> dict[str, Any]:
        """Unflag all entities as abuse."""
        raise NotImplementedError

    @staticmethod
    def update_vote(
        content_id: str,
        user_id: str,
        vote_type: str = "",
        is_deleted: bool = False,
        **kwargs: Any
    ) -> bool:
        """Update vote for a content."""
        raise NotImplementedError

    @classmethod
    def upvote_content(cls, entity_id: str, user_id: str, **kwargs: Any) -> bool:
        """Upvote a content."""
        raise NotImplementedError

    @classmethod
    def downvote_content(cls, entity_id: str, user_id: str, **kwargs: Any) -> bool:
        """Downvote a content."""
        raise NotImplementedError

    @classmethod
    def remove_vote(cls, entity_id: str, user_id: str, **kwargs: Any) -> bool:
        """Remove a vote for a content."""
        raise NotImplementedError

    @staticmethod
    def validate_thread_and_user(
        user_id: str, thread_id: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Validate a thread and user."""
        raise NotImplementedError

    @staticmethod
    def pin_unpin_thread(thread_id: str, action: str) -> None:
        """Pin or unpin a thread."""
        raise NotImplementedError

    @staticmethod
    def get_pinned_unpinned_thread_serialized_data(
        user_id: str, thread_id: str, serializer_class: Any
    ) -> dict[str, Any]:
        """Get pinned or unpinned thread serialized data."""
        raise NotImplementedError

    @classmethod
    def handle_pin_unpin_thread_request(
        cls, user_id: str, thread_id: str, action: str, serializer_class: Any
    ) -> dict[str, Any]:
        """Handle pin or unpin thread request."""
        raise NotImplementedError

    @staticmethod
    def get_abuse_flagged_count(thread_ids: list[str]) -> dict[str, int]:
        """Get abuse flagged count."""
        raise NotImplementedError

    @staticmethod
    def get_read_states(
        thread_ids: list[str], user_id: str, course_id: str
    ) -> dict[str, list[Any]]:
        """Get read states."""
        raise NotImplementedError

    @staticmethod
    def get_endorsed(thread_ids: list[str]) -> dict[str, bool]:
        """Get endorsed."""
        raise NotImplementedError

    @staticmethod
    def get_user_read_state_by_course_id(
        user_id: str, course_id: str
    ) -> dict[str, Any]:
        """Get user read state by course id."""
        raise NotImplementedError

    @classmethod
    def handle_threads_query(
        cls,
        comment_thread_ids: list[str],
        user_id: str,
        course_id: str,
        group_ids: list[int],
        author_id: Optional[str],
        thread_type: Optional[str],
        filter_flagged: bool,
        filter_unread: bool,
        filter_unanswered: bool,
        filter_unresponded: bool,
        count_flagged: bool,
        sort_key: str,
        page: int,
        per_page: int,
        context: str = "course",
        raw_query: bool = False,
        commentable_ids: Optional[list[str]] = None,
        is_moderator: bool = False,
    ) -> dict[str, Any]:
        """Handle threads query."""
        raise NotImplementedError

    @staticmethod
    def prepare_thread(
        thread_id: str,
        is_read: bool,
        unread_count: int,
        is_endorsed: bool,
        abuse_flagged_count: int,
    ) -> dict[str, Any]:
        """Prepare thread."""
        raise NotImplementedError

    @classmethod
    def threads_presentor(
        cls,
        thread_ids: list[str],
        user_id: str,
        course_id: str,
        count_flagged: bool = False,
    ) -> list[dict[str, Any]]:
        """Threads presenter."""
        raise NotImplementedError

    @staticmethod
    def get_username_from_id(user_id: str) -> Optional[str]:
        """Get username from id."""
        raise NotImplementedError

    @staticmethod
    def validate_object(model: str, obj_id: str) -> Any:
        """Validate object."""
        raise NotImplementedError

    @staticmethod
    def find_subscribed_threads(
        user_id: str, course_id: Optional[str] = None
    ) -> list[str]:
        """Find subscribed threads."""
        raise NotImplementedError

    @staticmethod
    def subscribe_user(
        user_id: str, source_id: str, source_type: str
    ) -> dict[str, Any] | None:
        """Subscribe user."""
        raise NotImplementedError

    @staticmethod
    def unsubscribe_user(user_id: str, source_id: str, source_type: str) -> None:
        """Unsubscribe user."""
        raise NotImplementedError

    @staticmethod
    def delete_comments_of_a_thread(thread_id: str) -> None:
        """Delete comments of a thread."""
        raise NotImplementedError

    @staticmethod
    def delete_subscriptions_of_a_thread(thread_id: str) -> None:
        """Delete subscriptions of a thread."""
        raise NotImplementedError

    @staticmethod
    def validate_params(params: dict[str, Any], user_id: Optional[str] = None) -> Any:
        """Validate params."""
        raise NotImplementedError

    @classmethod
    def get_threads(
        cls,
        params: dict[str, Any],
        user_id: str,
        serializer: Any,
        thread_ids: list[str],
    ) -> dict[str, Any]:
        """Get threads."""
        raise NotImplementedError

    @staticmethod
    def get_commentables_counts_based_on_type(course_id: str) -> dict[str, Any]:
        """Get commentables counts based on type."""
        raise NotImplementedError

    @classmethod
    def get_user_voted_ids(cls, user_id: str, vote: str) -> list[str]:
        """Get user voted ids."""
        raise NotImplementedError

    @staticmethod
    def filter_standalone_threads(comment_ids: list[str]) -> list[str]:
        """Filter standalone threads."""
        raise NotImplementedError

    @classmethod
    def user_to_hash(
        cls, user_id: str, params: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """User to hash."""
        raise NotImplementedError

    @staticmethod
    def replace_username_in_all_content(user_id: str, username: str) -> None:
        """Replace username in all content."""
        raise NotImplementedError

    @staticmethod
    def unsubscribe_all(user_id: str) -> None:
        """Unsubscribe all."""
        raise NotImplementedError

    @staticmethod
    def retire_all_content(user_id: str, username: str) -> None:
        """Retire all content."""
        raise NotImplementedError

    @staticmethod
    def find_or_create_read_state(user_id: str, thread_id: str) -> dict[str, Any]:
        """Find or create read state."""
        raise NotImplementedError

    @classmethod
    def mark_as_read(cls, user_id: str, thread_id: str) -> None:
        """Mark as read."""
        raise NotImplementedError

    @staticmethod
    def find_or_create_user_stats(user_id: str, course_id: str) -> dict[str, Any]:
        """Find or create user stats."""
        raise NotImplementedError

    @staticmethod
    def update_user_stats_for_course(user_id: str, stat: dict[str, Any]) -> None:
        """Update user stats for course."""
        raise NotImplementedError

    @classmethod
    def build_course_stats(cls, author_id: str, course_id: str) -> None:
        """Build course stats."""
        raise NotImplementedError

    @classmethod
    def update_all_users_in_course(cls, course_id: str) -> list[str]:
        """Update all users in course."""
        raise NotImplementedError

    @staticmethod
    def get_user_by_username(username: str | None) -> dict[str, Any] | None:
        """Get user by username."""
        raise NotImplementedError

    @staticmethod
    def find_or_create_user(
        user_id: str, username: Optional[str] = "", default_sort_key: Optional[str] = ""
    ) -> str:
        """Find or create user."""
        raise NotImplementedError

    @staticmethod
    def get_comment(comment_id: str) -> dict[str, Any] | None:
        """Get comment."""
        raise NotImplementedError

    @staticmethod
    def get_thread(thread_id: str) -> dict[str, Any] | None:
        """Get thread."""
        raise NotImplementedError

    @staticmethod
    def get_comments(**kwargs: Any) -> list[dict[str, Any]]:
        """Get comments."""
        raise NotImplementedError

    @staticmethod
    def get_comments_count(**kwargs: Any) -> int:
        """Get comments count."""
        raise NotImplementedError

    @classmethod
    def create_comment(cls, data: dict[str, Any]) -> Any:
        """Create comment."""
        raise NotImplementedError

    @staticmethod
    def delete_comment(comment_id: str) -> None:
        """Delete comment."""
        raise NotImplementedError

    @staticmethod
    def update_comment(comment_id: str, **kwargs: Any) -> int:
        """Update comment."""
        raise NotImplementedError

    @staticmethod
    def get_thread_id_from_comment(comment_id: str) -> dict[str, Any] | None:
        """Get thread id from comment."""
        raise NotImplementedError

    @staticmethod
    def get_user(user_id: str, get_full_dict: bool = True) -> dict[str, Any] | None:
        """Get user."""
        raise NotImplementedError

    @staticmethod
    def get_subscription(
        subscriber_id: str, source_id: str, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Get subscription."""
        raise NotImplementedError

    @staticmethod
    def get_subscriptions(query: dict[str, Any]) -> list[dict[str, Any]]:
        """Get subscriptions."""
        raise NotImplementedError

    @staticmethod
    def delete_thread(thread_id: str) -> int:
        """Delete thread."""
        raise NotImplementedError

    @staticmethod
    def create_thread(data: dict[str, Any]) -> str:
        """Create thread."""
        raise NotImplementedError

    @staticmethod
    def update_thread(thread_id: str, **kwargs: Any) -> int:
        """Update thread."""
        raise NotImplementedError

    @staticmethod
    def get_filtered_threads(
        query: dict[str, Any], ids_only: bool = False
    ) -> list[dict[str, Any]]:
        """Get filtered threads."""
        raise NotImplementedError

    @staticmethod
    def update_user(user_id: str, data: dict[str, Any]) -> int:
        """Update user."""
        raise NotImplementedError

    @staticmethod
    def get_thread_id_by_comment_id(parent_comment_id: str) -> str:
        """
        The thread Id from the parent comment.
        """
        raise NotImplementedError

    @staticmethod
    def update_comment_and_get_updated_comment(
        comment_id: str,
        body: Optional[str] = None,
        course_id: Optional[str] = None,
        user_id: Optional[str] = None,
        anonymous: Optional[bool] = False,
        anonymous_to_peers: Optional[bool] = False,
        endorsed: Optional[bool] = False,
        closed: Optional[bool] = False,
        editing_user_id: Optional[str] = None,
        edit_reason_code: Optional[str] = None,
        endorsement_user_id: Optional[str] = None,
    ) -> dict[str, Any] | None:
        """Update comment and get updated comment."""
        raise NotImplementedError

    @staticmethod
    def get_contents(**kwargs: Any) -> list[dict[str, Any]]:
        """Get contents."""
        raise NotImplementedError

    @staticmethod
    def get_users(**kwargs: Any) -> list[dict[str, Any]]:
        """Get users."""
        raise NotImplementedError

    @staticmethod
    def get_user_sort_criterion(sort_by: str) -> dict[str, Any]:
        """Get sort criterion."""
        raise NotImplementedError

    @staticmethod
    def get_thread_index_name() -> str:
        """Get the name of the thread index."""
        return "comment_threads"

    @staticmethod
    def get_votes_dict(up: list[str], down: list[str]) -> dict[str, Any]:
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

    @staticmethod
    def find_thread(**kwargs: Any) -> Optional[dict[str, Any]]:
        """
        Retrieves a first matching thread from the database.
        """
        raise NotImplementedError

    @staticmethod
    def find_comment(
        is_parent_comment: bool = True, with_abuse_flaggers: bool = False, **kwargs: Any
    ) -> Optional[dict[str, Any]]:
        """
        Retrieves a first matching comment from the database.
        """
        raise NotImplementedError

    @staticmethod
    def get_user_contents_by_username(username: str) -> list[dict[str, Any]]:
        """
        Retrieve all threads and comments authored by a specific user.
        """
        raise NotImplementedError
