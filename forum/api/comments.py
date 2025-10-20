"""
Native Python Comments APIs.
"""

import logging
import math
from typing import Any, Optional

from django.core.exceptions import ObjectDoesNotExist
from rest_framework.serializers import ValidationError

from forum.backend import get_backend
from forum.serializers.comment import CommentSerializer
from forum.utils import ForumV2RequestError

log = logging.getLogger(__name__)


def prepare_comment_api_response(
    comment: dict[str, Any],
    backend: Any,
    exclude_fields: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    Return serialized validated data.

    Parameters:
        comment: The comment details that needs to be serialized.
        exclude_fields: Any fields that need to be excluded from response.

    Response:
        serialized validated data of the comment.
    """
    comment_data = {
        **comment,
        "id": str(comment.get("_id")),
        "user_id": comment.get("author_id"),
        "thread_id": str(comment.get("comment_thread_id")),
        "username": comment.get("author_username"),
        "parent_id": str(comment.get("parent_id")),
        "type": str(comment.get("_type", "")).lower(),
    }
    if not exclude_fields:
        exclude_fields = []
    exclude_fields.append("children")
    serializer = CommentSerializer(
        data=comment_data,
        exclude_fields=exclude_fields,
        backend=backend,
    )
    if not serializer.is_valid(raise_exception=True):
        raise ValidationError(serializer.errors)

    return serializer.data


def get_parent_comment(
    comment_id: str, course_id: Optional[str] = None
) -> dict[str, Any]:
    """
    Get a parent comment.

    Parameters:
        comment_id: The ID of the comment.
    Body:
        Empty.
    Response:
        The details of the comment for the given comment_id.
    """
    backend = get_backend(course_id)()
    try:
        comment = backend.validate_object("Comment", comment_id)
    except ObjectDoesNotExist as exc:
        log.error("Forumv2RequestError for get parent comment request.")
        raise ForumV2RequestError(
            f"Comment does not exists with Id: {comment_id}"
        ) from exc
    return prepare_comment_api_response(
        comment,
        backend,
        exclude_fields=["sk"],
    )


def create_child_comment(
    parent_comment_id: str,
    body: str,
    user_id: str,
    course_id: str,
    anonymous: bool,
    anonymous_to_peers: bool,
) -> dict[str, Any]:
    """
    Create a new child comment.

    Parameters:
        comment_id: The ID of the parent comment for creating it's child comment.
        body: The content of the comment.
        course_id: The Id of the respective course.
        user_id: The requesting user id.
        anonymous: anonymous flag(True or False).
        anonymous_to_peers: anonymous to peers flag(True or False).
    Response:
        The details of the comment that is created.
    """
    backend = get_backend(course_id)()
    try:
        parent_comment = backend.validate_object("Comment", parent_comment_id)
    except ObjectDoesNotExist as exc:
        log.error("Forumv2RequestError for create child comment request.")
        raise ForumV2RequestError(
            f"Comment does not exists with Id: {parent_comment_id}"
        ) from exc

    comment_id = backend.create_comment(
        {
            "body": body,
            "author_id": user_id,
            "course_id": course_id,
            "anonymous": anonymous,
            "anonymous_to_peers": anonymous_to_peers,
            "depth": 1,
            "comment_thread_id": backend.get_thread_id_by_comment_id(parent_comment_id),
            "parent_id": parent_comment_id,
        }
    )
    comment = backend.get_comment(comment_id)
    if not comment:
        log.error("Forumv2RequestError for create child comment request.")
        raise ForumV2RequestError("comment is not created")

    user = backend.get_user(user_id)
    thread = backend.get_thread(parent_comment["comment_thread_id"])
    if user and thread and comment:
        backend.mark_as_read(user_id, parent_comment["comment_thread_id"])
    try:
        comment_data = prepare_comment_api_response(
            comment,
            backend,
            exclude_fields=["endorsement", "sk"],
        )
        return comment_data
    except ValidationError as error:
        raise error


def update_comment(
    comment_id: str,
    body: Optional[str] = None,
    course_id: Optional[str] = None,
    user_id: Optional[str] = None,
    anonymous: Optional[bool] = None,
    anonymous_to_peers: Optional[bool] = None,
    endorsed: Optional[bool] = None,
    closed: Optional[bool] = None,
    editing_user_id: Optional[str] = None,
    edit_reason_code: Optional[str] = None,
    endorsement_user_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Update an existing child/parent comment.

    Parameters:
        comment_id: The ID of the comment to be edited.
        body (Optional[str]): The content of the comment.
        course_id (Optional[str]): The Id of the respective course.
        user_id (Optional[str]): The requesting user id.
        anonymous (Optional[bool]): anonymous flag(True or False).
        anonymous_to_peers (Optional[bool]): anonymous to peers flag(True or False).
        endorsed (Optional[bool]): Flag indicating if the comment is endorsed by any user.
        closed (Optional[bool]): Flag indicating if the comment thread is closed.
        editing_user_id (Optional[str]): The ID of the user editing the comment.
        edit_reason_code (Optional[str]): The reason for editing the comment, typically represented by a code.
        endorsement_user_id (Optional[str]): The ID of the user endorsing the comment.
    Response:
        The details of the comment that is updated.
    """
    backend = get_backend(course_id)()
    try:
        backend.validate_object("Comment", comment_id)
    except ObjectDoesNotExist as exc:
        log.error("Forumv2RequestError for update comment request.")
        raise ForumV2RequestError(
            f"Comment does not exists with Id: {comment_id}"
        ) from exc

    updated_comment = backend.update_comment_and_get_updated_comment(
        comment_id,
        body=body,
        user_id=user_id,
        anonymous=anonymous,
        anonymous_to_peers=anonymous_to_peers,
        endorsed=endorsed,
        closed=closed,
        editing_user_id=editing_user_id,
        edit_reason_code=edit_reason_code,
        endorsement_user_id=endorsement_user_id,
    )
    if not updated_comment:
        log.error("Forumv2RequestError for create child comment request.")
        raise ForumV2RequestError("comment is not updated")
    try:
        return prepare_comment_api_response(
            updated_comment,
            backend,
            exclude_fields=(
                ["endorsement", "sk"] if updated_comment.get("parent_id") else ["sk"]
            ),
        )
    except ValidationError as error:
        raise error


def delete_comment(comment_id: str, course_id: Optional[str] = None) -> dict[str, Any]:
    """
    Delete a comment.

    Parameters:
        comment_id: The ID of the comment to be deleted.
    Body:
        Empty.
    Response:
        The details of the comment that is deleted.
    """
    backend = get_backend(course_id)()
    try:
        comment = backend.validate_object("Comment", comment_id)
    except ObjectDoesNotExist as exc:
        log.error("Forumv2RequestError for delete comment request.")
        raise ForumV2RequestError(
            f"Comment does not exists with Id: {comment_id}"
        ) from exc
    data = prepare_comment_api_response(
        comment,
        backend,
        exclude_fields=["endorsement", "sk"],
    )
    backend.delete_comment(comment_id)
    author_id = comment["author_id"]
    comment_course_id = comment["course_id"]
    parent_comment_id = data["parent_id"]
    if parent_comment_id:
        backend.update_stats_for_course(author_id, comment_course_id, replies=-1)
    else:
        backend.update_stats_for_course(author_id, comment_course_id, responses=-1)
    return data


def create_parent_comment(
    thread_id: str,
    body: str,
    user_id: str,
    course_id: str,
    anonymous: bool,
    anonymous_to_peers: bool,
) -> dict[str, Any]:
    """
    Create a new parent comment.

    Parameters:
        thread_id: The ID of the thread for creating a comment on it.
        body: The content of the comment.
        course_id: The Id of the respective course.
        user_id: The requesting user id.
        anonymous: anonymous flag(True or False).
        anonymous_to_peers: anonymous to peers flag(True or False).
    Response:
        The details of the comment that is created.
    """
    backend = get_backend(course_id)()
    try:
        backend.validate_object("CommentThread", thread_id)
    except ObjectDoesNotExist as exc:
        log.error("Forumv2RequestError for create parent comment request.")
        raise ForumV2RequestError(
            f"Thread does not exists with Id: {thread_id}"
        ) from exc

    comment_id = backend.create_comment(
        {
            "body": body,
            "author_id": user_id,
            "course_id": course_id,
            "anonymous": anonymous,
            "anonymous_to_peers": anonymous_to_peers,
            "depth": 0,
            "comment_thread_id": thread_id,
        }
    )
    if not comment_id:
        log.error("Forumv2RequestError for create parent comment request.")
        raise ForumV2RequestError("comment is not created")
    comment = backend.get_comment(comment_id) or {}
    user = backend.get_user(user_id)
    if user and comment:
        backend.mark_as_read(user_id, thread_id)
    try:
        return prepare_comment_api_response(
            comment,
            backend,
            exclude_fields=["endorsement", "sk"],
        )
    except ValidationError as error:
        raise error


def get_course_id_by_comment(comment_id: str) -> str | None:
    """
    Return course_id for the matching comment.
    It searches for comment_id both in mongodb and mysql.
    """
    #  pylint: disable=C0415
    from forum.backends.mongodb.api import MongoBackend
    from forum.backends.mysql.api import MySQLBackend

    return (
        MongoBackend.get_course_id_by_comment_id(comment_id)
        or MySQLBackend.get_course_id_by_comment_id(comment_id)
        or None
    )


def get_user_comments(
    user_id: str,
    course_id: str,
    flagged: Optional[bool] = False,
    page: int = 1,
    per_page: int = 10,
) -> dict[str, Any]:
    """
    Get all comments made by a user in a specific course.

    Args:
        user_id: The ID of the user
        course_id: The ID of the course
        flagged: Filter for flagged comments
        page: Page number for pagination
        per_page: Number of items per page

    Returns:
        A dictionary containing paginated comment results
    """

    backend = get_backend(course_id)()

    # Build query parameters
    query_params: dict[str, Any] = {
        "author_id": str(user_id),
        "course_id": course_id,
    }

    if flagged:
        query_params["abuse_flaggers"] = {"$ne": [], "$exists": True}

    # Get total count
    comment_count = backend.get_comments_count(**query_params)

    # Calculate pagination
    num_pages = max(1, math.ceil(comment_count / per_page))
    skip = (page - 1) * per_page

    # Get paginated comments
    query_params["resp_skip"] = skip
    query_params["resp_limit"] = per_page
    query_params["sort"] = -1  # Sort by newest first

    comments = backend.get_comments(**query_params)

    return {
        "collection": comments,
        "comment_count": comment_count,
        "num_pages": num_pages,
        "page": page,
    }
