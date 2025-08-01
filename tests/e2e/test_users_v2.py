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


@pytest.fixture(name="original_stats")
def get_original_stats(
    api_client: APIClient,
) -> tuple[dict[str, Any], str, str]:
    """Setup the initial data structure and save stats."""
    backend: patched_mysql_backend = patched_mysql_backend()
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


def test_handles_removing_flags(
    api_client: APIClient,
    original_stats: tuple[dict[str, Any], str, str],
) -> None:
    """Test handling removing abuse flags."""
    backend = patched_mysql_backend()
    stats, username, course_id = original_stats

    user = backend.get_user_by_username(username)
    assert isinstance(user, dict)
    assert user is not None

    # Find a comment with existing abuse flaggers
    comment = backend.find_comment(
        author_id=user.get("_id"), course_id=course_id, with_abuse_flaggers=True
    )
    assert comment is not None

    # Set abuse flaggers to two users
    backend.update_comment(str(comment.get("_id")), abuse_flaggers=["1", "2"])

    # Remove the flag for the first user
    response = api_client.put_json(
        f"/api/v2/comments/{str(comment.get('_id'))}/abuse_unflag",
        data={"user_id": "1"},
    )
    assert response.status_code == 200

    # Fetch new stats, the active flags should stay the same (still one flagger left)
    new_stats = get_new_stats(api_client, course_id, username)

    assert new_stats is not None
    assert new_stats["active_flags"] == stats["active_flags"]

    # Remove the flag for the second user
    response = api_client.put_json(
        f"/api/v2/comments/{str(comment.get('_id'))}/abuse_unflag",
        data={"user_id": "2"},
    )
    assert response.status_code == 200

    # Fetch stats again, now the active flags should reduce by one
    response = api_client.get_json(f"/api/v2/users/{course_id}/stats", params={})
    assert response.status_code == 200
    res_data = response.json()["user_stats"]
    new_stats = next(stats for stats in res_data if stats["username"] == username)

    assert new_stats is not None
    assert new_stats["active_flags"] == stats["active_flags"] - 1
