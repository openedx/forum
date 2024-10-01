"""
Native Python Comments APIs.
"""

import logging
from typing import Any, Optional

from django.core.exceptions import ObjectDoesNotExist
from rest_framework.serializers import ValidationError

from forum.backends.mongodb.api import (
    create_comment,
    delete_comment_by_id,
    get_thread_by_id,
    get_thread_id_by_comment_id,
    get_user_by_id,
    mark_as_read,
    update_comment_and_get_updated_comment,
    update_stats_for_course,
    validate_object,
)
from forum.backends.mongodb.comments import Comment
from forum.backends.mongodb.threads import CommentThread
from forum.serializers.comment import CommentSerializer
from forum.utils import ForumV2RequestError

log = logging.getLogger(__name__)


def prepare_comment_api_response(
    comment: dict[str, Any],
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
    )
    if not serializer.is_valid(raise_exception=True):
        raise ValidationError(serializer.errors)

    return serializer.data


def get_parent_comment(comment_id: str) -> dict[str, Any]:
    """
    Get a parent comment.

    Parameters:
        comment_id: The ID of the comment.
    Body:
        Empty.
    Response:
        The details of the comment for the given comment_id.
    """
    try:
        comment = validate_object(Comment, comment_id)
    except ObjectDoesNotExist as exc:
        log.error("Forumv2RequestError for get parent comment request.")
        raise ForumV2RequestError(
            f"Comment does not exists with Id: {comment_id}"
        ) from exc
    return prepare_comment_api_response(
        comment,
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
    try:
        parent_comment = validate_object(Comment, parent_comment_id)
    except ObjectDoesNotExist as exc:
        log.error("Forumv2RequestError for create child comment request.")
        raise ForumV2RequestError(
            f"Comment does not exists with Id: {parent_comment_id}"
        ) from exc

    comment = create_comment(
        body,
        user_id,
        course_id,
        anonymous,
        anonymous_to_peers,
        1,
        get_thread_id_by_comment_id(parent_comment_id),
        parent_id=parent_comment_id,
    )
    if not comment:
        log.error("Forumv2RequestError for create child comment request.")
        raise ForumV2RequestError("comment is not created")

    user = get_user_by_id(user_id)
    thread = get_thread_by_id(parent_comment["comment_thread_id"])
    if user and thread and comment:
        mark_as_read(user, thread)
    try:
        comment_data = prepare_comment_api_response(
            comment,
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
    try:
        validate_object(Comment, comment_id)
    except ObjectDoesNotExist as exc:
        log.error("Forumv2RequestError for update comment request.")
        raise ForumV2RequestError(
            f"Comment does not exists with Id: {comment_id}"
        ) from exc

    updated_comment = update_comment_and_get_updated_comment(
        comment_id,
        body,
        course_id,
        user_id,
        anonymous,
        anonymous_to_peers,
        endorsed,
        closed,
        editing_user_id,
        edit_reason_code,
        endorsement_user_id,
    )
    if not updated_comment:
        log.error("Forumv2RequestError for create child comment request.")
        raise ForumV2RequestError("comment is not updated")
    try:
        return prepare_comment_api_response(
            updated_comment,
            exclude_fields=(
                ["endorsement", "sk"] if updated_comment.get("parent_id") else ["sk"]
            ),
        )
    except ValidationError as error:
        raise error


def delete_comment(comment_id: str) -> dict[str, Any]:
    """
    Delete a comment.

    Parameters:
        comment_id: The ID of the comment to be deleted.
    Body:
        Empty.
    Response:
        The details of the comment that is deleted.
    """
    try:
        comment = validate_object(Comment, comment_id)
    except ObjectDoesNotExist as exc:
        log.error("Forumv2RequestError for delete comment request.")
        raise ForumV2RequestError(
            f"Comment does not exists with Id: {comment_id}"
        ) from exc
    data = prepare_comment_api_response(
        comment,
        exclude_fields=["endorsement", "sk"],
    )
    delete_comment_by_id(comment_id)
    author_id = comment["author_id"]
    course_id = comment["course_id"]
    parent_comment_id = data["parent_id"]
    if parent_comment_id:
        update_stats_for_course(author_id, course_id, replies=-1)
    else:
        update_stats_for_course(author_id, course_id, responses=-1)
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
    try:
        thread = validate_object(CommentThread, thread_id)
    except ObjectDoesNotExist as exc:
        log.error("Forumv2RequestError for create parent comment request.")
        raise ForumV2RequestError(
            f"Thread does not exists with Id: {thread_id}"
        ) from exc

    comment = create_comment(
        body,
        user_id,
        course_id,
        anonymous,
        anonymous_to_peers,
        0,
        thread_id=thread_id,
    )
    if not comment:
        log.error("Forumv2RequestError for create parent comment request.")
        raise ForumV2RequestError("comment is not created")
    user = get_user_by_id(user_id)
    if user and comment:
        mark_as_read(user, thread)
    try:
        return prepare_comment_api_response(
            comment,
            exclude_fields=["endorsement", "sk"],
        )
    except ValidationError as error:
        raise error