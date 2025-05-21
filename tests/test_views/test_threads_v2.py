"""Test threads api endpoints."""

from datetime import datetime
from typing import Any, Optional
import pytest

from django.contrib.auth import get_user_model
from test_utils.client import APIClient
from forum.backends.mysql.models import ReadState
from forum.backends.mysql.api import MySQLBackend

pytestmark = pytest.mark.django_db
User = get_user_model()


def setup_models(
    backend: Any,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    course_id: Optional[str] = None,
    thread_type: Optional[str] = None,
) -> tuple[str, str]:
    """
    Setup models.

    This will create a user, thread and parent comment
    for being used in comments api tests.
    """

    user_id = user_id or "1"
    username = username or "user1"
    course_id = course_id or "course1"
    backend.find_or_create_user(user_id, username=username)
    comment_thread_id = backend.create_thread(
        {
            "title": "Thread 1",
            "body": "Thread 1",
            "course_id": course_id,
            "commentable_id": "CommentThread",
            "author_id": user_id,
            "author_username": username,
            "abuse_flaggers": [],
            "historical_abuse_flaggers": [],
            "thread_type": thread_type or "discussion",
        }
    )
    return user_id, comment_thread_id


def create_comments_in_a_thread(backend: Any, thread_id: str) -> tuple[str, str]:
    """create comments in a thread."""
    user_id = "1"
    username = "user1"
    course_id = "course1"
    comment_id_1 = backend.create_comment(
        {
            "body": "Comment 1",
            "course_id": course_id,
            "author_id": user_id,
            "comment_thread_id": thread_id,
            "author_username": username,
        }
    )

    comment_id_2 = backend.create_comment(
        {
            "body": "Comment 2",
            "course_id": course_id,
            "author_id": user_id,
            "comment_thread_id": thread_id,
            "author_username": username,
        }
    )
    return comment_id_1, comment_id_2


def is_thread_id_exists_in_user_read_state(user_id: str, thread_id: str) -> bool:
    """
    Return True or False if thread_id exists in read_states of any user using Django ORM.
    Assumes a User model with a JSONField or related model for read_states.
    """
    return ReadState.objects.filter(
        user_id=user_id, last_read_times__comment_thread=thread_id
    ).exists()


def test_read_states_deletion_of_a_thread_on_thread_deletion(
    api_client: APIClient,
    patched_mysql_backend: MySQLBackend,
) -> None:
    """Test delete read_states of the thread on deletion of a thread for mongodb."""
    user_id, thread_id = setup_models(backend=patched_mysql_backend)
    comment_id_1, comment_id_2 = create_comments_in_a_thread(
        patched_mysql_backend, thread_id
    )
    thread_from_db = patched_mysql_backend.get_thread(thread_id)
    assert thread_from_db is not None
    assert thread_from_db["comment_count"] == 2
    get_thread_response = api_client.get_json(
        f"/api/v2/threads/{thread_id}",
        params={
            "recursive": False,
            "with_responses": True,
            "user_id": int(user_id),
            "mark_as_read": False,
            "resp_skip": 0,
            "resp_limit": 10,
            "reverse_order": "true",
            "merge_question_type_responses": False,
        },
    )  # call get_thread API to save read_states of this thread in user model
    assert get_thread_response.status_code == 200
    assert is_thread_id_exists_in_user_read_state(user_id, thread_id) is True
    response = api_client.delete_json(f"/api/v2/threads/{thread_id}")
    assert response.status_code == 200
    assert patched_mysql_backend.get_thread(thread_id) is None
    assert patched_mysql_backend.get_comment(comment_id_1) is None
    assert patched_mysql_backend.get_comment(comment_id_2) is None
    assert (
        patched_mysql_backend.get_subscription(
            subscriber_id=user_id, source_id=thread_id
        )
        is None
    )
    assert is_thread_id_exists_in_user_read_state(user_id, thread_id) is False


def test_read_states_deletion_on_thread_deletion_without_read_states(
    api_client: APIClient,
    patched_mysql_backend: MySQLBackend,
) -> None:
    """Test delete read_states of the thread on deletion of a thread when there are no read states."""
    user_id, thread_id = setup_models(backend=patched_mysql_backend)
    comment_id_1, comment_id_2 = create_comments_in_a_thread(
        patched_mysql_backend, thread_id
    )
    thread_from_db = patched_mysql_backend.get_thread(thread_id)
    assert thread_from_db is not None
    assert thread_from_db["comment_count"] == 2
    assert is_thread_id_exists_in_user_read_state(user_id, thread_id) is False

    response = api_client.delete_json(f"/api/v2/threads/{thread_id}")
    assert response.status_code == 200
    assert patched_mysql_backend.get_thread(thread_id) is None
    assert patched_mysql_backend.get_comment(comment_id_1) is None
    assert patched_mysql_backend.get_comment(comment_id_2) is None
    assert (
        patched_mysql_backend.get_subscription(
            subscriber_id=user_id, source_id=thread_id
        )
        is None
    )
    assert is_thread_id_exists_in_user_read_state(user_id, thread_id) is False


def test_read_states_deletion_on_thread_deletion_with_multiple_read_states(
    api_client: APIClient,
    patched_mysql_backend: MySQLBackend,
) -> None:
    """Test delete read_states of the thread on deletion of a thread when there are multiple read states."""
    # Setup first thread and read state
    user_id_1, thread_id_1 = setup_models(backend=patched_mysql_backend)
    get_thread_response = api_client.get_json(
        f"/api/v2/threads/{thread_id_1}",
        params={
            "recursive": False,
            "with_responses": True,
            "user_id": int(user_id_1),
            "mark_as_read": True,
            "resp_skip": 0,
            "resp_limit": 10,
            "reverse_order": "true",
            "merge_question_type_responses": False,
        },
    )
    assert get_thread_response.status_code == 200
    assert is_thread_id_exists_in_user_read_state(user_id_1, thread_id_1) is True

    # Setup second thread and read state
    user_id_2, thread_id_2 = setup_models(
        backend=patched_mysql_backend,
        user_id="2",
        username="user2",
        course_id="course2",
    )
    get_thread_response = api_client.get_json(
        f"/api/v2/threads/{thread_id_2}",
        params={
            "recursive": False,
            "with_responses": True,
            "user_id": int(user_id_2),
            "mark_as_read": True,
            "resp_skip": 0,
            "resp_limit": 10,
            "reverse_order": "true",
            "merge_question_type_responses": False,
        },
    )
    assert get_thread_response.status_code == 200
    assert is_thread_id_exists_in_user_read_state(user_id_2, thread_id_2) is True

    # Delete first thread and verify its read state is removed while second remains
    response = api_client.delete_json(f"/api/v2/threads/{thread_id_1}")
    assert response.status_code == 200
    assert patched_mysql_backend.get_thread(thread_id_1) is None
    assert is_thread_id_exists_in_user_read_state(user_id_1, thread_id_1) is False
    assert is_thread_id_exists_in_user_read_state(user_id_2, thread_id_2) is True


def test_read_states_deletion_checks_thread_id_existence(
    api_client: APIClient,
    patched_mysql_backend: MySQLBackend,
) -> None:
    """Test that read state deletion only occurs when thread_id exists in last_read_times."""
    user_id, thread_id = setup_models(backend=patched_mysql_backend)
    _, other_thread_id = setup_models(backend=patched_mysql_backend)

    read_states = [
        {
            "course_id": "course1",
            "last_read_times": {other_thread_id: datetime.now()},
        }
    ]
    patched_mysql_backend.update_user(user_id, {"read_states": read_states})

    assert is_thread_id_exists_in_user_read_state(user_id, other_thread_id) is True
    assert is_thread_id_exists_in_user_read_state(user_id, thread_id) is False

    response = api_client.delete_json(f"/api/v2/threads/{thread_id}")
    assert response.status_code == 200
    assert is_thread_id_exists_in_user_read_state(user_id, other_thread_id) is True
