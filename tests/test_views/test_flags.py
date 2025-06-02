"""Test flags api endpoints."""

import pytest

from forum.backends.mysql.api import MySQLBackend as patched_mysql_backend
from test_utils.client import APIClient

pytestmark = pytest.mark.django_db


def test_comment_thread_api(api_client: APIClient) -> None:
    """
    Test the comment thread flag API.

    This test checks that a user can flag a comment thread for abuse and then unflag it.
    """
    backend = patched_mysql_backend
    flag_user = backend.generate_id()
    author_user = backend.generate_id()
    backend.find_or_create_user(flag_user, flag_user)
    backend.find_or_create_user(author_user, author_user)
    comment_thread_id = backend.create_thread(
        {
            "title": "Thread 1",
            "body": "Body 1",
            "course_id": "course1",
            "commentable_id": "3",
            "author_id": author_user,
            "author_username": author_user,
            "abuse_flaggers": [],
            "historical_abuse_flaggers": [],
        }
    )

    response = api_client.put_json(
        f"/api/v2/threads/{comment_thread_id}/abuse_flag",
        data={"user_id": str(flag_user)},
    )

    assert response.status_code == 200
    comment_thread = response.json()
    assert comment_thread["abuse_flaggers"] == [str(flag_user)]

    # Call API second time, it should not update the results.
    response = api_client.put_json(
        f"/api/v2/threads/{comment_thread_id}/abuse_flag",
        data={"user_id": str(flag_user)},
    )

    assert response.status_code == 200
    comment_thread = response.json()
    assert comment_thread["abuse_flaggers"] == [str(flag_user)]

    response = api_client.put_json(
        path=f"/api/v2/threads/{comment_thread_id}/abuse_unflag",
        data={"user_id": str(flag_user)},
    )
    assert response.status_code == 200
    comment = backend.get_thread(comment_thread_id)
    assert comment is not None
    assert comment["abuse_flaggers"] == []


def test_comment_flag_api(api_client: APIClient) -> None:
    """
    Test the comment flag API.

    This test checks that a user can flag a comment for abuse and then unflag it.
    """
    backend = patched_mysql_backend
    flag_user = backend.generate_id()
    author_user = backend.generate_id()
    backend.find_or_create_user(flag_user, flag_user)
    backend.find_or_create_user(author_user, author_user)
    course_id = "course-xyz"
    comment_thread_id = backend.create_thread(
        {
            "title": "Thread 1",
            "body": "Body 1",
            "course_id": course_id,
            "commentable_id": "3",
            "author_id": author_user,
            "author_username": author_user,
            "abuse_flaggers": [],
            "historical_abuse_flaggers": [],
        }
    )
    comment_id = backend.create_comment(
        {
            "body": "<p>Comment 1</p>",
            "course_id": course_id,
            "author_id": author_user,
            "comment_thread_id": comment_thread_id,
            "author_username": author_user,
            "anonymous": False,
            "anonymous_to_peers": False,
            "depth": 0,
        }
    )

    response = api_client.put_json(
        f"/api/v2/comments/{comment_id}/abuse_flag",
        data={"user_id": str(flag_user)},
    )
    assert response.status_code == 200
    comment_thread = response.json()
    assert comment_thread["abuse_flaggers"] == [str(flag_user)]

    response = api_client.put_json(
        path=f"/api/v2/comments/{comment_id}/abuse_unflag",
        data={"user_id": str(flag_user)},
    )
    assert response.status_code == 200
    comment = backend.get_comment(comment_id)
    assert comment is not None
    assert comment["abuse_flaggers"] == []

    response = api_client.put_json(
        path=f"/api/v2/comments/{comment_id}/abuse_unflag",
        data={"user_id": str(flag_user)},
    )
    assert response.status_code == 200
    comment = backend.get_comment(comment_id)
    assert comment is not None
    assert comment["abuse_flaggers"] == []


def test_comment_flag_api_invalid_data(
    api_client: APIClient,
) -> None:
    """
    Test the comment flag API with invalid data.

    This test checks that the API returns a 400 error when the user or comment does not exist.
    """
    backend = patched_mysql_backend
    user = backend.generate_id()
    backend.find_or_create_user(user)
    comment_id = backend.generate_id()

    response = api_client.put_json(
        path=f"/api/v2/comments/{comment_id}/abuse_flag",
        data={"user_id": str(user)},
    )
    assert response.status_code == 400
    assert response.json() == {"error": "User / Comment doesn't exist"}


def test_comment_flag_api_with_all_param(
    api_client: APIClient,
) -> None:
    """
    Test the comment flag API with the `all` parameter.

    This test checks that a user can flag a comment for abuse and then unflag it using all.
    """
    backend = patched_mysql_backend
    flag_user = backend.generate_id()
    flag_user_2 = backend.generate_id()
    author_user = backend.generate_id()
    backend.find_or_create_user(flag_user, flag_user)
    backend.find_or_create_user(flag_user_2, flag_user_2)
    backend.find_or_create_user(author_user, author_user)
    course_id = "course-xyz"
    comment_thread_id = backend.create_thread(
        {
            "title": "Test Thread",
            "body": "This is a test thread",
            "course_id": "course1",
            "commentable_id": "commentable",
            "author_id": author_user,
            "author_username": author_user,
        }
    )
    comment_id = backend.create_comment(
        {
            "body": "<p>Comment 1</p>",
            "course_id": course_id,
            "author_id": author_user,
            "comment_thread_id": comment_thread_id,
            "author_username": author_user,
            "abuse_flaggers": [],
            "historical_abuse_flaggers": [],
        }
    )

    comment = backend.get_comment(comment_id)
    assert comment is not None
    assert comment["abuse_flaggers"] == []

    response = api_client.put_json(
        f"/api/v2/comments/{comment_id}/abuse_flag",
        data={"user_id": flag_user},
    )

    assert response.status_code == 200
    flagged_comment = response.json()
    assert flagged_comment["abuse_flaggers"] == [str(flag_user)]

    response = api_client.put_json(
        f"/api/v2/comments/{comment_id}/abuse_flag",
        data={"user_id": flag_user_2},
    )

    assert response.status_code == 200
    flagged_comment = response.json()
    assert flagged_comment is not None
    comment = backend.get_comment(flagged_comment["id"])
    assert comment is not None
    assert comment["abuse_flaggers"] == [flag_user, flag_user_2]
    assert comment["historical_abuse_flaggers"] == []

    response = api_client.put_json(
        path=f"/api/v2/comments/{comment_id}/abuse_unflag",
        data={"user_id": flag_user, "all": True},
    )

    assert response.status_code == 200
    unflagged_comment = response.json()
    assert unflagged_comment is not None
    comment = backend.get_comment(unflagged_comment["id"])
    assert comment is not None
    assert comment["abuse_flaggers"] == []
    assert set(comment["historical_abuse_flaggers"]) == set([flag_user, flag_user_2])

    # Test thread abuse and unabuse.
    response = api_client.put_json(
        f"/api/v2/threads/{comment_thread_id}/abuse_flag",
        data={"user_id": flag_user},
    )

    assert response.status_code == 200
    flagged_thread = response.json()
    assert flagged_thread is not None
    thread = backend.get_thread(flagged_thread["id"])
    assert thread is not None
    assert thread["abuse_flaggers"] == [flag_user]
    assert thread["historical_abuse_flaggers"] == []

    response = api_client.put_json(
        path=f"/api/v2/threads/{comment_thread_id}/abuse_unflag",
        data={"user_id": flag_user, "all": True},
    )

    assert response.status_code == 200
    unflagged_thread = response.json()
    assert unflagged_thread is not None
    thread = backend.get_thread(unflagged_thread["id"])
    assert thread is not None
    assert thread["abuse_flaggers"] == []
    assert thread["historical_abuse_flaggers"] == [flag_user]


def test_flag_unflag_thread_twice(
    api_client: APIClient,
) -> None:
    """
    Test flagging a thread, unflagging it, flagging it again, and unflagging it again.
    """
    backend = patched_mysql_backend
    flag_user = backend.generate_id()
    author_user = backend.generate_id()
    backend.find_or_create_user(flag_user, flag_user)
    backend.find_or_create_user(author_user, author_user)
    comment_thread_id = backend.create_thread(
        {
            "title": "Thread 1",
            "body": "Body 1",
            "course_id": "course1",
            "commentable_id": "3",
            "author_id": author_user,
            "author_username": author_user,
            "abuse_flaggers": [],
            "historical_abuse_flaggers": [],
        }
    )

    # Flag the thread
    response = api_client.put_json(
        f"/api/v2/threads/{comment_thread_id}/abuse_flag",
        data={"user_id": flag_user},
    )
    assert response.status_code == 200
    flagged_thread = response.json()
    assert flagged_thread is not None
    thread = backend.get_thread(flagged_thread["id"])
    assert thread is not None
    assert thread["abuse_flaggers"] == [flag_user]
    # After first flag, historical_abuse_flaggers should be unchanged or contain flag_user
    assert (
        flag_user in thread["historical_abuse_flaggers"]
        or thread["historical_abuse_flaggers"] == []
    )

    # Unflag the thread
    response = api_client.put_json(
        path=f"/api/v2/threads/{comment_thread_id}/abuse_unflag",
        data={"user_id": flag_user, "all": True},
    )
    assert response.status_code == 200
    unflagged_thread = response.json()
    assert unflagged_thread is not None
    thread = backend.get_thread(unflagged_thread["id"])
    assert thread is not None
    assert thread["abuse_flaggers"] == []
    # After unflag, historical_abuse_flaggers should contain flag_user
    assert flag_user in thread["historical_abuse_flaggers"]

    # Flag the thread again
    response = api_client.put_json(
        f"/api/v2/threads/{comment_thread_id}/abuse_flag",
        data={"user_id": flag_user},
    )
    assert response.status_code == 200
    flagged_thread = response.json()
    assert flagged_thread is not None
    thread = backend.get_thread(flagged_thread["id"])
    assert thread is not None
    assert thread["abuse_flaggers"] == [flag_user]
    # historical_abuse_flaggers should still contain flag_user (no duplicates)
    assert thread["historical_abuse_flaggers"].count(flag_user) == 1

    # Unflag the thread again
    response = api_client.put_json(
        path=f"/api/v2/threads/{comment_thread_id}/abuse_unflag",
        data={"user_id": flag_user, "all": True},
    )
    assert response.status_code == 200
    unflagged_thread = response.json()
    assert unflagged_thread is not None
    thread = backend.get_thread(unflagged_thread["id"])
    assert thread is not None
    assert thread["abuse_flaggers"] == []
    # historical_abuse_flaggers should still contain flag_user (no duplicates)
    assert thread["historical_abuse_flaggers"].count(flag_user) == 1
