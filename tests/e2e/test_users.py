"""
E2E testcases.
"""

import random
import time
from typing import Any, Optional

import pytest
from faker import Faker

from forum.backends.mysql.api import MySQLBackend as patched_mysql_backend
from test_utils.client import APIClient

fake = Faker()
pytestmark = pytest.mark.django_db


def setup_10_threads(author_id: str, author_username: str, backend: Any) -> list[str]:
    """Create 10 threads for a user."""
    ids = []
    for thread in range(10):
        thread_id = backend.create_thread(
            {
                "title": f"Test Thread {thread}",
                "body": "This is a test thread",
                "course_id": "course1",
                "commentable_id": "commentable1",
                "author_id": author_id,
                "author_username": author_username,
            },
        )
        backend.create_comment(
            {
                "body": "This is a test comment",
                "course_id": "course1",
                "author_id": author_id,
                "comment_thread_id": str(thread_id),
                "author_username": author_username,
            },
        )
        ids.append(thread_id)
    return ids


def add_flags(
    content_type: str,
    content_data: Optional[dict[str, Any]],
    expected_data: dict[str, Any],
    backend: Any,
) -> None:
    """Add abuse flags to the content and update expected data."""
    if not content_data:
        return

    abuse_flaggers = list(range(1, random.randint(0, 3)))
    historical_abuse_flaggers = list(range(1, random.randint(0, 2)))

    if content_type == "comment":
        backend.update_comment(
            str(content_data["_id"]),
            abuse_flaggers=abuse_flaggers,
            historical_abuse_flaggers=historical_abuse_flaggers,
        )
    else:
        backend.update_thread(
            str(content_data["_id"]),
            abuse_flaggers=abuse_flaggers,
            historical_abuse_flaggers=historical_abuse_flaggers,
        )

    expected_data[content_data["author_id"]]["active_flags"] += (
        1 if abuse_flaggers else 0
    )
    expected_data[content_data["author_id"]]["inactive_flags"] += (
        1 if historical_abuse_flaggers else 0
    )


def build_structure_and_response(
    course_id: str,
    authors: list[dict[str, Any]],
    backend: Any,
    build_initial_stats: bool = True,
    with_timestamps: bool = False,
) -> dict[str, dict[str, Any]]:
    """Build the content structure and expected response."""

    assert authors is not None
    assert not any(not item for item in authors)

    expected_data: dict[str, dict[str, Any]] = {
        str(author["external_id"]): {
            "username": author["username"],
            "active_flags": 0,
            "inactive_flags": 0,
            "threads": 0,
            "responses": 0,
            "replies": 0,
        }
        for author in authors
    }

    for _ in range(10):
        thread_author = random.choice(authors)
        expected_data[str(thread_author["external_id"])]["threads"] += 1
        if with_timestamps:
            expected_data[str(thread_author["external_id"])]["last_activity_at"] = (
                time.strftime("%Y-%m-%dT%H:%M:%SZ")
            )
        thread_id = backend.create_thread(
            {
                "title": fake.word(),
                "body": fake.sentence(),
                "course_id": course_id,
                "commentable_id": "course",
                "author_id": thread_author["external_id"],
            },
        )
        thread = backend.get_thread(thread_id) or {}

        add_flags("thread", thread, expected_data, backend)

        for _ in range(5):
            comment_author = random.choice(authors)
            expected_data[str(comment_author["external_id"])]["responses"] += 1
            if with_timestamps:
                expected_data[str(comment_author["external_id"])][
                    "last_activity_at"
                ] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
            comment_id = backend.create_comment(
                {
                    "body": fake.sentence(),
                    "course_id": course_id,
                    "author_id": comment_author["external_id"],
                    "comment_thread_id": thread_id,
                },
            )
            comment = backend.get_comment(comment_id) or {}

            add_flags("comment", comment, expected_data, backend)

            for _ in range(2):
                reply_author = random.choice(authors)
                expected_data[str(reply_author["external_id"])]["replies"] += 1
                if with_timestamps:
                    expected_data[str(reply_author["external_id"])][
                        "last_activity_at"
                    ] = time.strftime("%Y-%m-%dT%H:%M:%SZ")

                reply_id = backend.create_comment(
                    {
                        "body": fake.sentence(),
                        "course_id": course_id,
                        "author_id": reply_author["external_id"],
                        "parent_id": str(comment["_id"]),
                        "comment_thread_id": thread_id,
                    },
                )
                reply = backend.get_comment(reply_id) or {}

                add_flags("comment", reply, expected_data, backend)

    if build_initial_stats:
        for author in authors:
            backend.build_course_stats(author["_id"], course_id)

    return expected_data


@pytest.mark.parametrize("sort_key", [None, "recency", "flagged"])
def test_get_user_stats(
    api_client: Any,
    sort_key: Optional[str],
) -> None:
    """Test retrieving user stats with various sorting options."""
    backend = patched_mysql_backend()
    course_id = fake.word()
    authors_ids = [
        backend.find_or_create_user(str(i), username=f"author-{i}") for i in range(1, 7)
    ]
    authors = [backend.get_user(author_id) or {} for author_id in authors_ids]

    build_structure_and_response(course_id, authors, backend)

    params = {"sort_key": sort_key, "with_timestamps": "true"}
    response = api_client.get_json(f"/api/v2/users/{course_id}/stats", params)
    assert response.status_code == 200

    res_data = response.json()["user_stats"]

    if sort_key == "recency":
        expected_order = sorted(
            res_data, key=lambda x: (x["last_activity_at"], x["username"]), reverse=True
        )
    elif sort_key == "flagged":
        expected_order = sorted(
            res_data,
            key=lambda x: (x["active_flags"], x["inactive_flags"], x["username"]),
            reverse=True,
        )
    else:
        expected_order = sorted(
            res_data,
            key=lambda x: (x["threads"], x["responses"], x["replies"], x["username"]),
            reverse=True,
        )

    assert res_data == expected_order


def test_stats_for_user_with_no_activity(api_client: Any) -> None:
    """Test handling stats for user with no activity."""
    invalid_course_id = "course-v1:edX+DNE+Not_EXISTS"

    response = api_client.get_json(
        f"/api/v2/users/{invalid_course_id}/stats", params={}
    )
    assert response.status_code == 200

    res_data = response.json()["user_stats"]
    assert res_data == []


def test_user_stats_filtered_by_user(
    api_client: Any,
) -> None:
    """Test returning user stats filtered by usernames with default/activity sort."""
    backend = patched_mysql_backend()
    course_id = fake.word()

    # Create some users
    authors_ids = [
        backend.find_or_create_user(str(i), username=f"userauthor-{i}")
        for i in range(1, 11)
    ]
    authors = [backend.get_user(author_id) or {} for author_id in authors_ids]

    # Build structure and response
    full_data = build_structure_and_response(course_id, authors, backend)

    # Randomly sample and shuffle usernames
    usernames = [
        "userauthor-1"
    ]  # random.sample([f"userauthor-{i}" for i in range(1, 4)], 2)

    usernames_str = ",".join(usernames)

    # Get user stats filtered by usernames
    response = api_client.get_json(
        f"/api/v2/users/{course_id}/stats?usernames={usernames_str}", params={}
    )
    assert response.status_code == 200

    res_data = response.json()["user_stats"]

    # Sort the map entries using the usernames order
    expected_result = sorted(
        [data for data in full_data.values() if data["username"] in usernames],
        key=lambda x: usernames.index(x["username"]),
    )

    assert res_data == expected_result


def test_user_stats_with_recency_sort(
    api_client: APIClient,
) -> None:
    """Test returning user stats with recency sort."""
    backend = patched_mysql_backend()
    course_id = fake.word()
    # Create some users
    authors_ids = [
        backend.find_or_create_user(str(i), username=f"userauthor-{i}")
        for i in range(1, 6)
    ]
    authors = [backend.get_user(author_id) or {} for author_id in authors_ids]

    # Build structure with timestamps
    build_structure_and_response(course_id, authors, backend, with_timestamps=True)

    # Get user stats sorted by recency
    response = api_client.get_json(
        f"/api/v2/users/{course_id}/stats",
        params={"sort_key": "recency", "with_timestamps": "true"},
    )
    assert response.status_code == 200

    res_data = response.json()["user_stats"]

    # Sort by last_activity_at and username in reverse order
    sorted_order = sorted(
        res_data, key=lambda x: (x["last_activity_at"], x["username"]), reverse=True
    )

    assert res_data == sorted_order


@pytest.fixture(name="original_stats")
def get_original_stats(
    api_client: APIClient,
) -> tuple[dict[str, Any], str, str]:
    """Setup the initial data structure and save stats."""
    backend = patched_mysql_backend()
    course_id = fake.word()
    authors_ids = [
        backend.find_or_create_user(str(i), username=f"userauthor-{i}")
        for i in range(1, 4)
    ]
    authors = [backend.get_user(author_id) or {} for author_id in authors_ids]

    build_structure_and_response(course_id, authors, backend)

    response = api_client.get_json(f"/api/v2/users/{course_id}/stats", params={})
    assert response.status_code == 200

    res_data = response.json()["user_stats"]

    # Save original stats for the first entry
    org_stats = res_data[0]
    org_username = org_stats["username"]

    return org_stats, org_username, course_id


def get_new_stats(
    api_client: APIClient,
    course_id: str,
    original_username: str,
) -> Optional[dict[str, Any]]:
    """Fetch the new stats after performing actions."""
    response = api_client.get_json(f"/api/v2/users/{course_id}/stats", params={})
    assert response.status_code == 200

    res_data = response.json()["user_stats"]
    return next(
        (stat for stat in res_data if stat["username"] == original_username), None
    )


def test_handles_deleting_threads(
    api_client: APIClient,
    original_stats: tuple[dict[str, Any], str, str],
) -> None:
    """Test handling deleting threads."""
    backend = patched_mysql_backend()
    stats, username, course_id = original_stats

    user = backend.get_user_by_username(username)
    assert user is not None
    assert isinstance(user, dict)

    thread = backend.find_thread(author_id=user.get("_id"), course_id=course_id)
    assert thread is not None

    response = api_client.delete_json(f"/api/v2/threads/{str(thread['_id'])}")
    assert response.status_code == 200

    new_stats = get_new_stats(api_client, course_id, username)

    assert new_stats is not None
    assert new_stats["threads"] == stats["threads"] - 1
    assert new_stats["responses"] <= stats["responses"]
    assert new_stats["replies"] <= stats["replies"]


def test_handles_updating_threads(
    api_client: APIClient,
    original_stats: tuple[dict[str, Any], str, str],
) -> None:
    """Test handling updating threads."""
    backend = patched_mysql_backend()
    stats, username, course_id = original_stats

    user = backend.get_user_by_username(username)
    assert user is not None
    assert isinstance(user, dict)

    thread = backend.find_thread(author_id=user.get("_id"), course_id=course_id)
    assert thread is not None

    response = api_client.put_json(
        f"/api/v2/threads/{thread['_id']}",
        data={
            "body": "new body",
            "title": "new title",
            "commentable_id": "new_commentable_id",
            "thread_type": "question",
            "user_id": 1,
        },
    )
    assert response.status_code == 200

    new_stats = get_new_stats(api_client, course_id, username)

    assert new_stats is not None
    assert new_stats["threads"] == stats["threads"]
    assert new_stats["responses"] == stats["responses"]
    assert new_stats["replies"] == stats["replies"]


def test_handles_adding_threads(
    api_client: APIClient,
    original_stats: tuple[dict[str, Any], str, str],
) -> None:
    """Test handling adding threads."""
    stats, username, course_id = original_stats

    response = api_client.post_json(
        "/api/v2/course/threads",
        data={
            "title": "new thread",
            "body": "new thread",
            "course_id": course_id,
            "user_id": username.replace("userauthor-", ""),
        },
    )
    assert response.status_code == 200

    new_stats = get_new_stats(api_client, course_id, username)

    assert new_stats is not None
    assert new_stats["threads"] == stats["threads"] + 1
    assert new_stats["responses"] == stats["responses"]
    assert new_stats["replies"] == stats["replies"]


def test_handles_deleting_responses(
    api_client: APIClient,
    original_stats: tuple[dict[str, Any], str, str],
) -> None:
    """Test handling deleting responses."""
    backend = patched_mysql_backend()
    stats, username, course_id = original_stats

    user = backend.get_user_by_username(username)
    assert user is not None
    assert isinstance(user, dict)

    comment = backend.find_comment(
        author_id=user.get("_id"), course_id=course_id, parent_id=None
    )
    assert comment is not None

    response = api_client.delete_json(f"/api/v2/comments/{str(comment.get('_id'))}")
    assert response.status_code == 200

    new_stats = get_new_stats(api_client, course_id, username)

    assert new_stats is not None
    assert new_stats["threads"] == stats["threads"]
    assert new_stats["responses"] == stats["responses"] - 1
    assert new_stats["replies"] <= stats["replies"]


def test_handles_updating_responses(
    api_client: APIClient,
    original_stats: tuple[dict[str, Any], str, str],
) -> None:
    """Test handling updating responses."""
    backend = patched_mysql_backend()
    stats, username, course_id = original_stats

    user = backend.get_user_by_username(username)
    assert user is not None
    assert isinstance(user, dict)

    comment = backend.find_comment(author_id=user.get("_id"), course_id=course_id)
    assert comment is not None

    response = api_client.put_json(
        f"/api/v2/comments/{comment.get('_id')}",
        data={"body": "new body", "user_id": "1"},
    )
    assert response.status_code == 200

    new_stats = get_new_stats(api_client, course_id, username)

    assert new_stats is not None
    assert new_stats["threads"] == stats["threads"]
    assert new_stats["responses"] == stats["responses"]
    assert new_stats["replies"] == stats["replies"]


def test_handles_deleting_replies(
    api_client: APIClient,
    original_stats: tuple[dict[str, Any], str, str],
) -> None:
    """Test handling deleting replies."""
    backend = patched_mysql_backend()
    stats, username, course_id = original_stats

    user = backend.get_user_by_username(username)
    assert user is not None
    assert isinstance(user, dict)

    # Find a reply (comment with a parent_id)
    reply = backend.find_comment(
        author_id=user.get("_id"), course_id=course_id, is_parent_comment=False
    )
    assert reply is not None

    # Delete the reply
    response = api_client.delete_json(f"/api/v2/comments/{str(reply.get('_id'))}")
    assert response.status_code == 200
    # Fetch new stats
    new_stats = get_new_stats(api_client, course_id, username)

    # Thread count should stay the same
    assert new_stats is not None
    assert new_stats["threads"] == stats["threads"]
    assert new_stats["responses"] == stats["responses"]
    assert new_stats["replies"] == stats["replies"] - 1


def test_build_course_stats_with_anonymous_posts(
    api_client: APIClient,
) -> None:
    """Test that anonymous posts are not included in user stats after a non-anonymous post."""
    backend = patched_mysql_backend()
    # Create a test user
    user_id = backend.find_or_create_user(user_id="3", username="user3")
    course_id = "course-1"

    threads_ids = []

    # Create threads
    for i in range(len(range(3))):
        response = api_client.post_json(
            "/api/v2/course/threads",
            data={
                "title": f"thread_{i}",
                "body": f"thread {i} by author",
                "course_id": course_id,
                "user_id": user_id,
                "anonymous_to_peers": "true" if i == 0 else "false",
                "anonymous": "true" if i == 1 else "false",
            },
        )
        assert response.status_code == 200
        threads_ids.append(response.json()["id"])

    # Fetch the user stats
    response = api_client.get_json(f"/api/v2/users/{course_id}/stats", {})
    assert response.status_code == 200

    # Parse response data
    stats = response.json()

    # Assert that only the non-anonymous post is included in stats
    assert stats["user_stats"][0]["replies"] == 0
    assert stats["user_stats"][0]["responses"] == 0
    assert stats["user_stats"][0]["threads"] == 1


def test_update_user_stats(api_client: APIClient) -> None:
    """Test that user stats are updated when requested."""
    backend = patched_mysql_backend()
    # Create a test course ID and users
    course_id = fake.word()
    authors_ids = [
        backend.find_or_create_user(user_id=str(i), username=f"author-{i}")
        for i in range(1, 7)
    ]
    authors = [backend.get_user(author_id) or {} for author_id in authors_ids]
    # Build the expected data without initial stats
    expected_data = build_structure_and_response(
        course_id, authors, backend, build_initial_stats=False
    )

    # Sort the data for expected result (threads, responses, replies)
    expected_result = sorted(
        expected_data.values(),
        key=lambda val: (val["threads"], val["responses"], val["replies"]),
        reverse=True,
    )

    # Fetch user stats (before updating)
    response = api_client.get_json(f"/api/v2/users/{course_id}/stats", {})
    assert response.status_code == 200
    res = response.json()
    assert res["user_stats"] != expected_result  # User stats should not be updated yet

    # Request to update user stats
    response = api_client.post_json(f"/api/v2/users/{course_id}/update_stats", {})
    assert response.status_code == 200
    res = response.json()
    assert res["user_count"] == 6  # Confirm all 6 users are counted

    # Fetch user stats (after updating)
    response = api_client.get_json(f"/api/v2/users/{course_id}/stats", {})
    assert response.status_code == 200
    res = response.json()

    assert (
        res["user_stats"] == expected_result
    )  # User stats should now match the expected data


def test_mark_thread_as_read(api_client: APIClient) -> None:
    """Test that a thread is marked as read for the user."""
    backend = patched_mysql_backend()
    user_id = "1"
    username = "user1"
    backend.find_or_create_user(user_id=user_id, username=username)

    # Setup 10 threads for testing
    threads_ids = setup_10_threads(user_id, username, backend)
    thread = backend.get_thread(threads_ids[0]) or {}

    # Create a test user
    user_id = backend.find_or_create_user(user_id="42", username="user-42")

    # Mark the first thread as read
    response = api_client.post_json(
        f"/api/v2/users/{user_id}/read",
        data={"source_type": "thread", "source_id": str(thread["_id"])},
    )
    assert response.status_code == 200

    # Reload the user and verify read state
    user = backend.get_user(user_id) or {}
    read_states = [
        course_state
        for course_state in user["read_states"]
        if course_state["course_id"] == thread["course_id"]
    ]
    read_date = read_states[0]["last_read_times"][str(thread["_id"])]

    assert (
        read_date >= thread["updated_at"]
    )  # Verify the read date is on or after the thread's updated_at


def test_retire_user_inactive(
    api_client: APIClient,
) -> None:
    """Test retiring an inactive user."""

    backend = patched_mysql_backend()
    user_id = backend.find_or_create_user(user_id="1", username="user1")
    user = backend.get_user(user_id) or {}

    # Verify user is not subscribed to any threads
    response = api_client.get_json(
        f"/api/v2/users/{user['external_id']}/subscribed_threads",
        params={"course_id": "1"},
    )
    assert response.status_code == 200
    assert response.json()["thread_count"] == 0

    response = api_client.get_json(
        f"/api/v2/users/{user['external_id']}/subscribed_threads",
        params={"course_id": "2"},
    )
    assert response.status_code == 200
    assert response.json()["thread_count"] == 0

    # Retire the user
    retired_username = "retired_username_ABCD1234"
    response = api_client.post_json(
        f"/api/v2/users/{user['external_id']}/retire",
        data={"retired_username": retired_username},
    )
    assert response.status_code == 200

    user = backend.get_user(user_id) or {}
    assert user["username"] == retired_username
    assert user["email"] == ""

    content = backend.get_user_contents_by_username(retired_username)
    assert len(content) == 0
