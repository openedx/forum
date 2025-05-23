"""
This module contains the functions to update the flag status of a comment.
"""

from typing import Any, Optional

from forum.backends.mysql.api import MySQLBackend as backend
from forum.serializers.comment import CommentSerializer
from forum.serializers.thread import ThreadSerializer
from forum.utils import ForumV2RequestError


def update_comment_flag(
    comment_id: str,
    action: str,
    user_id: Optional[str] = None,
    update_all: Optional[bool] = False,
) -> dict[str, Any]:
    """
    Update the flag status of a comment.

    Args:
        user_id (str): The ID of the user.
        comment_id (str): The ID of the comment.
        action (str): The action to perform ("flag" or "unflag").
        update_all (bool, optional): Whether to update all flags. Defaults to False.
    """
    if not user_id:
        raise ForumV2RequestError("user_id not provided in params")
    user = backend.get_user(user_id)
    try:
        comment = backend.get_comment(comment_id)
    except ValueError as exc:
        raise ForumV2RequestError("User / Comment doesn't exist") from exc
    if not user or not comment:
        raise ForumV2RequestError("User / Comment doesn't exist")

    if action == "flag":
        updated_comment = backend.flag_as_abuse(
            user_id, comment_id, entity_type="Comment"
        )
    elif action == "unflag":
        if update_all:
            updated_comment = backend.un_flag_all_as_abuse(
                comment_id, entity_type="Comment"
            )
        else:
            updated_comment = backend.un_flag_as_abuse(
                user_id, comment_id, entity_type="Comment"
            )
    else:
        raise ForumV2RequestError("Invalid action")

    if updated_comment is None:
        raise ForumV2RequestError("Failed to update comment")

    context = {
        "id": updated_comment["_id"],
        **updated_comment,
        "user_id": user["_id"],
        "username": user["username"],
        "type": "comment",
        "comment_thread_id": str(updated_comment.get("comment_thread_id", None)),
    }
    return CommentSerializer(context, backend=backend).data


def update_thread_flag(
    thread_id: str,
    action: str,
    user_id: Optional[str] = None,
    update_all: Optional[bool] = False,
) -> dict[str, Any]:
    """
    Update the flag status of a thread.

    Args:
        user_id (str): The ID of the user.
        thread_id (str): The ID of the thread.
        action (str): The action to perform ("flag" or "unflag").
        update_all (bool, optional): Whether to update all flags. Defaults to False.
    """
    if not user_id:
        raise ForumV2RequestError("user_id not provided in params")
    user = backend.get_user(user_id)
    thread = backend.get_thread(thread_id)
    if not user or not thread:
        raise ForumV2RequestError("User / Thread doesn't exist")

    if action == "flag":
        updated_thread = backend.flag_as_abuse(
            user_id, thread_id, entity_type="CommentThread"
        )
    elif action == "unflag":
        if update_all:
            updated_thread = backend.un_flag_all_as_abuse(
                thread_id, entity_type="CommentThread"
            )
        else:
            updated_thread = backend.un_flag_as_abuse(
                user_id, thread_id, entity_type="CommentThread"
            )
    else:
        raise ForumV2RequestError("Invalid action")

    if updated_thread is None:
        raise ForumV2RequestError("Failed to update thread")

    context = {
        "id": str(updated_thread["_id"]),
        **updated_thread,
        "user_id": user["_id"],
        "username": user["username"],
        "type": "thread",
        "thread_id": str(updated_thread.get("comment_thread_id", None)),
    }
    return ThreadSerializer(context, backend=backend).data
