"""Tests for votes apis."""

from typing import Any

import pytest

from forum.backends.mysql.api import MySQLBackend as patched_mysql_backend
from test_utils.client import APIClient

pytestmark = pytest.mark.django_db


@pytest.fixture(name="user")
def get_user() -> dict[str, Any]:
    """
    Fixture to create and return a test user.

    This fixture sets up a user with a predefined ID, username, and email.

    Returns:
        dict[str, Any]: The created user, represented as a dictionary.
    """
    backend = patched_mysql_backend
    user_id = "1"
    backend.find_or_create_user(user_id, username="testuser")
    return backend.get_user(user_id) or {}


@pytest.fixture(name="thread")
def get_thread(user: dict[str, Any]) -> dict[str, Any]:
    """
    Fixture to create and return a test thread.

    This fixture sets up a thread with a predefined title, body, and author.
    It also initializes votes for the thread.

    Args:
        user (dict[str, Any]): The test user who will be the author of the thread.

    Returns:
        dict[str, Any]: The created thread, represented as a dictionary.
    """
    backend = patched_mysql_backend

    # create dummy users
    for user_id in range(2, 6):
        backend.find_or_create_user(str(user_id), username=f"testuser-{user_id}")

    thread_id = backend.create_thread(
        {
            "title": "Test Thread",
            "body": "This is a test thread.",
            "author_id": user["_id"],
            "course_id": "course-v1:Test+Course+2024_S2",
            "commentable_id": "commentable_id",
            "author_username": "testuser",
        }
    )
    votes = backend.get_votes_dict(up=["2", "3"], down=["4", "5"])
    backend.update_thread(thread_id, votes=votes)
    return backend.get_thread(thread_id) or {}


@pytest.fixture(name="comment")
def get_comment(
    user: dict[str, Any],
    thread: dict[str, Any],
) -> dict[str, Any]:
    """
    Fixture to create and return a test comment.

    This fixture sets up a comment for a given thread with predefined body and author.
    It also initializes votes for the comment.

    Args:
        user (dict[str, Any]): The test user who will be the author of the comment.
        thread (dict[str, Any]): The thread to which the comment belongs.

    Returns:
        dict[str, Any]: The created comment, represented as a dictionary.
    """
    backend = patched_mysql_backend
    comment_id = backend.create_comment(
        {
            "body": "This is a test comment.",
            "course_id": "course-v1:Test+Course+2024_S2",
            "comment_thread_id": thread["_id"],
            "author_id": user["_id"],
            "author_username": "testuser",
        }
    )
    votes = backend.get_votes_dict(up=["2", "3"], down=["4", "5"])
    backend.update_comment(comment_id, votes=votes)
    return backend.get_comment(comment_id) or {}


def test_upvote_thread_api(
    api_client: APIClient,
    user: dict[str, Any],
    thread: dict[str, Any],
) -> None:
    """
    Test the API for upvoting a thread.

    This test verifies that an upvote on a thread increases the upvote count correctly.
    It checks the response from the API and the updated thread data.

    Args:
        api_client (APIClient): The API client to perform requests.
        user (dict[str, Any]): The test user performing the upvote.
        thread (dict[str, Any]): The thread to be upvoted.
    """
    backend = patched_mysql_backend
    user_id = user["_id"]
    thread_id = thread["_id"]

    prev_up_count = thread["votes"]["up_count"]

    response = api_client.put_json(
        f"/api/v2/threads/{thread_id}/votes",
        data={"user_id": user_id, "value": "up"},
    )
    # Calling the API second time, it should have no impact on the results.
    response = api_client.put_json(
        f"/api/v2/threads/{thread_id}/votes",
        data={"user_id": user_id, "value": "up"},
    )
    assert response.status_code == 200
    response_data = response.json()
    assert response_data is not None
    assert response_data["votes"]["up_count"] == prev_up_count + 1

    thread_data = backend.get_thread(thread_id) or {}
    assert thread_data["votes"]["up_count"] == prev_up_count + 1


def test_vote_thread_api(
    api_client: APIClient,
    user: dict[str, Any],
    thread: dict[str, Any],
) -> None:
    """
    Test the API for upvoting, downvote, and again upvotes the same thread.

    This test verifies that an upvote on a thread increases the upvote count correctly.
    It also checks downvote the upvote thread decreases the count.

    Args:
        api_client (APIClient): The API client to perform requests.
        user (dict[str, Any]): The test user performing the upvote.
        thread (dict[str, Any]): The thread to be upvoted.
    """
    backend = patched_mysql_backend
    user_id = user["_id"]
    thread_id = thread["_id"]

    prev_up_count = thread["votes"]["up_count"]
    prev_down_count = thread["votes"]["down_count"]

    # Upvote the Thread
    response = api_client.put_json(
        f"/api/v2/threads/{thread_id}/votes",
        data={"user_id": user_id, "value": "up"},
    )
    assert response.status_code == 200
    response_data = response.json()
    assert response_data is not None
    assert response_data["votes"]["up_count"] == prev_up_count + 1
    assert response_data["votes"]["down_count"] == prev_down_count

    # Downvote the upvoted Thread
    response = api_client.put_json(
        f"/api/v2/threads/{thread_id}/votes",
        data={"user_id": user_id, "value": "down"},
    )

    thread_data = backend.get_thread(thread_id) or {}
    assert thread_data["votes"]["up_count"] == prev_up_count
    assert thread_data["votes"]["down_count"] == prev_down_count + 1

    # Upvote the downvoted Thread
    response = api_client.put_json(
        f"/api/v2/threads/{thread_id}/votes",
        data={"user_id": user_id, "value": "up"},
    )
    assert response.status_code == 200
    response_data = response.json()
    assert response_data is not None
    assert response_data["votes"]["up_count"] == prev_up_count + 1
    assert response_data["votes"]["down_count"] == prev_down_count


def test_downvote_thread_api(
    api_client: APIClient,
    user: dict[str, Any],
    thread: dict[str, Any],
) -> None:
    """
    Test the API for downvoting a thread.

    This test verifies that a downvote on a thread increases the downvote count correctly.
    It checks the response from the API and the updated thread data.

    Args:
        api_client (APIClient): The API client to perform requests.
        user (dict[str, Any]): The test user performing the downvote.
        thread (dict[str, Any]): The thread to be downvoted.
    """
    backend = patched_mysql_backend
    user_id = user["_id"]
    thread_id = thread["_id"]

    prev_down_count = thread["votes"]["down_count"]

    response = api_client.put_json(
        f"/api/v2/threads/{thread_id}/votes",
        data={"user_id": user_id, "value": "down"},
    )
    assert response.status_code == 200
    response_data = response.json()
    assert response_data is not None
    assert response_data["votes"]["down_count"] == prev_down_count + 1

    thread_data = backend.get_thread(thread_id)
    assert thread_data is not None
    assert thread_data["votes"]["down_count"] == prev_down_count + 1


def test_remove_vote_thread_api(
    api_client: APIClient,
    user: dict[str, Any],
    thread: dict[str, Any],
) -> None:
    """
    Test the API for removing a vote from a thread.

    This test verifies that removing a vote correctly updates the upvote and downvote counts.
    It first upvotes the thread, then removes the vote and checks the counts.

    Args:
        api_client (APIClient): The API client to perform requests.
        user (dict[str, Any]): The test user who performed the upvote.
        thread (dict[str, Any]): The thread from which the vote will be removed.
    """
    backend = patched_mysql_backend
    user_id = user["_id"]
    thread_id = thread["_id"]

    prev_up_count = thread["votes"]["up_count"]
    prev_down_count = thread["votes"]["down_count"]

    # Upvote the thread first
    api_client.put_json(
        f"/api/v2/threads/{thread_id}/votes",
        data={"user_id": user_id, "value": "up"},
    )

    response = api_client.delete_json(
        f"/api/v2/threads/{thread_id}/votes?user_id={user_id}",
    )
    assert response.status_code == 200
    response_data = response.json()
    assert response_data is not None
    assert response_data["votes"]["up_count"] == prev_up_count
    assert response_data["votes"]["down_count"] == prev_down_count

    thread_data = backend.get_thread(thread_id) or {}
    assert thread_data is not None
    assert thread_data["votes"]["up_count"] == prev_up_count
    assert thread_data["votes"]["down_count"] == prev_down_count

    # Downvote the thread first
    api_client.put_json(
        f"/api/v2/threads/{thread_id}/votes",
        data={"user_id": user_id, "value": "down"},
    )
    response = api_client.delete_json(
        f"/api/v2/threads/{thread_id}/votes?user_id={user_id}",
    )
    assert response.status_code == 200
    response_data = response.json()
    assert response_data is not None
    assert response_data["votes"]["up_count"] == prev_up_count
    assert response_data["votes"]["down_count"] == prev_down_count

    thread_data = backend.get_thread(thread_id) or {}
    assert thread_data is not None
    assert thread_data["votes"]["up_count"] == prev_up_count
    assert thread_data["votes"]["down_count"] == prev_down_count


def test_upvote_comment_api(
    api_client: APIClient,
    user: dict[str, Any],
    comment: dict[str, Any],
) -> None:
    """
    Test the API for upvoting a comment.

    This test verifies that an upvote on a comment increases the upvote count correctly.
    It checks the response from the API and the updated comment data.

    Args:
        api_client (APIClient): The API client to perform requests.
        user (dict[str, Any]): The test user performing the upvote.
        comment (dict[str, Any]): The comment to be upvoted.
    """
    backend = patched_mysql_backend
    user_id = user["_id"]
    comment_id = comment["_id"]

    prev_up_count = comment["votes"]["up_count"]

    response = api_client.put_json(
        f"/api/v2/comments/{comment_id}/votes",
        data={"user_id": user_id, "value": "up"},
    )
    assert response.status_code == 200
    response_data = response.json()
    assert response_data is not None
    assert response_data["votes"]["up_count"] == prev_up_count + 1

    comment_data = backend.get_comment(comment_id)
    assert comment_data is not None
    assert comment_data["votes"]["up_count"] == prev_up_count + 1


def test_downvote_comment_api(
    api_client: APIClient,
    user: dict[str, Any],
    comment: dict[str, Any],
) -> None:
    """
    Test the API for downvoting a comment.

    This test verifies that a downvote on a comment increases the downvote count correctly.
    It checks the response from the API and the updated comment data.

    Args:
        api_client (APIClient): The API client to perform requests.
        user (dict[str, Any]): The test user performing the downvote.
        comment (dict[str, Any]): The comment to be downvoted.
    """
    backend = patched_mysql_backend
    user_id = user["_id"]
    comment_id = comment["_id"]

    prev_down_count = comment["votes"]["down_count"]

    response = api_client.put_json(
        f"/api/v2/comments/{comment_id}/votes",
        data={"user_id": user_id, "value": "down"},
    )
    assert response.status_code == 200
    response_data = response.json()
    assert response_data is not None
    assert response_data["votes"]["down_count"] == prev_down_count + 1

    comment_data = backend.get_comment(comment_id)
    assert comment_data is not None
    assert comment_data["votes"]["down_count"] == prev_down_count + 1


def test_remove_vote_comment_api(
    api_client: APIClient,
    user: dict[str, Any],
    comment: dict[str, Any],
) -> None:
    """
    Test the API for removing a vote from a comment.

    This test verifies that removing a vote correctly updates the upvote and downvote counts.
    It first upvotes the comment, then removes the vote and checks the counts.

    Args:
        api_client (APIClient): The API client to perform requests.
        user (dict[str, Any]): The test user who performed the upvote.
        comment (dict[str, Any]): The comment from which the vote will be removed.
    """
    backend = patched_mysql_backend
    user_id = user["_id"]
    comment_id = comment["_id"]

    prev_up_count = comment["votes"]["up_count"]
    prev_down_count = comment["votes"]["down_count"]

    # Upvote the comment first
    api_client.put_json(
        f"/api/v2/comments/{comment_id}/votes",
        data={"user_id": user_id, "value": "up"},
    )

    response = api_client.delete(
        f"/api/v2/comments/{comment_id}/votes?user_id={user_id}",
    )
    assert response.status_code == 200
    response_data = response.json()
    assert response_data is not None
    assert response_data["votes"]["up_count"] == prev_up_count
    assert response_data["votes"]["down_count"] == prev_down_count

    comment_data = backend.get_comment(comment_id)
    assert comment_data is not None
    assert comment_data["votes"]["up_count"] == prev_up_count
    assert comment_data["votes"]["down_count"] == prev_down_count


def test_vote_api_invalid_data(api_client: APIClient) -> None:
    """
    Test the API's response to invalid voting data.

    This test verifies that the API returns a 400 status code when provided with invalid data
    for voting on threads or comments.

    Args:
        api_client (APIClient): The API client to perform requests.
    """
    user_id = "1"
    thread_id = "507f1f77bff86cd799439011"
    comment_id = "507f1f77bcf86cd799439011"

    response = api_client.put_json(
        f"/api/v2/threads/{thread_id}/votes",
        data={"user_id": user_id, "value": "up"},
    )
    assert response.status_code == 400

    response = api_client.put_json(
        f"/api/v2/comments/{comment_id}/votes",
        data={"user_id": user_id, "value": "up"},
    )
    assert response.status_code == 400

    response = api_client.delete_json(
        f"/api/v2/threads/{thread_id}/votes?user_id={user_id}",
    )
    assert response.status_code == 400

    response = api_client.delete(
        f"/api/v2/comments/{comment_id}/votes?user_id={user_id}",
    )
    assert response.status_code == 400


def test_vote_api_missing_parameters(api_client: APIClient) -> None:
    """
    Test the API's response to missing parameters in voting requests.

    This test verifies that the API returns a 400 status code when required parameters
    are missing from the voting requests for threads or comments.

    Args:
        api_client (APIClient): The API client to perform requests.
    """
    thread_id = "507f1f77bff86cd799439011"
    comment_id = "507f1f77bcf86cd799439011"

    response = api_client.put_json(
        f"/api/v2/threads/{thread_id}/votes",
        data={"value": "up"},
    )
    assert response.status_code == 400

    response = api_client.put_json(
        f"/api/v2/comments/{comment_id}/votes",
        data={"value": "up"},
    )
    assert response.status_code == 400

    response = api_client.put_json(
        f"/api/v2/threads/{thread_id}/votes",
        data={"user_id": "1"},
    )
    assert response.status_code == 400

    response = api_client.put_json(
        f"/api/v2/comments/{comment_id}/votes",
        data={"user_id": "1"},
    )
    assert response.status_code == 400
