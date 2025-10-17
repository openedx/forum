"""
Native Python Users APIs.
"""

import logging
import math
from typing import Any, Optional

from forum.backend import get_backend
from forum.constants import FORUM_DEFAULT_PAGE, FORUM_DEFAULT_PER_PAGE
from forum.serializers.thread import ThreadSerializer
from forum.serializers.users import UserSerializer
from forum.utils import ForumV2RequestError

log = logging.getLogger(__name__)


def get_user(
    user_id: str,
    group_ids: Optional[list[int]] = None,
    course_id: Optional[str] = None,
    complete: Optional[bool] = False,
) -> dict[str, Any]:
    """Get user data by user_id."""
    """
    Get users data by user_id.
    Parameters:
        user_id (str): The ID of the requested User.
        params (str): attributes for user's data filteration.
    Response:
        A response with the users data.
    """
    backend = get_backend(course_id)()
    user = backend.get_user(user_id, get_full_dict=False)
    if not user:
        log.error(f"Forumv2RequestError for retrieving user's data for id {user_id}.")
        raise ForumV2RequestError(str(f"user not found with id: {user_id}"))

    params = {
        "complete": complete,
        "group_ids": group_ids,
        "course_id": course_id,
    }
    hashed_user = backend.user_to_hash(user_id, params)
    serializer = UserSerializer(hashed_user)
    return serializer.data


def update_user(
    user_id: str,
    username: Optional[str] = None,
    default_sort_key: Optional[str] = None,
    course_id: Optional[str] = None,
    group_ids: Optional[list[int]] = None,
    complete: Optional[bool] = False,
) -> dict[str, Any]:
    """Update user."""
    backend = get_backend(course_id)()
    user = backend.get_user(user_id)
    user_by_username = backend.get_user_by_username(username)
    if user and user_by_username:
        if user["external_id"] != user_by_username["external_id"]:
            raise ForumV2RequestError("user does not match")
    elif user_by_username:
        raise ForumV2RequestError(f"user already exists with username: {username}")
    else:
        user_id = backend.find_or_create_user(user_id)
    update_data = {"username": username}
    if default_sort_key is not None:
        update_data["default_sort_key"] = default_sort_key
    backend.update_user(user_id, update_data)
    updated_user = backend.get_user(user_id)
    if not updated_user:
        raise ForumV2RequestError(f"user not found with id: {user_id}")
    params = {
        "complete": complete,
        "group_ids": group_ids,
        "course_id": course_id,
    }
    hashed_user = backend.user_to_hash(user_id, params)
    serializer = UserSerializer(hashed_user)
    return serializer.data


def create_user(
    user_id: str,
    username: str,
    default_sort_key: str = "date",
    course_id: Optional[str] = None,
    group_ids: Optional[list[int]] = None,
    complete: bool = False,
) -> dict[str, Any]:
    """Create user."""
    backend = get_backend(course_id)()
    user_by_id = backend.get_user(user_id)
    user_by_username = backend.get_user_by_username(username)

    if user_by_id or user_by_username:
        raise ForumV2RequestError(f"user already exists with id: {id}")

    backend.find_or_create_user(
        user_id, username=username, default_sort_key=default_sort_key
    )
    user = backend.get_user(user_id)
    if not user:
        raise ForumV2RequestError(f"user not found with id: {user_id}")
    params = {
        "complete": complete,
        "group_ids": group_ids,
        "course_id": course_id,
    }
    hashed_user = backend.user_to_hash(user_id, params)
    serializer = UserSerializer(hashed_user)
    return serializer.data


def update_username(
    user_id: str, new_username: str, course_id: Optional[str] = None
) -> dict[str, str]:
    """Update username."""
    backend = get_backend(course_id)()
    user = backend.get_user(user_id)
    if not user:
        raise ForumV2RequestError(str(f"user not found with id: {user_id}"))
    backend.update_user(user_id, {"username": new_username})
    backend.replace_username_in_all_content(user_id, new_username)
    return {"message": "Username updated successfully"}


def retire_user(
    user_id: str, retired_username: str, course_id: Optional[str] = None
) -> dict[str, str]:
    """Retire user."""
    backend = get_backend(course_id)()
    user = backend.get_user(user_id)
    if not user:
        raise ForumV2RequestError(f"user not found with id: {user_id}")
    backend.update_user(
        user_id,
        data={
            "email": "",
            "username": retired_username,
            "read_states": [],
        },
    )
    backend.unsubscribe_all(user_id)
    backend.retire_all_content(user_id, retired_username)

    return {"message": "User retired successfully"}


def mark_thread_as_read(
    user_id: str,
    source_id: str,
    complete: bool = False,
    course_id: Optional[str] = None,
    group_ids: Optional[list[int]] = None,
) -> dict[str, Any]:
    """Mark thread as read."""
    backend = get_backend(course_id)()
    user = backend.get_user(user_id)
    if not user:
        raise ForumV2RequestError(str(f"user not found with id: {user_id}"))

    thread = backend.get_thread(source_id)
    if not thread:
        raise ForumV2RequestError(str(f"source not found with id: {source_id}"))

    backend.mark_as_read(user_id, source_id)

    user = backend.get_user(user_id)
    if not user:
        raise ForumV2RequestError(str(f"user not found with id: {user_id}"))

    params = {
        "complete": complete,
        "group_ids": group_ids,
        "course_id": course_id,
    }

    hashed_user = backend.user_to_hash(user_id, params)
    serializer = UserSerializer(hashed_user)
    return serializer.data


def get_user_active_threads(
    user_id: str,
    course_id: str,
    author_id: Optional[str] = None,
    thread_type: Optional[str] = None,
    flagged: Optional[bool] = False,
    unread: Optional[bool] = False,
    unanswered: Optional[bool] = False,
    unresponded: Optional[bool] = False,
    count_flagged: Optional[bool] = False,
    sort_key: Optional[str] = "user_activity",
    page: Optional[int] = FORUM_DEFAULT_PAGE,
    per_page: Optional[int] = FORUM_DEFAULT_PER_PAGE,
    group_id: Optional[str] = None,
    is_moderator: Optional[bool] = False,
) -> dict[str, Any]:
    """Get user active threads."""
    backend = get_backend(course_id)()
    raw_query = bool(sort_key == "user_activity")
    if not course_id:
        return {}
    active_contents = list(
        backend.get_contents(
            author_id=user_id,
            anonymous=False,
            anonymous_to_peers=False,
            course_id=course_id,
        )
    )

    if flagged:
        active_contents = [
            content
            for content in active_contents
            if content["abuse_flaggers"] and len(content["abuse_flaggers"]) > 0
        ]
    active_contents = sorted(
        active_contents, key=lambda x: x["updated_at"], reverse=True
    )
    active_thread_ids = list(
        set(
            (
                content["comment_thread_id"]
                if content["_type"] == "Comment"
                else content["_id"]
            )
            for content in active_contents
        )
    )

    params: dict[str, Any] = {
        "comment_thread_ids": active_thread_ids,
        "user_id": user_id,
        "course_id": course_id,
        "group_ids": [int(group_id)] if group_id else [],
        "author_id": author_id,
        "thread_type": thread_type,
        "filter_flagged": flagged,
        "filter_unread": unread,
        "filter_unanswered": unanswered,
        "filter_unresponded": unresponded,
        "count_flagged": count_flagged,
        "sort_key": sort_key,
        "page": page,
        "per_page": per_page,
        "context": "course",
        "raw_query": raw_query,
        "is_moderator": is_moderator,
    }
    data = backend.handle_threads_query(**params)

    if collections := data.get("collection"):
        thread_serializer = ThreadSerializer(
            collections,
            many=True,
            context={
                "count_flagged": count_flagged,
                "include_endorsed": True,
                "include_read_state": True,
            },
            backend=backend,
        )
        data["collection"] = thread_serializer.data
    else:
        collection = data.get("result", [])
        for thread in collection:
            thread["_id"] = str(thread.pop("_id"))
            thread["type"] = str(thread.get("_type", "")).lower()
        data["collection"] = ThreadSerializer(
            collection, many=True, backend=backend
        ).data

    return data


def _get_user_data(
    user_stats: dict[str, Any], exclude_from_stats: list[str]
) -> dict[str, Any]:
    """Get user data from user stats."""
    user_data = {"username": user_stats["username"]}
    for k, v in user_stats["course_stats"].items():
        if k not in exclude_from_stats:
            user_data[k] = v
    return user_data


def _get_stats_for_usernames(
    course_id: str, usernames: list[str], backend: Any
) -> list[dict[str, Any]]:
    """Get stats for specific usernames."""
    users = backend.get_users()
    stats_query = []
    for user in users:
        if user["username"] not in usernames:
            continue
        course_stats = user.get("course_stats")
        if course_stats:
            for course_stat in course_stats:
                if course_stat["course_id"] == course_id:
                    stats_query.append(
                        {"username": user["username"], "course_stats": course_stat}
                    )
                    break
    return sorted(stats_query, key=lambda u: usernames.index(u["username"]))


def get_user_course_stats(
    course_id: str,
    usernames: Optional[str] = None,
    page: int = FORUM_DEFAULT_PAGE,
    per_page: int = FORUM_DEFAULT_PER_PAGE,
    sort_key: str = "",
    with_timestamps: bool = False,
) -> dict[str, Any]:
    """Get user course stats."""
    backend = get_backend(course_id)()
    sort_criterion = backend.get_user_sort_criterion(sort_key)
    exclude_from_stats = ["_id", "course_id"]
    if not with_timestamps:
        exclude_from_stats.append("last_activity_at")

    usernames_list = usernames.split(",") if usernames else None
    data = []

    if not usernames_list:
        paginated_stats = backend.get_paginated_user_stats(
            course_id, page, per_page, sort_criterion
        )
        num_pages = 0
        page = 0
        total_count = 0
        if paginated_stats.get("pagination"):
            total_count = paginated_stats["pagination"][0]["total_count"]
            num_pages = max(1, math.ceil(total_count / per_page))
            data = [
                _get_user_data(user_stats, exclude_from_stats)
                for user_stats in paginated_stats["data"]
            ]
    else:
        stats_query = _get_stats_for_usernames(course_id, usernames_list, backend)
        total_count = len(stats_query)
        num_pages = 1
        data = [
            {
                "username": user_stats["username"],
                **{
                    k: v
                    for k, v in user_stats["course_stats"].items()
                    if k not in exclude_from_stats
                },
            }
            for user_stats in stats_query
        ]

    return {
        "user_stats": data,
        "num_pages": num_pages,
        "page": page,
        "count": total_count,
    }


def update_users_in_course(course_id: str) -> dict[str, int]:
    """Update all user stats in a course."""
    backend = get_backend(course_id)()
    updated_users = backend.update_all_users_in_course(course_id)
    return {"user_count": len(updated_users)}
