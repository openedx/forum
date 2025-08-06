"""Forum Utils."""

import logging
from datetime import datetime
from typing import Any, Sequence

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.dispatch import Signal
from django.http import HttpRequest
from django.utils import timezone
from requests.models import Response

log = logging.getLogger(__name__)


def handle_proxy_requests(request: HttpRequest, suffix: str, method: str) -> Response:
    """
    Catches all requests and sends them to forum/cs_comments_service URLs.

    Arguments:
        request (HttpRequest): The incoming HTTP request.
        suffix (str): The URL suffix for the target service.
        method (str): The HTTP method to use for the proxy request.

    Returns:
        Response: The response from the proxied service.
    """
    comments_service_url = getattr(
        settings, "CS_COMMENTS_SERVICE_URL", "http://forum:4567"
    )
    url = f"{comments_service_url}/api/v1/{suffix}"
    request_headers = {
        "X-Edx-Api-Key": request.headers.get("X-Edx-Api-Key", ""),
        "Accept-Language": request.headers.get("Accept-Language", ""),
    }
    request_data = request.POST.dict()
    request_params = request.GET.dict()

    log.error(
        "%s request to Forum V1 URL: %s with Params: %s and Data: %s",
        method.upper(),
        url,
        request_params,
        request_data,
    )
    return requests.request(
        method,
        url,
        data=request_data,
        params=request_params,
        headers=request_headers,
        timeout=5.0,
    )


def str_to_bool(value: str | bool) -> bool:
    """
    Convert a string or boolean value to a boolean.

    If the input is already a boolean, the value is returned as is.
    For string inputs, 'true' (case-insensitive) or '1' are considered True,
    while any other value is considered False.

    Args:
        value (str | bool): The input value, either a string or a boolean.

    Returns:
        bool: The converted boolean value.
    """
    if isinstance(value, bool):
        return value
    return value.lower() in ("true", "1")


def get_int_value_from_collection(
    collection: dict[str, Any], key: str, default_value: int
) -> int:
    """
    Get int value from the collection.
    """
    try:
        return int(collection[key])
    except (TypeError, ValueError, KeyError):
        return default_value


def get_str_value_from_collection(collection: dict[str, Any], key: str) -> str:
    """
    Get str value from the collection.
    """
    try:
        value = str(collection[key])
    except (TypeError, ValueError, KeyError) as exception:
        raise ValueError("Invalud Value") from exception
    return value


def get_handler_by_name(name: str) -> Signal:
    """
    Return the signal handler by name.

    Args:
        name (str): The name of the signal.

    Returns:
        Signal: The corresponding signal object.
    """
    # TODO: Remove this function when we shift to MySQL as we can receive the signals
    # directly from the model updates using pose_save and other methods.
    from forum import signals  # pylint: disable=cyclic-import import-outside-toplevel

    map_signals = {
        "comment_deleted": signals.comment_deleted,
        "comment_thread_deleted": signals.comment_thread_deleted,
        "comment_inserted": signals.comment_inserted,
        "comment_thread_inserted": signals.comment_thread_inserted,
        "comment_updated": signals.comment_updated,
        "comment_thread_updated": signals.comment_thread_updated,
    }

    try:
        return map_signals[name]
    except KeyError as exc:
        raise KeyError(f"No signal found for the name: {name}") from exc


def prepare_comment_data_for_get_children(
    children: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Prepare children data to be used in serializer."""
    children_data = []
    for child in children:
        children_data.append(
            {
                **child,
                "id": str(child.get("_id")),
                "user_id": child.get("author_id"),
                "thread_id": str(child.get("comment_thread_id")),
                "username": child.get("author_username"),
                "parent_id": str(child.get("parent_id")),
                "type": str(child.get("_type", "")).lower(),
            }
        )
    return children_data


def validate_upvote_or_downvote(value: int) -> None:
    """Validate upvote or downvote value."""
    if value not in [1, -1]:
        raise ValidationError("This field only accepts 1 or -1.")


def make_aware(dt: datetime) -> datetime:
    """Make datetime timezone-aware."""
    if dt.tzinfo is None:
        return timezone.make_aware(dt)
    return dt


def get_group_ids_from_params(params: dict[str, Any]) -> list[int]:
    """
    Extract group IDs from the provided parameters.

    Args:
        params (dict): A dictionary containing the parameters.

    Returns:
        list: A list of group IDs.

    Raises:
        ValueError: If both `group_id` and `group_ids` are specified in the parameters.
    """
    if "group_id" in params and "group_ids" in params:
        raise ValueError("Cannot specify both group_id and group_ids")
    if group_id := params.get("group_id"):
        return [int(group_id)]
    elif group_ids := params.get("group_ids", []):
        if isinstance(group_ids, str):
            return [int(x) for x in group_ids.split(",")]
        elif isinstance(group_ids, list):
            return [int(x) for x in group_ids]
        # if it's not a str or list, it's invalid, so drop it.
    return []


def get_commentable_ids_from_params(params: dict[str, Any]) -> list[str]:
    """
    Extract commentable IDs from the provided parameters.

    Args:
        params (dict): A dictionary containing the parameters.

    Returns:
        list: A list of commentable IDs.

    Raises:
        ValueError: If both `commentable_id` and `commentable_ids` are specified in the parameters.
    """
    if "commentable_id" in params and "commentable_ids" in params:
        raise ValueError("Cannot specify both commentable_id and commentable_ids")

    commentable_id = params.get("commentable_id")
    if commentable_id:
        return [commentable_id]

    commentable_ids = params.get("commentable_ids", [])
    if isinstance(commentable_ids, str):
        return commentable_ids.split(",")
    elif isinstance(commentable_ids, list):
        return commentable_ids

    return []


def get_sort_criteria(sort_key: str) -> Sequence[tuple[str, int]]:
    """
    Generate sorting criteria based on the provided key.

    Parameters:
    -----------
    sort_key : str
        Key to determine sort order ("date", "activity", "votes", "comments").

    Returns:
    --------
    list
        List of tuples for sorting, including "pinned" and the relevant field,
        optionally adding "created_at" if needed.
    """
    sort_key_mapper = {
        "date": "created_at",
        "activity": "last_activity_at",
        "votes": "votes.point",
        "comments": "comment_count",
    }
    sort_key = sort_key or "date"
    sort_key = sort_key_mapper.get(sort_key, "")

    if sort_key:
        # only sort order of -1 (descending) is supported.
        sort_criteria = [("pinned", -1), (sort_key, -1)]
        if sort_key not in ["created_at", "last_activity_at"]:
            sort_criteria.append(("created_at", -1))
        return sort_criteria
    return []


def get_trunc_title(title: str) -> str:
    """
    Truncate a title to 1024 characters for mysql db.

    Args:
        title (str): A title string.

    Returns:
        str: A truncated title string with length less than 1025 characters.
    """
    return title[:1024]


class ForumV2RequestError(Exception):
    pass
