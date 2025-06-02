"""Tests for subscription apis."""

import pytest

from forum.backends.mysql.api import MySQLBackend as patched_mysql_backend
from test_utils.client import APIClient

pytestmark = pytest.mark.django_db


def test_get_subscribed_threads(
    api_client: APIClient,
) -> None:
    """
    Test getting subscribed threads for a user.
    """
    backend = patched_mysql_backend
    user_id = "1"
    username = "user1"
    course_id = "demo_course"
    backend.find_or_create_user(user_id, username=username)

    comment_thread_id = backend.create_thread(
        {
            "title": "Thread 1",
            "body": "Body 1",
            "course_id": course_id,
            "thread_type": "discussion",
            "author_id": user_id,
            "author_username": username,
        }
    )
    backend.subscribe_user(user_id, comment_thread_id, source_type="CommentThread")
    response = api_client.get(
        f"/api/v2/users/{user_id}/subscribed_threads?course_id={course_id}"
    )
    assert response.status_code == 200
    threads = response.json()["collection"]
    assert len(threads) == 1
    assert threads[0]["id"] == comment_thread_id


def test_get_subscribed_threads_with_filters(
    api_client: APIClient,
) -> None:
    """
    Test getting subscribed threads for a user with filters.
    """
    backend = patched_mysql_backend
    user_id = "1"
    username = "user1"
    course_id = "demo_course"
    backend.find_or_create_user(user_id, username=username)
    comment_thread_id = backend.create_thread(
        {
            "title": "Thread 1",
            "body": "Body 1",
            "course_id": course_id,
            "author_id": user_id,
            "author_username": username,
        }
    )
    backend.subscribe_user(user_id, comment_thread_id, source_type="CommentThread")

    response = api_client.get(
        f"/api/v2/users/{user_id}/subscribed_threads?flagged=true&course_id={course_id}"
    )
    assert response.status_code == 200
    threads = response.json()["collection"]
    assert len(threads) == 0

    backend.update_thread(comment_thread_id, abuse_flaggers=[user_id])
    response = api_client.get(
        f"/api/v2/users/{user_id}/subscribed_threads?flagged=true&course_id={course_id}"
    )
    assert response.status_code == 200
    threads = response.json()["collection"]
    assert len(threads) == 1
    assert threads[0]["id"] == comment_thread_id


def test_subscribe_thread(api_client: APIClient) -> None:
    """
    Test subscribing to a thread.
    """
    backend = patched_mysql_backend
    user_id = "1"
    course_id = "demo_course"
    username = "user1"
    author_id = "2"
    author_username = "author"
    backend.find_or_create_user(user_id, username)
    backend.find_or_create_user(author_id, author_username)
    comment_thread_id = backend.create_thread(
        {
            "title": "Thread 1",
            "body": "Body 1",
            "course_id": course_id,
            "author_id": author_id,
            "author_username": author_username,
        }
    )
    response = api_client.post(
        f"/api/v2/users/{user_id}/subscriptions",
        data={"source_type": "thread", "source_id": comment_thread_id},
    )
    assert response.status_code == 200
    subscription = backend.subscribe_user(
        user_id, comment_thread_id, source_type="CommentThread"
    )
    assert subscription is not None


def test_unsubscribe_thread(api_client: APIClient) -> None:
    """
    Test unsubscribing from a thread.
    """
    backend = patched_mysql_backend
    user_id = "1"
    course_id = "demo_course"
    username = "user1"
    author_id = "2"
    author_username = "author"
    backend.find_or_create_user(user_id, username)
    backend.find_or_create_user(author_id, author_username)
    comment_thread_id = backend.create_thread(
        {
            "title": "Thread 1",
            "body": "Body 1",
            "course_id": course_id,
            "author_id": author_id,
            "author_username": author_username,
        }
    )
    backend.subscribe_user(user_id, comment_thread_id, source_type="CommentThread")

    response = api_client.delete(
        f"/api/v2/users/{user_id}/subscriptions?source_id={comment_thread_id}"
    )
    assert response.status_code == 200
    assert backend.get_subscription(user_id, comment_thread_id) is None

    # Attempt to unsubscribe from a thread that the user is not subscribed to
    response = api_client.delete(
        f"/api/v2/users/{user_id}/subscriptions?source_id={comment_thread_id}"
    )
    assert response.status_code == 400


def test_get_subscribed_threads_with_pagination(
    api_client: APIClient,
) -> None:
    """
    Test getting subscribed threads for a user with pagination.
    """
    backend = patched_mysql_backend
    user_id = "1"
    course_id = "demo_course"
    username = "user1"
    author_id = "2"
    author_username = "author"
    backend.find_or_create_user(user_id, username)
    backend.find_or_create_user(author_id, author_username)
    comment_thread_id_1 = backend.create_thread(
        {
            "title": "Thread 1",
            "body": "Body 1",
            "course_id": course_id,
            "author_id": author_id,
            "author_username": author_username,
        }
    )

    comment_thread_id_2 = backend.create_thread(
        {
            "title": "Thread 2",
            "body": "Body 2",
            "course_id": course_id,
            "type": "CommentThread",
            "author_id": author_id,
            "author_username": author_username,
        }
    )

    comment_thread_id_3 = backend.create_thread(
        {
            "title": "Thread 2",
            "body": "Body 2",
            "course_id": course_id,
            "type": "CommentThread",
            "author_id": author_id,
            "author_username": author_username,
        }
    )
    backend.subscribe_user(user_id, comment_thread_id_1, source_type="CommentThread")
    backend.subscribe_user(user_id, comment_thread_id_2, source_type="CommentThread")
    backend.subscribe_user(user_id, comment_thread_id_3, source_type="CommentThread")

    response = api_client.get(
        f"/api/v2/users/{user_id}/subscribed_threads?page=1&per_page=2&course_id={course_id}"
    )
    assert response.status_code == 200
    threads = response.json()["collection"]
    assert len(threads) == 2
    assert threads[0]["id"] in [
        comment_thread_id_1,
        comment_thread_id_2,
        comment_thread_id_3,
    ]

    response = api_client.get(
        f"/api/v2/users/{user_id}/subscribed_threads?page=2&per_page=2&course_id={course_id}"
    )
    assert response.status_code == 200
    threads = response.json()["collection"]
    assert len(threads) == 1
    assert threads[0]["id"] in [
        comment_thread_id_1,
        comment_thread_id_2,
        comment_thread_id_3,
    ]


def test_get_thread_subscriptions(
    api_client: APIClient,
) -> None:
    """
    Test getting subscriptions of a thread.
    """
    backend = patched_mysql_backend
    user_id = "1"
    course_id = "demo_course"
    username = "user1"
    author_id = "2"
    author_username = "author"
    backend.find_or_create_user(user_id, username)
    backend.find_or_create_user(author_id, author_username)
    comment_thread_id = backend.create_thread(
        {
            "title": "Thread 1",
            "body": "Body 1",
            "course_id": course_id,
            "author_id": author_id,
            "author_username": author_username,
        }
    )
    subscription = backend.subscribe_user(
        user_id, comment_thread_id, source_type="CommentThread"
    )
    assert subscription

    response = api_client.get(
        f"/api/v2/threads/{comment_thread_id}/subscriptions?page=1"
    )
    assert response.status_code == 200
    subscriptions = response.json()["collection"]
    assert len(subscriptions) == 1
    assert subscriptions[0]["id"] == subscription["_id"]

    response = api_client.get(
        f"/api/v2/threads/{comment_thread_id}/subscriptions?page=2"
    )
    assert response.status_code == 200
    subscriptions = response.json()["collection"]
    assert len(subscriptions) == 0


def test_get_thread_subscriptions_with_pagination(
    api_client: APIClient,
) -> None:
    """
    Test getting subscriptions of a thread with pagination.
    """
    backend = patched_mysql_backend
    user_id = "1"
    course_id = "demo_course"
    author_id = "10"
    author_username = "author"
    backend.find_or_create_user(author_id, author_username)
    comment_thread_id = backend.create_thread(
        {
            "title": "Thread 1",
            "body": "Body 1",
            "course_id": course_id,
            "author_id": author_id,
            "author_username": author_username,
        }
    )
    user_ids = ["1", "2", "3", "4", "5"]
    for user_id in user_ids:
        backend.find_or_create_user(user_id, username=f"user{user_id}")
        backend.subscribe_user(user_id, comment_thread_id, source_type="CommentThread")

    response = api_client.get(
        f"/api/v2/threads/{comment_thread_id}/subscriptions?page=1&per_page=2"
    )
    assert response.status_code == 200
    subscriptions = response.json()["collection"]
    assert len(subscriptions) == 2
    assert subscriptions[0]["subscriber_id"] == user_ids[0]
    assert subscriptions[1]["subscriber_id"] == user_ids[1]

    response = api_client.get(
        f"/api/v2/threads/{comment_thread_id}/subscriptions?page=2&per_page=2"
    )
    assert response.status_code == 200
    subscriptions = response.json()["collection"]
    assert len(subscriptions) == 2
    assert subscriptions[0]["subscriber_id"] == user_ids[2]
    assert subscriptions[1]["subscriber_id"] == user_ids[3]

    response = api_client.get(
        f"/api/v2/threads/{comment_thread_id}/subscriptions?page=3&per_page=2"
    )
    assert response.status_code == 200
    subscriptions = response.json()["collection"]
    assert len(subscriptions) == 1
    assert subscriptions[0]["subscriber_id"] == user_ids[4]
