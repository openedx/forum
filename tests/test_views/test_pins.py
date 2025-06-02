"""Test pin/unpin thread api endpoints."""

import pytest

from forum.backends.mysql.api import MySQLBackend as patched_mysql_backend
from test_utils.client import APIClient

pytestmark = pytest.mark.django_db


def test_pin_and_unpin_thread_api(
    api_client: APIClient,
) -> None:
    """
    Test the pin/unpin thread API.
    This test checks that a user can pin/unpin a thread.
    """
    backend = patched_mysql_backend
    user_id = "1"

    backend.find_or_create_user(user_id, username="user1")
    comment_thread_id = backend.create_thread(
        {
            "title": "title",
            "body": "Hello World!",
            "pinned": False,
            "author_id": user_id,
            "course_id": "course-v1:Arbisoft+SE002+2024_S2",
            "commentable_id": "66b4e0440dead7001deb948b",
            "author_username": "Faraz",
        }
    )
    backend.create_comment(
        {
            "body": "Hello World!",
            "course_id": "course-v1:Arbisoft+SE002+2024_S2",
            "comment_thread_id": comment_thread_id,
            "author_id": "1",
            "author_username": "Faraz",
        }
    )
    response = api_client.put_json(
        f"/api/v2/threads/{comment_thread_id}/pin",
        data={"user_id": user_id},
    )

    assert response.status_code == 200
    thread_data = response.json()
    assert thread_data is not None
    assert thread_data["pinned"] is True
    thread = backend.get_thread(comment_thread_id)
    assert thread is not None
    assert thread["pinned"] is True

    response = api_client.put_json(
        f"/api/v2/threads/{comment_thread_id}/unpin",
        data={"user_id": user_id},
    )

    assert response.status_code == 200
    thread_data = response.json()
    assert thread_data is not None
    assert thread_data["pinned"] is False
    thread = backend.get_thread(comment_thread_id)
    assert thread is not None
    assert thread["pinned"] is False


def test_pin_unpin_thread_api_invalid_data(
    api_client: APIClient,
) -> None:
    """
    Test the invalid data for pin/unpin thread API.
    This test checks that if user/thread exists or not.
    """
    backend = patched_mysql_backend
    user_id = "1"
    thread_id = backend.generate_id()
    backend.find_or_create_user(user_id, username="user1")

    response = api_client.put_json(
        path=f"/api/v2/threads/{thread_id}/pin",
        data={"user_id": str(user_id)},
    )
    assert response.status_code == 400
    assert response.json() == {"error": "User / Thread doesn't exist"}

    response = api_client.put_json(
        path=f"/api/v2/threads/{thread_id}/unpin",
        data={"user_id": str(user_id)},
    )
    assert response.status_code == 400
    assert response.json() == {"error": "User / Thread doesn't exist"}
