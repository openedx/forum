"""
Native Python Threads APIs.
"""

import logging
from typing import Any, Optional

from django.core.exceptions import ObjectDoesNotExist
from rest_framework.serializers import ValidationError

from forum.api.users import mark_thread_as_read
from forum.backend import get_backend
from forum.serializers.thread import ThreadSerializer
from forum.utils import ForumV2RequestError, get_int_value_from_collection, str_to_bool

log = logging.getLogger(__name__)


def _get_thread_data_from_request_data(data: dict[str, Any]) -> dict[str, Any]:
    """convert request data to a dict excluding empty data"""
    fields = [
        "title",
        "body",
        "course_id",
        "anonymous",
        "anonymous_to_peers",
        "closed",
        "commentable_id",
        "thread_type",
        "edit_reason_code",
        "close_reason_code",
        "endorsed",
        "pinned",
        "group_id",
        "context",
    ]
    result = {field: data.get(field) for field in fields if data.get(field) is not None}

    # Handle special cases
    if "user_id" in data:
        result["author_id"] = data["user_id"]
    if "editing_user_id" in data:
        result["editing_user_id"] = data["editing_user_id"]
    if "closing_user_id" in data:
        result["closed_by_id"] = data["closing_user_id"]

    return result


def get_thread_data(thread: dict[str, Any]) -> dict[str, Any]:
    """Prepare thread data for the api response."""
    _type = str(thread.get("_type", "")).lower()
    thread_data = {
        **thread,
        "id": str(thread.get("_id")),
        "type": "thread" if _type.lower() == "commentthread" else _type,
        "user_id": thread.get("author_id"),
        "username": str(thread.get("author_username")),
        "comments_count": thread["comment_count"],
    }
    return thread_data


def prepare_thread_api_response(
    thread: dict[str, Any],
    backend: Any,
    include_context: Optional[bool] = False,
    data_or_params: Optional[dict[str, Any]] = None,
    include_data_from_params: Optional[bool] = False,
    course_id: Optional[str] = None,
) -> dict[str, Any]:
    """Serialize thread data for the api response."""
    thread_data = get_thread_data(thread)

    context = {}
    if include_context:
        context = {
            "include_endorsed": True,
            "include_read_state": True,
        }
        if data_or_params:
            if user_id := data_or_params.get("user_id"):
                context["user_id"] = user_id

            if include_data_from_params:
                thread_data["resp_skip"] = get_int_value_from_collection(
                    data_or_params, "resp_skip", 0
                )
                thread_data["resp_limit"] = get_int_value_from_collection(
                    data_or_params, "resp_limit", 100
                )
                params = [
                    "recursive",
                    "with_responses",
                    "mark_as_read",
                    "reverse_order",
                    "merge_question_type_responses",
                ]
                for param in params:
                    if value := data_or_params.get(param):
                        context[param] = str_to_bool(value)
                if user_id and backend.get_user(user_id):
                    mark_thread_as_read(user_id, thread["_id"], course_id=course_id)

    serializer = ThreadSerializer(
        data=thread_data,
        context=context,
        backend=backend,
    )
    if not serializer.is_valid(raise_exception=True):
        log.error(f"validation error in thread API call: {serializer.errors}")
        raise ValidationError(serializer.errors)

    return serializer.data


def get_thread(
    thread_id: str,
    params: Optional[dict[str, Any]] = None,
    course_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Get the thread for the given thread_id.

    Parameters:
        thread_id: The ID of the thread.
        user_id: The ID of the user requesting the thread.
        resp_skip: Number of responses to skip.
        resp_limit: Maximum number of responses to return.
        recursive: Whether to include nested responses.
        with_responses: Whether to include responses.
        mark_as_read: Whether to mark the thread as read.
        reverse_order: Whether to reverse the order of responses.
        merge_question_type_responses: Whether to merge question type responses.
    Response:
        The details of the thread for the given thread_id.
    """
    backend = get_backend(course_id)()
    try:
        thread = backend.validate_object("CommentThread", thread_id)
    except ObjectDoesNotExist as exc:
        log.error("Forumv2RequestError for get thread request.")
        raise ForumV2RequestError(
            f"Thread does not exist with Id: {thread_id}"
        ) from exc

    try:
        return prepare_thread_api_response(
            thread,
            backend,
            True,
            params,
            True,
            course_id=course_id,
        )
    except ValidationError as error:
        log.error(f"Validation error in get_thread: {error}")
        raise ForumV2RequestError("Failed to prepare thread API response") from error


def delete_thread(thread_id: str, course_id: Optional[str] = None) -> dict[str, Any]:
    """
    Delete the thread for the given thread_id.

    Parameters:
        thread_id: The ID of the thread to be deleted.
    Response:
        The details of the thread that is deleted.
    """
    backend = get_backend(course_id)()
    try:
        thread = backend.validate_object("CommentThread", thread_id)
    except ObjectDoesNotExist as exc:
        log.error("Forumv2RequestError for delete thread request.")
        raise ForumV2RequestError(
            f"Thread does not exist with Id: {thread_id}"
        ) from exc

    backend.delete_comments_of_a_thread(thread_id)
    thread = backend.validate_object("CommentThread", thread_id)

    try:
        serialized_data = prepare_thread_api_response(thread, backend)
    except ValidationError as error:
        log.error(f"Validation error in get_thread: {error}")
        raise ForumV2RequestError("Failed to prepare thread API response") from error

    backend.delete_subscriptions_of_a_thread(thread_id)
    result = backend.delete_thread(thread_id)
    if result and not (thread["anonymous"] or thread["anonymous_to_peers"]):
        backend.update_stats_for_course(
            thread["author_id"], thread["course_id"], threads=-1
        )

    return serialized_data


def update_thread(
    thread_id: str,
    title: Optional[str] = None,
    body: Optional[str] = None,
    course_id: Optional[str] = None,
    anonymous: Optional[bool] = None,
    anonymous_to_peers: Optional[bool] = None,
    closed: Optional[bool] = None,
    commentable_id: Optional[str] = None,
    user_id: Optional[str] = None,
    editing_user_id: Optional[str] = None,
    pinned: Optional[bool] = None,
    thread_type: Optional[str] = None,
    edit_reason_code: Optional[str] = None,
    close_reason_code: Optional[str] = None,
    closing_user_id: Optional[str] = None,
    endorsed: Optional[bool] = None,
) -> dict[str, Any]:
    """
    Update the thread for the given thread_id.

    Parameters:
        thread_id: The ID of the thread to be updated.
        data: The data to be updated.
    Response:
        The details of the thread that is updated.
    """
    backend = get_backend(course_id)()
    try:
        thread = backend.validate_object("CommentThread", thread_id)
    except ObjectDoesNotExist as exc:
        log.error("Forumv2RequestError for update thread request.")
        raise ForumV2RequestError(
            f"Thread does not exist with Id: {thread_id}"
        ) from exc

    data = {
        "title": title,
        "body": body,
        "anonymous": anonymous,
        "anonymous_to_peers": anonymous_to_peers,
        "closed": closed,
        "commentable_id": commentable_id,
        "user_id": user_id,
        "editing_user_id": editing_user_id,
        "pinned": pinned,
        "thread_type": thread_type,
        "edit_reason_code": edit_reason_code,
        "close_reason_code": close_reason_code,
        "closing_user_id": closing_user_id,
        "endorsed": endorsed,
    }
    update_thread_data: dict[str, Any] = _get_thread_data_from_request_data(data)

    if "body" in update_thread_data:
        update_thread_data["original_body"] = thread.get("body")

    if update_thread_data.get("closed"):
        missing_fields = {"close_reason_code", "closed_by_id"} - set(
            update_thread_data.keys()
        )
        if missing_fields:
            raise ForumV2RequestError(
                f"Missing required fields: {', '.join(missing_fields)}"
            )
    backend.update_thread(thread_id, **update_thread_data)
    thread = backend.get_thread(thread_id)
    if thread is None:
        log.error(
            "Forumv2RequestError for update thread request - retrieving updated thread to send in response."
        )
        raise ForumV2RequestError(f"Thread no longer exists with Id: {thread_id}")

    try:
        return prepare_thread_api_response(
            thread,
            backend,
            True,
            data,
        )
    except ValidationError as error:
        log.error(f"Validation error in get_thread: {error}")
        raise ForumV2RequestError("Failed to prepare thread API response") from error


def create_thread(
    title: str,
    body: str,
    course_id: str,
    user_id: str,
    anonymous: bool = False,
    anonymous_to_peers: bool = False,
    commentable_id: str = "course",
    thread_type: str = "discussion",
    group_id: Optional[int] = None,
    context: str = "course",
) -> dict[str, Any]:
    """
    Create a new thread.

    Parameters:
        title: The title of the thread.
        body: The body of the thread.
        course_id: The ID of the course.
        anonymous: Whether the thread is anonymous.
        anonymous_to_peers: Whether the thread is anonymous to peers.
        closed: Whether the thread is closed.
        commentable_id: The ID of the commentable.
        user_id: The ID of the user.
        group_id: The ID of the group.
    Response:
        The details of the thread that is created.
    """
    backend = get_backend(course_id)()
    data = {
        "title": title,
        "body": body,
        "course_id": course_id,
        "user_id": user_id,
        "anonymous": anonymous,
        "anonymous_to_peers": anonymous_to_peers,
        "commentable_id": commentable_id,
        "thread_type": thread_type,
        "group_id": group_id,
        "context": context,
    }
    thread_data: dict[str, Any] = _get_thread_data_from_request_data(data)

    thread_id = backend.create_thread(thread_data)
    thread = backend.get_thread(thread_id)
    if not thread:
        raise ForumV2RequestError(f"Failed to create thread with data: {data}")

    if not (anonymous or anonymous_to_peers):
        backend.update_stats_for_course(
            thread["author_id"], thread["course_id"], threads=1
        )

    try:
        return prepare_thread_api_response(
            thread,
            backend,
            True,
            data,
        )
    except ValidationError as error:
        log.error(f"Validation error in get_thread: {error}")
        raise ForumV2RequestError("Failed to prepare thread API response") from error


def get_user_threads(
    course_id: str,
    author_id: Optional[str] = None,
    thread_type: Optional[str] = None,
    flagged: Optional[bool] = None,
    unread: Optional[bool] = None,
    unanswered: Optional[bool] = None,
    unresponded: Optional[bool] = None,
    count_flagged: Optional[bool] = None,
    sort_key: Optional[str] = None,
    page: Optional[str] = None,
    per_page: Optional[str] = None,
    request_id: Optional[str] = None,
    commentable_ids: Optional[str] = None,
    user_id: Optional[str] = None,
    group_id: Optional[int] = None,
    group_ids: Optional[int] = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Get the threads for the given thread_ids.
    """
    backend = get_backend(course_id)()
    params = {
        "course_id": course_id,
        "author_id": author_id,
        "thread_type": thread_type,
        "flagged": flagged,
        "unread": unread,
        "unanswered": unanswered,
        "unresponded": unresponded,
        "count_flagged": count_flagged,
        "sort_key": sort_key,
        "page": int(page) if page else None,
        "per_page": int(per_page) if per_page else None,
        "request_id": request_id,
        "commentable_ids": commentable_ids,
        "user_id": user_id,
        "group_id": group_id,
        "group_ids": group_ids,
    }
    params = {k: v for k, v in params.items() if v is not None}
    backend.validate_params(params)

    thread_filter = backend.get_user_thread_filter(course_id)
    filtered_threads = backend.get_filtered_threads(thread_filter, ids_only=True)
    thread_ids = [thread["_id"] for thread in filtered_threads]
    threads = backend.get_threads(params, user_id or "", ThreadSerializer, thread_ids)

    return threads


def get_course_id_by_thread(thread_id: str) -> str | None:
    """
    Return course_id for the matching thread.
    It searches for thread_id both in mongodb and mysql.
    """
    #  pylint: disable=C0415
    from forum.backends.mongodb.api import MongoBackend
    from forum.backends.mysql.api import MySQLBackend

    return (
        MongoBackend.get_course_id_by_thread_id(thread_id)
        or MySQLBackend.get_course_id_by_thread_id(thread_id)
        or None
    )
