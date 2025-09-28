"""
API for search.
"""

from typing import Any, Optional

from forum.backend import get_backend
from forum.constants import FORUM_DEFAULT_PAGE, FORUM_DEFAULT_PER_PAGE
from forum.search import get_thread_search_backend
from forum.serializers.thread import ThreadSerializer


def _get_thread_ids_from_indexes(
    context: str,
    group_ids: list[int],
    text: str,
    commentable_ids: Optional[list[str]] = None,
    course_id: Optional[str] = None,
) -> tuple[list[str], Optional[str]]:
    """
    Retrieve thread IDs based on the search text and suggested corrections if necessary.

    Args:
        context (str): The context in which the search is performed, e.g., "course".
        group_ids (list[int]): list of group IDs to filter the search.
        params (dict[str, Any]): Query parameters for the search.
        text (str): The search text used to find threads.

    Returns:
        tuple[Optional[list[str]], Optional[str]]:
            - A list of thread IDs that match the search criteria.
            - A suggested correction for the search text, or None if no correction is found.
    """
    corrected_text: Optional[str] = None
    thread_search = get_thread_search_backend()

    thread_ids = thread_search.get_thread_ids(
        context,
        group_ids,
        text,
        commentable_ids=commentable_ids,
        course_id=course_id,
    )
    if not thread_ids:
        corrected_text = thread_search.get_suggested_text(text)
        if corrected_text:
            thread_ids = thread_search.get_thread_ids_with_corrected_text(
                context,
                group_ids,
                corrected_text,
                commentable_ids=commentable_ids,
                course_id=course_id,
            )
        if not thread_ids:
            corrected_text = None

    return thread_ids, corrected_text


def search_threads(
    text: str,
    user_id: str,
    course_id: str,
    group_ids: Optional[list[int]] = None,
    commentable_ids: Optional[list[str]] = None,
    author_id: Optional[str] = None,
    thread_type: Optional[str] = None,
    sort_key: str = "date",
    context: str = "course",
    flagged: bool = False,
    unread: bool = False,
    unanswered: bool = False,
    unresponded: bool = False,
    count_flagged: bool = False,
    page: int = FORUM_DEFAULT_PAGE,
    per_page: int = FORUM_DEFAULT_PER_PAGE,
    is_moderator: bool = False,
) -> dict[str, Any]:
    """
    Search for threads based on the provided data.
    """
    group_ids = group_ids or []
    commentable_ids = commentable_ids or []

    thread_ids, corrected_text = _get_thread_ids_from_indexes(
        context, group_ids, text, commentable_ids, course_id
    )

    backend = get_backend(course_id)()

    data = backend.handle_threads_query(
        thread_ids,
        user_id,
        course_id,
        group_ids,
        author_id,
        thread_type,
        flagged,
        unread,
        unanswered,
        unresponded,
        count_flagged,
        sort_key,
        page,
        per_page,
        context,
        raw_query=False,
        commentable_ids=commentable_ids,
        is_moderator=is_moderator,
    )

    if collections := data.get("collection"):
        thread_serializer = ThreadSerializer(
            collections,
            many=True,
            context={
                "count_flagged": True,
                "include_endorsed": True,
                "include_read_state": True,
            },
            backend=backend,
        )
        data["collection"] = thread_serializer.data

    if data:
        data["corrected_text"] = corrected_text
        data["total_results"] = len(thread_ids)

    return data
