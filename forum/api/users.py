"""
Native Python Users APIs.
"""

import logging
import math
from typing import Any, Dict, Optional
from datetime import datetime

from django.http import HttpRequest
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
    show_deleted: Optional[bool] = False,
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
        "is_deleted": show_deleted,
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
    exclude_from_stats = ["_id", "course_id", "deleted_count"]
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


def mute_user(
    muted_user_id: str,
    muter_id: str,
    course_id: str,
    scope: str = "personal",
    reason: str = "",
    requester_is_privileged: bool = False,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Mute a user in discussions.

    Args:
        muted_user_id: ID of user to mute
        muter_id: ID of user performing the mute
        course_id: Course identifier
        scope: Mute scope ('personal' or 'course')
        reason: Optional reason for mute
        requester_is_privileged: Whether requester has course-level privileges

    Returns:
        Dictionary containing mute record data
    """
    try:
        backend = get_backend(course_id)()
        return backend.mute_user(
            muted_user_id=muted_user_id,
            muter_id=muter_id,
            course_id=course_id,
            scope=scope,
            reason=reason,
            requester_is_privileged=requester_is_privileged,
            **kwargs,
        )
    except ValueError as e:
        raise ForumV2RequestError(str(e)) from e
    except Exception as e:
        raise ForumV2RequestError(f"Failed to mute user: {str(e)}") from e


def unmute_user(
    muted_user_id: str,
    unmuted_by_id: str,
    course_id: str,
    scope: str = "personal",
    muter_id: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Unmute a user in discussions.

    Args:
        muted_user_id: ID of user to unmute
        unmuted_by_id: ID of user performing the unmute
        course_id: Course identifier
        scope: Mute scope ('personal' or 'course')
        muter_id: Optional filter by who performed the original mute

    Returns:
        Dictionary containing unmute operation result
    """
    try:
        backend = get_backend(course_id)()
        return backend.unmute_user(
            muted_user_id=muted_user_id,
            unmuted_by_id=unmuted_by_id,
            course_id=course_id,
            scope=scope,
            muter_id=muter_id,
            **kwargs,
        )
    except ValueError as e:
        raise ForumV2RequestError(str(e)) from e
    except Exception as e:
        raise ForumV2RequestError(f"Failed to unmute user: {str(e)}") from e


def get_user_mute_status(
    user_id: str, course_id: str, viewer_id: str, **kwargs: Any
) -> Dict[str, Any]:
    """
    Get mute status for a user in a course.

    Args:
        user_id: ID of user to check
        course_id: Course identifier
        viewer_id: ID of user requesting the status

    Returns:
        Dictionary containing mute status information
    """
    try:
        backend = get_backend(course_id)()
        return backend.get_user_mute_status(
            muted_user_id=user_id,
            course_id=course_id,
            requesting_user_id=viewer_id,
            **kwargs,
        )
    except ValueError as e:
        raise ForumV2RequestError(str(e)) from e
    except Exception as e:
        raise ForumV2RequestError(f"Failed to get mute status: {str(e)}") from e


def get_muted_users(
    muter_id: str, course_id: str, scope: str = "all", **kwargs: Any
) -> list[dict[str, Any]]:
    """
    Get list of users muted by a specific user.

    Args:
        muter_id: ID of the user who muted others
        course_id: Course identifier
        scope: Scope filter ('personal', 'course', or 'all')

    Returns:
        List of muted user records
    """
    try:
        backend = get_backend(course_id)()
        return backend.get_muted_users(
            moderator_id=muter_id, course_id=course_id, scope=scope, **kwargs
        )
    except ValueError as e:
        raise ForumV2RequestError(str(e)) from e
    except Exception as e:
        raise ForumV2RequestError(f"Failed to get muted users: {str(e)}") from e


def mute_and_report_user(
    muted_user_id: str,
    muter_id: str,
    course_id: str,
    scope: str = "personal",
    reason: str = "",
    thread_id: str = "",
    comment_id: str = "",
    request: Optional[HttpRequest] = None,
    requester_is_privileged: bool = False,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Mute a user and flag their content as abusive in discussions.

    Args:
        muted_user_id: ID of user to mute
        muter_id: ID of user performing the mute
        course_id: Course identifier
        scope: Mute scope ('personal' or 'course')
        reason: Reason for muting and reporting
        thread_id: Optional content ID to flag (tries as thread, then comment)
        comment_id: Optional comment ID to flag as abusive
        request: Django request object for content flagging
        requester_is_privileged: Whether requester has course-level privileges
        **kwargs: Additional parameters to pass to backend.mute_user

    Returns:
        Dictionary containing mute and report operation result
    """
    try:
        backend = get_backend(course_id)()

        # Mute the user first
        mute_result = backend.mute_user(
            muted_user_id=muted_user_id,
            muter_id=muter_id,
            course_id=course_id,
            scope=scope,
            reason=reason,
            requester_is_privileged=requester_is_privileged,
            **kwargs,
        )

        # Handle content flagging if request provided
        flagged_items = []
        should_flag_content = (thread_id or comment_id) and request

        if should_flag_content and request:
            user_id = str(getattr(request.user, "id", ""))

            # Flag thread_id (may be thread or comment)
            if thread_id:
                try:
                    backend.flag_as_abuse(
                        user_id=user_id,
                        entity_id=thread_id,
                        entity_type="CommentThread",
                    )
                    result = {
                        "content_type": "thread",
                        "content_id": thread_id,
                        "flagged": True,
                    }
                except Exception as e:  # pylint: disable=broad-except
                    log.warning("Failed to flag thread %s: %s", thread_id, str(e))
                    # Retry as Comment
                    try:
                        backend.flag_as_abuse(
                            user_id=user_id, entity_id=thread_id, entity_type="Comment"
                        )
                        result = {
                            "content_type": "comment",
                            "content_id": thread_id,
                            "flagged": True,
                        }
                    except Exception as e2:  # pylint: disable=broad-except
                        log.warning("Failed to flag comment %s: %s", thread_id, str(e2))
                        result = {
                            "content_type": "comment",
                            "content_id": thread_id,
                            "flagged": False,
                            "error": str(e2),
                        }
                flagged_items.append(result)

            # Flag comment_id separately
            if comment_id:
                try:
                    backend.flag_as_abuse(
                        user_id=user_id, entity_id=comment_id, entity_type="Comment"
                    )
                    flagged_items.append(
                        {
                            "content_type": "comment",
                            "content_id": comment_id,
                            "flagged": True,
                        }
                    )
                except Exception as e:  # pylint: disable=broad-except
                    log.warning("Failed to flag comment %s: %s", comment_id, str(e))
                    flagged_items.append(
                        {
                            "content_type": "comment",
                            "content_id": comment_id,
                            "flagged": False,
                            "error": str(e),
                        }
                    )

        # Build report result based on flagged content
        if flagged_items:
            all_flagged = all(item["flagged"] for item in flagged_items)
            report_result = {
                "status": "success" if all_flagged else "partial",
                "flagged_items": flagged_items,
            }
            message = "User muted and content flagged"
        else:
            report_result = {
                "status": "success",
                "report_id": f"report_{muted_user_id}_{muter_id}_{course_id}",
                "reported_user_id": muted_user_id,
                "reported_by_id": muter_id,
                "course_id": course_id,
                "reason": reason,
                "created": datetime.utcnow().isoformat(),
                "message": "User reported (no specific content flagged)",
            }
            message = "User muted and reported"

        return {
            "status": "success",
            "message": message,
            "mute_record": mute_result,
            "report_record": report_result,
        }
    except ValueError as e:
        raise ForumV2RequestError(str(e)) from e
    except Exception as e:  # pylint: disable=broad-except
        raise ForumV2RequestError(f"Failed to mute and report user: {str(e)}") from e


def get_all_muted_users_for_course(
    course_id: str,
    requester_id: Optional[str] = None,
    scope: str = "all",
    requester_is_privileged: bool = False,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Get all muted users in a course with role-based access control.

    Args:
        course_id: Course identifier
        requester_id: ID of the user requesting the list
        scope: Scope filter ('personal', 'course', or 'all')
        requester_is_privileged: Whether the requester has course-level privileges

    Returns:
        Dictionary containing list of muted users based on requester role and scope

    Authorization:
        - Learners: Can only see their own personal mutes
        - Staff: Can see course-wide mutes and all personal mutes
    """
    try:
        backend = get_backend(course_id)()
        return backend.get_all_muted_users_for_course(
            course_id=course_id,
            requester_id=requester_id,
            scope=scope,
            requester_is_privileged=requester_is_privileged,
            **kwargs,
        )
    except ValueError as e:
        raise ForumV2RequestError(str(e)) from e
    except Exception as e:  # pylint: disable=broad-except
        raise ForumV2RequestError(f"Failed to get course muted users: {str(e)}") from e
