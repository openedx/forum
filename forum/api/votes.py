"""
API for votes.
"""

from typing import Any

from forum.backends.mysql.api import MySQLBackend as backend
from forum.serializers.comment import CommentSerializer
from forum.serializers.thread import ThreadSerializer
from forum.serializers.votes import VotesInputSerializer
from forum.utils import ForumV2RequestError


def _get_thread_and_user(
    thread_id: str, user_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Fetches the thread and user based on provided IDs.

    Args:
        thread_id (str): The ID of the thread.
        user_id (str): The ID of the user.

    Returns:
        tuple: The thread and user objects.

    Raises:
        ValueError: If the thread or user is not found.
    """
    thread = backend.get_thread(thread_id)
    if not thread:
        raise ValueError("Thread not found")

    user = backend.get_user(user_id)
    if not user:
        raise ValueError("User not found")

    return thread, user


def _prepare_thread_response(
    thread: dict[str, Any], user: dict[str, Any]
) -> dict[str, Any]:
    """
    Prepares the serialized response data after voting.

    Args:
        thread (dict): The thread data.
        user (dict): The user data.

    Returns:
        dict: The serialized response data.

    Raises:
        ValueError: If serialization fails.
    """
    context = {
        "id": str(thread["_id"]),
        **thread,
        "user_id": user["_id"],
        "username": user["username"],
        "type": "thread",
    }
    serializer = ThreadSerializer(data=context, backend=backend)
    if not serializer.is_valid():
        raise ValueError(serializer.errors)
    return serializer.data


def update_thread_votes(thread_id: str, user_id: str, value: str) -> dict[str, Any]:
    """
    Updates the votes for a thread.

    Args:
        thread_id (str): The ID of the thread.
        user_id (str): The ID of the user.
        value (str): The vote value ("up" or "down").
    """
    data = {"user_id": user_id, "value": value}
    vote_serializer = VotesInputSerializer(data=data)

    if not vote_serializer.is_valid():
        raise ForumV2RequestError(vote_serializer.errors)

    try:
        thread, user = _get_thread_and_user(thread_id, user_id)
    except ValueError as error:
        raise ForumV2RequestError(str(error)) from error

    if vote_serializer.data["value"] == "up":
        is_updated = backend.upvote_content(
            thread_id, user_id, entity_type="CommentThread"
        )
    else:
        is_updated = backend.downvote_content(
            thread_id, user_id, entity_type="CommentThread"
        )

    if is_updated:
        thread = backend.get_thread(thread_id) or {}

    return _prepare_thread_response(thread, user)


def delete_thread_vote(thread_id: str, user_id: str) -> dict[str, Any]:
    """
    Deletes the vote for a thread.

    Args:
        thread_id (str): The ID of the thread.
        user_id (str): The ID of the user.
    """
    try:
        _, user = _get_thread_and_user(thread_id, user_id)
    except ValueError as error:
        raise ForumV2RequestError(str(error)) from error

    deleted_thread = None
    if backend.remove_vote(thread_id, user_id, entity_type="CommentThread"):
        deleted_thread = backend.get_thread(thread_id)

    if not deleted_thread:
        raise ForumV2RequestError("Thread not found")

    return _prepare_thread_response(deleted_thread, user)


def _get_comment_and_user(
    comment_id: str, user_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Fetches the comment and user based on provided IDs.

    Args:
        comment_id (str): The ID of the comment.
        user_id (str): The ID of the user.

    Returns:
        tuple: The comment and user objects.

    Raises:
        ValueError: If the comment or user is not found.
    """
    comment = backend.get_comment(comment_id)
    if not comment:
        raise ValueError("Comment not found")

    user = backend.get_user(user_id)
    if not user:
        raise ValueError("User not found")

    return comment, user


def _prepare_comment_response(
    comment: dict[str, Any], user: dict[str, Any]
) -> dict[str, Any]:
    """
    Prepares the serialized response data after voting.

    Args:
        comment (dict): The comment data.
        user (dict): The user data.

    Returns:
        dict: The serialized response data.

    Raises:
        ValueError: If serialization fails.
    """
    context = {
        "id": str(comment["_id"]),
        **comment,
        "user_id": user["_id"],
        "username": user["username"],
        "type": "comment",
        "thread_id": str(comment.get("comment_thread_id", None)),
    }
    serializer = CommentSerializer(data=context, backend=backend)
    if not serializer.is_valid():
        raise ValueError(serializer.errors)
    return serializer.data


def update_comment_votes(comment_id: str, user_id: str, value: str) -> dict[str, Any]:
    """
    Updates the votes for a comment.

    Args:
        comment_id (str): The ID of the comment.
        user_id (str): The ID of the user.
        value (str): The vote value ("up" or "down").
    """
    data = {"user_id": user_id, "value": value}
    vote_serializer = VotesInputSerializer(data=data)

    if not vote_serializer.is_valid():
        raise ForumV2RequestError(vote_serializer.errors)

    try:
        _, user = _get_comment_and_user(comment_id, user_id)
    except ValueError as error:
        raise ForumV2RequestError(str(error)) from error

    if vote_serializer.data["value"] == "up":
        is_updated = backend.upvote_content(comment_id, user_id, entity_type="Comment")
    else:
        is_updated = backend.downvote_content(
            comment_id, user_id, entity_type="Comment"
        )

    updated_comment = None
    if is_updated:
        updated_comment = backend.get_comment(comment_id)

    if not updated_comment:
        raise ForumV2RequestError("Comment not found")

    return _prepare_comment_response(updated_comment, user)


def delete_comment_vote(comment_id: str, user_id: str) -> dict[str, Any]:
    """
    Deletes the vote for a comment.

    Args:
        comment_id (str): The ID of the comment.
        user_id (str): The ID of the user.
    """
    try:
        _, user = _get_comment_and_user(comment_id, user_id)
    except ValueError as error:
        raise ForumV2RequestError(str(error)) from error

    deleted_comment = None
    if backend.remove_vote(comment_id, user_id, entity_type="Comment"):
        deleted_comment = backend.get_comment(comment_id)

    if not deleted_comment:
        raise ForumV2RequestError("Comment not found")

    return _prepare_comment_response(deleted_comment, user)
