"""Test threads api endpoints."""

import time
from typing import Any, Optional
import pytest

from forum.backends.mongodb.api import MongoBackend
from forum.backends.mongodb.users import Users
from test_utils.client import APIClient

pytestmark = pytest.mark.django_db


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


def test_update_thread(api_client: APIClient, patched_get_backend: Any) -> None:
    """Test updating a thread."""
    backend = patched_get_backend
    user_id, thread_id = setup_models(backend=backend)
    response = api_client.put_json(
        f"/api/v2/threads/{thread_id}",
        data={
            "body": "new thread body",
            "title": "new thread title",
            "commentable_id": "new_commentable_id",
            "thread_type": "question",
            "user_id": user_id,
            "editing_user_id": user_id,
        },
    )
    assert response.status_code == 200
    updated_thread = response.json()
    updated_thread_from_db = backend.get_thread(updated_thread["id"])
    assert updated_thread_from_db is not None
    assert updated_thread_from_db["body"] == "new thread body"
    assert updated_thread_from_db["title"] == "new thread title"
    assert updated_thread_from_db["commentable_id"] == "new_commentable_id"
    assert updated_thread_from_db["thread_type"] == "question"


def test_update_thread_without_user_id(
    api_client: APIClient, patched_get_backend: Any
) -> None:
    """Test updaing a thread without user id."""
    backend = patched_get_backend
    _, thread_id = setup_models(backend=backend)
    response = api_client.put_json(
        f"/api/v2/threads/{thread_id}",
        data={
            "body": "new thread body",
            "title": "new thread title",
            "commentable_id": "new_commentable_id",
            "thread_type": "question",
        },
    )
    assert response.status_code == 200
    updated_thread = response.json()
    updated_thread_from_db = backend.get_thread(updated_thread["id"])
    assert updated_thread_from_db is not None
    assert updated_thread_from_db["body"] == "new thread body"
    assert updated_thread_from_db["title"] == "new thread title"
    assert updated_thread_from_db["commentable_id"] == "new_commentable_id"
    assert updated_thread_from_db["thread_type"] == "question"


def test_update_close_reason(api_client: APIClient, patched_get_backend: Any) -> None:
    """Test close a thread through update thread API."""
    backend = patched_get_backend
    user_id, thread_id = setup_models(backend=backend)
    response = api_client.put_json(
        f"/api/v2/threads/{thread_id}",
        data={
            "closed": True,
            "closing_user_id": user_id,
            "close_reason_code": "test_code",
        },
    )
    assert response.status_code == 200
    updated_thread = response.json()
    updated_thread_from_db = backend.get_thread(updated_thread["id"])
    assert updated_thread_from_db is not None
    assert updated_thread_from_db["closed"]
    assert updated_thread_from_db["close_reason_code"] == "test_code"
    assert updated_thread_from_db["closed_by_id"] == user_id


def test_closing_and_reopening_thread_clears_reason_code(
    api_client: APIClient, patched_get_backend: Any
) -> None:
    """Test close a thread and reopen a thread through update thread API."""
    backend = patched_get_backend
    user_id, thread_id = setup_models(backend=backend)
    response = api_client.put_json(
        f"/api/v2/threads/{thread_id}",
        data={
            "closed": True,
            "closing_user_id": user_id,
            "close_reason_code": "test_code",
        },
    )
    assert response.status_code == 200
    response = api_client.put_json(
        f"/api/v2/threads/{thread_id}",
        data={
            "closed": False,
            "closing_user_id": user_id,
            "close_reason_code": "test_code",
        },
    )
    assert response.status_code == 200
    updated_thread = response.json()
    updated_thread_from_db = backend.get_thread(updated_thread["id"])
    assert updated_thread_from_db is not None
    assert not updated_thread_from_db["closed"]
    assert updated_thread_from_db["close_reason_code"] is None
    assert updated_thread_from_db["closed_by_id"] is None


def test_update_thread_not_exist(
    api_client: APIClient, patched_get_backend: Any
) -> None:
    """Test thread does not exists through update thread API."""
    backend = patched_get_backend
    wrong_thread_id = backend.generate_id()
    response = api_client.put_json(
        f"/api/v2/threads/{wrong_thread_id}",
        data={
            "body": "new thread body",
            "title": "new thread title",
        },
    )
    assert response.status_code == 400


def test_unicode_data(api_client: APIClient, patched_get_backend: Any) -> None:
    """Test data through update thread API."""
    backend = patched_get_backend
    user_id, thread_id = setup_models(backend=backend)
    texts = ["测试", "テスト", "test"]
    for text in texts:
        response = api_client.put_json(
            f"/api/v2/threads/{thread_id}",
            data={
                "body": text,
                "title": text,
                "user_id": user_id,
            },
        )
        assert response.status_code == 200
        updated_thread = response.json()
        updated_thread_from_db = backend.get_thread(updated_thread["id"])
        assert updated_thread_from_db is not None
        assert updated_thread_from_db["body"] == text
        assert updated_thread_from_db["title"] == text


def test_delete_thread(api_client: APIClient, patched_get_backend: Any) -> None:
    """Test delete a thread."""
    backend = patched_get_backend
    user_id, thread_id = setup_models(backend=backend)
    comment_id_1, comment_id_2 = create_comments_in_a_thread(backend, thread_id)
    thread_from_db = backend.get_thread(thread_id)
    assert thread_from_db is not None
    assert thread_from_db["comment_count"] == 2
    response = api_client.delete_json(f"/api/v2/threads/{thread_id}")
    assert response.status_code == 200
    assert backend.get_thread(thread_id) is None
    assert backend.get_comment(comment_id_1) is None
    assert backend.get_comment(comment_id_2) is None
    assert backend.get_subscription(subscriber_id=user_id, source_id=thread_id) is None


def test_delete_thread_not_exist(
    api_client: APIClient, patched_get_backend: Any
) -> None:
    """Test thread does not exists through delete thread API."""
    backend = patched_get_backend
    wrong_thread_id = backend.generate_id()
    response = api_client.delete_json(f"/api/v2/threads/{wrong_thread_id}")
    assert response.status_code == 400


def test_invalid_data(api_client: APIClient, patched_get_backend: Any) -> None:
    """Test invalid data"""
    setup_models(patched_get_backend)
    response = api_client.get_json("/api/v2/threads", {})
    assert response.status_code == 400

    params = {"course_id": "course1", "user_id": "4"}
    response = api_client.get_json("/api/v2/threads", params)
    assert response.status_code == 400


def test_filter_by_course(api_client: APIClient, patched_get_backend: Any) -> None:
    """Test filter threads by course id through get thread API."""
    setup_models(patched_get_backend)
    params = {"course_id": "course1"}
    response = api_client.get_json("/api/v2/threads", params)
    assert response.status_code == 200
    results = response.json().get("collection", [])

    assert len(results) == 1
    for _, res in enumerate(results):
        assert res["course_id"] == "course1"


def test_filter_exclude_standalone(
    api_client: APIClient, patched_get_backend: Any
) -> None:
    """Test filter exclude standalone threads through get thread API."""
    backend = patched_get_backend
    setup_models(backend=backend)
    backend.create_thread(
        {
            "title": "Thread 2",
            "body": "Thread 2",
            "course_id": "course1",
            "commentable_id": "CommentThread",
            "author_id": "1",
            "author_username": "user1",
            "abuse_flaggers": [],
            "historical_abuse_flaggers": [],
            "context": "standalone",
        }
    )
    params = {"course_id": "course1"}
    response = api_client.get_json("/api/v2/threads", params)
    assert response.status_code == 200
    results = response.json().get("collection", [])

    assert len(results) == 1
    for _, res in enumerate(results):
        assert res["course_id"] == "course1"
        assert res["context"] == "course"


def test_api_with_count_flagged(
    api_client: APIClient, patched_get_backend: Any
) -> None:
    """Test thread API with count flagged."""
    backend = patched_get_backend
    _, thread_id = setup_models(backend)
    comment_id_1, comment_id_2 = create_comments_in_a_thread(backend, thread_id)

    # Mark Comment 1 as abused
    backend.update_comment(comment_id_1, abuse_flaggers=["1"])

    params = {"course_id": "course1", "count_flagged": "true"}
    response = api_client.get_json("/api/v2/threads", params)
    assert response.status_code == 200
    results = response.json().get("collection", [])

    assert len(results) == 1
    assert results[0]["abuse_flagged_count"] == 1

    # Mark Comment 2 as abused
    backend.update_comment(comment_id_2, abuse_flaggers=["1"])

    params = {"course_id": "course1", "count_flagged": "true"}
    response = api_client.get_json("/api/v2/threads", params)
    assert response.status_code == 200
    results = response.json().get("collection", [])

    assert len(results) == 1
    assert results[0]["abuse_flagged_count"] == 2


def test_no_matching_course_id(api_client: APIClient, patched_get_backend: Any) -> None:
    """Test no matching course id through get thread API."""
    backend = patched_get_backend
    setup_models(backend)
    wrong_course_id = "abc"
    params = {"course_id": wrong_course_id}
    response = api_client.get_json("/api/v2/threads", params)
    assert response.status_code == 200
    results = response.json().get("collection", [])
    assert len(results) == 0


def test_filter_flagged_posts(api_client: APIClient, patched_get_backend: Any) -> None:
    """Test filter flagged posts through get thread API."""
    backend = patched_get_backend
    user_id, thread_id = setup_models(backend)
    tests_flags = [(True, "1"), (False, "0")]
    for flagged, abuse_flaggers in tests_flags:
        action = "flag" if flagged else "unflag"
        response = api_client.put_json(
            path=f"/api/v2/threads/{thread_id}/abuse_{action}",
            data={"user_id": str(user_id), "count_flagged": True},
        )
        params = {"course_id": "course1", "flagged": flagged}
        response = api_client.get_json("/api/v2/threads", params)
        assert response.status_code == 200
        if action == "unflag":
            assert response.json()["collection"] == []
        else:
            result = response.json()["collection"][0]
            assert result["abuse_flaggers"] == [abuse_flaggers]


def test_filter_by_author(api_client: APIClient, patched_get_backend: Any) -> None:
    """Test filter threads by author id through get thread API."""
    backend = patched_get_backend
    user_id1, _ = setup_models(backend=backend)
    user_id2, _ = setup_models(backend, "2", "user2", "course2")

    params = {"course_id": "course1", "author_id": user_id1}
    response = api_client.get_json("/api/v2/threads", params)
    assert response.status_code == 200
    result = response.json()["collection"]
    assert len(result) == 1

    params = {"course_id": "course2", "author_id": user_id2}
    response = api_client.get_json("/api/v2/threads", params)
    assert response.status_code == 200
    result = response.json()["collection"]
    assert len(result) == 1

    wrong_user_id = "3"
    params = {"course_id": "course2", "author_id": wrong_user_id}
    response = api_client.get_json("/api/v2/threads", params)
    assert response.status_code == 200
    result = response.json()["collection"]
    assert len(result) == 0


def test_anonymous_threads(api_client: APIClient, patched_get_backend: Any) -> None:
    """Test Anonymus threads are only visible to Authors"""
    backend = patched_get_backend
    course_id = "course-1"
    author_id = "1"
    author_username = "author-1"
    backend.find_or_create_user(author_id, username=author_username)

    backend.create_thread(
        {
            "title": "Thread 1",
            "body": "Thread 1",
            "course_id": course_id,
            "commentable_id": "CommentThread",
            "author_id": author_id,
            "author_username": author_username,
        }
    )

    backend.create_thread(
        {
            "title": "Thread 2",
            "body": "Thread 2",
            "course_id": course_id,
            "commentable_id": "CommentThread",
            "author_id": author_id,
            "author_username": author_username,
            "anonymous": True,
            "anonymous_to_peers": True,
        }
    )

    user_id = backend.find_or_create_user("2", username="anonymus-user")

    params = {"course_id": course_id, "author_id": author_id, "user_id": user_id}
    response = api_client.get_json("/api/v2/threads", params)
    assert response.status_code == 200
    result = response.json()["collection"]
    assert len(result) == 1

    params = {"course_id": course_id, "author_id": author_id, "user_id": author_id}
    response = api_client.get_json("/api/v2/threads", params)
    assert response.status_code == 200
    result = response.json()["collection"]
    assert len(result) == 2


def test_unresponded_filter(api_client: APIClient, patched_get_backend: Any) -> None:
    """Test unresponded filter"""
    backend = patched_get_backend
    _, thread_id = setup_models(backend)
    create_comments_in_a_thread(backend, thread_id)
    setup_models(backend, "2", "user2")

    response = api_client.get_json(
        "/api/v2/threads", params={"course_id": "course1", "unresponded": "true"}
    )

    assert response.status_code == 200
    thread = response.json()["collection"]
    assert len(thread) == 1


def test_filter_by_post_type(api_client: APIClient, patched_get_backend: Any) -> None:
    """Test filter threads by thread_type through get thread API."""
    backend = patched_get_backend
    setup_models(backend=backend)
    setup_models(backend, "2", "user2", "course1")
    username_3 = "user3"
    user_id_3 = backend.find_or_create_user("3", username_3)
    backend.create_thread(
        {
            "title": "Thread 3",
            "body": "Thread 3",
            "course_id": "course1",
            "commentable_id": "CommentThread",
            "author_id": user_id_3,
            "author_username": username_3,
            "abuse_flaggers": [],
            "historical_abuse_flaggers": [],
            "thread_type": "question",
        }
    )
    params = {"course_id": "course1", "thread_type": "discussion"}
    response = api_client.get_json("/api/v2/threads", params)
    assert response.status_code == 200
    results = response.json()["collection"]
    assert len(results) == 2
    for thread in results:
        assert thread["thread_type"] == "discussion"

    params = {"course_id": "course1", "thread_type": "question"}
    response = api_client.get_json("/api/v2/threads", params)
    assert response.status_code == 200
    results = response.json()["collection"]
    assert len(results) == 1
    for thread in results:
        assert thread["thread_type"] == "question"


def test_filter_unanswered_questions(
    api_client: APIClient, patched_get_backend: Any
) -> None:
    """Test filter unanswered questions through get thread API."""
    backend = patched_get_backend
    course_id = "course1"
    username = "user1"
    user_id_1, thread1 = setup_models(backend, "1", "user1", thread_type="question")
    user_id_2, thread2 = setup_models(backend, "2", "user2", thread_type="question")
    username_3 = "user3"
    user_id_3 = backend.find_or_create_user("3", username_3)
    backend.create_thread(
        {
            "title": "Thread 3",
            "body": "Thread 3",
            "course_id": "course1",
            "commentable_id": "CommentThread",
            "author_id": user_id_3,
            "author_username": username_3,
            "abuse_flaggers": [],
            "historical_abuse_flaggers": [],
            "thread_type": "question",
        }
    )

    params = {"course_id": "course1", "unanswered": True}
    response = api_client.get_json("/api/v2/threads", params)
    assert response.status_code == 200
    results = response.json()["collection"]
    assert len(results) == 3

    comment_id_1 = backend.create_comment(
        {
            "body": "<p>Thread 1 Comment</p>",
            "course_id": course_id,
            "author_id": user_id_1,
            "comment_thread_id": thread1,
            "author_username": username,
        }
    )

    comment_id_2 = backend.create_comment(
        {
            "body": "<p>Thread 2 Comment</p>",
            "course_id": course_id,
            "author_id": user_id_2,
            "comment_thread_id": thread2,
            "author_username": username,
        }
    )

    backend.update_comment(comment_id=comment_id_1, endorsed=True)
    backend.update_comment(comment_id=comment_id_2, endorsed=True)

    # api_client.put_json(
    #     f"/api/v2/threads/{thread1}",
    #     data={"endorsed": True},
    # )
    # api_client.put_json(
    #     f"/api/v2/threads/{thread2}",
    #     data={"endorsed": True},
    # )

    params = {"course_id": "course1", "unanswered": True}
    response = api_client.get_json("/api/v2/threads", params)
    assert response.status_code == 200
    results = response.json()["collection"]
    assert len(results) == 1
    for thread in results:
        assert thread["title"] == "Thread 3"
        assert thread["body"] == "Thread 3"


def test_get_thread(api_client: APIClient, patched_get_backend: Any) -> None:
    """Test get thread by thread_id."""
    backend = patched_get_backend
    _, thread_id = setup_models(backend)
    response = api_client.get_json(
        f"/api/v2/threads/{thread_id}",
        params={
            "recursive": False,
            "with_responses": True,
            "user_id": 6,
            "mark_as_read": False,
            "resp_skip": 0,
            "resp_limit": 10,
            "reverse_order": "true",
            "merge_question_type_responses": False,
        },
    )
    assert response.status_code == 200
    thread = response.json()
    assert thread["body"] == "Thread 1"
    assert thread["title"] == "Thread 1"
    assert thread["commentable_id"] == "CommentThread"
    assert thread["thread_type"] == "discussion"


def test_computes_endorsed_correctly(
    api_client: APIClient, patched_get_backend: Any
) -> None:
    """Test computes endorsed correctly through get thread API."""
    backend = patched_get_backend
    _, thread_id = setup_models(backend)
    comment_id = backend.create_comment(
        {
            "body": "Comment 1",
            "course_id": "course1",
            "author_id": "1",
            "comment_thread_id": thread_id,
            "author_username": "user1",
        }
    )
    backend.update_comment(comment_id=comment_id, endorsed=True)
    response = api_client.get_json(
        f"/api/v2/threads/{thread_id}",
        params={
            "recursive": False,
            "with_responses": True,
            "user_id": 6,
            "mark_as_read": False,
            "resp_skip": 0,
            "resp_limit": 10,
            "reverse_order": "true",
            "merge_question_type_responses": False,
        },
    )
    assert response.status_code == 200
    thread = response.json()
    assert thread["endorsed"] is True


def test_no_children_for_informational_request(
    api_client: APIClient, patched_get_backend: Any
) -> None:
    """Test no children returned from get thread by thread_id API"""
    backend = patched_get_backend
    _, thread_id = setup_models(backend)
    backend.create_comment(
        {
            "body": "Comment 1",
            "course_id": "course1",
            "author_id": "1",
            "comment_thread_id": thread_id,
            "author_username": "user1",
        }
    )
    response = api_client.get_json(
        f"/api/v2/threads/{thread_id}",
        params={
            "recursive": False,
            "with_responses": False,
            "user_id": 6,
            "mark_as_read": False,
            "resp_skip": 0,
            "resp_limit": 10,
            "reverse_order": "true",
            "merge_question_type_responses": False,
        },
    )
    assert response.status_code == 200
    thread = response.json()
    assert "children" not in thread


def test_mark_as_read(api_client: APIClient, patched_get_backend: Any) -> None:
    """Test mark as read"""
    backend = patched_get_backend
    _, thread_id = setup_models(backend)
    response = api_client.get_json(
        f"/api/v2/threads/{thread_id}",
        params={
            "recursive": False,
            "with_responses": True,
            "user_id": 1,
            "mark_as_read": True,
            "resp_skip": 0,
            "resp_limit": 10,
            "reverse_order": "true",
            "merge_question_type_responses": False,
        },
    )
    assert response.status_code == 200
    thread = response.json()
    assert thread["username"] == "user1"
    assert thread["read"] is True


def test_thread_with_comments(api_client: APIClient, patched_get_backend: Any) -> None:
    """Test children returned from get thread by thread_id API"""
    backend = patched_get_backend
    _, thread_id = setup_models(backend)
    comment_id_1, comment_id_2 = create_comments_in_a_thread(backend, thread_id)

    response = api_client.get_json(
        f"/api/v2/threads/{thread_id}",
        params={
            "with_responses": True,
            "mark_as_read": False,
            "reverse_order": "true",
            "merge_question_type_responses": False,
        },
    )
    assert response.status_code == 200
    thread = response.json()
    thread_children = thread["children"]

    assert len(thread_children) == 2
    assert thread_children[0]["id"] == comment_id_2
    assert thread_children[1]["id"] == comment_id_1


def test_endorement_is_none_after_unanswering_a_comment_in_question(
    api_client: APIClient, patched_get_backend: Any
) -> None:
    """
    Test endorsement is None by marking it as unanswered.
    when that question was initialy marked as answered.
    """
    backend = patched_get_backend
    user_id, thread_id = setup_models(backend, thread_type="question")
    comment_id = backend.create_comment(
        {
            "body": "Comment 1",
            "course_id": "course1",
            "author_id": user_id,
            "comment_thread_id": thread_id,
            "author_username": "user1",
        }
    )
    response = api_client.put_json(
        f"/api/v2/comments/{comment_id}",
        data={"endorsed": "True", "endorsement_user_id": user_id},
    )
    assert response.status_code == 200
    comment = backend.get_comment(comment_id)
    assert comment is not None
    assert comment["endorsed"] is True
    assert comment["endorsement"]["user_id"] == user_id

    response = api_client.put_json(
        f"/api/v2/comments/{comment_id}",
        data={"endorsed": "False"},
    )
    assert response.status_code == 200

    response = api_client.get_json(
        f"/api/v2/threads/{thread_id}",
        params={
            "recursive": False,
            "with_responses": True,
            "user_id": 6,
            "mark_as_read": False,
            "resp_skip": 0,
            "resp_limit": 10,
            "reverse_order": "true",
            "merge_question_type_responses": False,
        },
    )
    assert response.status_code == 200
    thread = response.json()
    assert thread["thread_type"] == "question"
    assert thread["children"][0]["endorsement"] is None


def test_response_for_thread_type_question(
    api_client: APIClient, patched_get_backend: Any
) -> None:
    """
    Test responses for thread_type question.
    It varies according to queryparams.
    """
    backend = patched_get_backend
    user_id, thread_id = setup_models(backend, thread_type="question")
    comment_id1 = backend.create_comment(
        {
            "body": "Comment 1",
            "course_id": "course1",
            "author_id": user_id,
            "comment_thread_id": thread_id,
            "author_username": "user1",
        }
    )

    comment_id2 = backend.create_comment(
        {
            "body": "Comment 2",
            "course_id": "course1",
            "author_id": user_id,
            "comment_thread_id": thread_id,
            "author_username": "user1",
        }
    )
    response = api_client.put_json(
        f"/api/v2/comments/{comment_id1}",
        data={"endorsed": "True", "endorsement_user_id": user_id},
    )
    assert response.status_code == 200

    response = api_client.get_json(
        f"/api/v2/threads/{thread_id}",
        params={
            "recursive": False,
            "with_responses": True,
            "user_id": 6,
            "mark_as_read": False,
            "resp_skip": 0,
            "resp_limit": 10,
            "reverse_order": "true",
            "merge_question_type_responses": False,
        },
    )
    assert response.status_code == 200
    thread = response.json()
    assert thread["thread_type"] == "question"
    assert len(thread["children"]) == 2
    assert thread["children"][0]["id"] == comment_id2
    assert thread["children"][1]["id"] == comment_id1

    response = api_client.get_json(
        f"/api/v2/threads/{thread_id}",
        params={
            "with_responses": True,
            "mark_as_read": False,
            "reverse_order": False,
            "merge_question_type_responses": False,
        },
    )
    assert response.status_code == 200
    thread = response.json()
    assert thread["thread_type"] == "question"
    assert thread["non_endorsed_responses"][0]["id"] == comment_id2
    assert thread["endorsed_responses"][0]["id"] == comment_id1
    assert thread["non_endorsed_resp_total"] == 1

    response = api_client.get_json(
        f"/api/v2/threads/{thread_id}",
        params={
            "recursive": True,
            "with_responses": True,
            "mark_as_read": False,
            "reverse_order": "true",
            "merge_question_type_responses": False,
        },
    )
    assert response.status_code == 200
    thread = response.json()
    assert thread["thread_type"] == "question"
    assert thread["non_endorsed_responses"][0]["id"] == comment_id2
    assert thread["endorsed_responses"][0]["id"] == comment_id1
    assert thread["non_endorsed_resp_total"] == 1

    response = api_client.get_json(
        f"/api/v2/threads/{thread_id}",
        params={
            "with_responses": True,
            "user_id": "8",
            "mark_as_read": False,
            "reverse_order": False,
            "merge_question_type_responses": False,
        },
    )
    assert response.status_code == 200
    thread = response.json()
    assert thread["thread_type"] == "question"
    assert thread["non_endorsed_responses"][0]["id"] == comment_id2
    assert thread["endorsed_responses"][0]["id"] == comment_id1
    assert thread["non_endorsed_resp_total"] == 1


def test_read_states_deletion_of_a_thread_on_thread_deletion(
    api_client: APIClient, patched_mongo_backend: MongoBackend
) -> None:
    """Test delete read_states of the thread on deletion of a thread for mongodb."""
    user_id, thread_id = setup_models(backend=patched_mongo_backend)
    comment_id_1, comment_id_2 = create_comments_in_a_thread(
        patched_mongo_backend, thread_id
    )
    thread_from_db = patched_mongo_backend.get_thread(thread_id)
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
    assert patched_mongo_backend.get_thread(thread_id) is None
    assert patched_mongo_backend.get_comment(comment_id_1) is None
    assert patched_mongo_backend.get_comment(comment_id_2) is None
    assert (
        patched_mongo_backend.get_subscription(
            subscriber_id=user_id, source_id=thread_id
        )
        is None
    )
    assert is_thread_id_exists_in_user_read_state(user_id, thread_id) is False


def is_thread_id_exists_in_user_read_state(user_id: str, thread_id: str) -> bool:
    """Return True or False if thread_id exists in read_states of any user."""
    user = Users().find_one({"_id": user_id})
    if user:
        for read_state in user.get("read_states", []):
            if thread_id in read_state.get("last_read_times", {}):
                return True
    return False


def test_filter_by_group_id(api_client: APIClient, patched_get_backend: Any) -> None:
    """
    Filter threads by their group_id. This should return:
    - Threads with the specified group ID.
    - Threads that do not belong to any group (i.e., group_id=None).
    """
    backend = patched_get_backend
    setup_models(backend=backend)

    for i in range(2, 5):
        time.sleep(0.001)
        backend.create_thread(
            {
                "title": f"Thread {i}",
                "body": f"Thread {i}",
                "course_id": "course1",
                "commentable_id": "CommentThread",
                "author_id": "1",
                "author_username": "user1",
                "abuse_flaggers": [],
                "historical_abuse_flaggers": [],
                "context": "course",
                "group_id": i,
            }
        )
    params = {"course_id": "course1", "group_id": "2"}
    response = api_client.get_json("/api/v2/threads", params)
    assert response.status_code == 200
    results = response.json().get("collection", [])

    # The result includes one thread from setup_models with group_id=None
    # and another thread: Thread 2 with group_id=2.
    assert len(results) == 2
    assert results[0]["group_id"] == 2
    assert results[1]["group_id"] is None


def test_filter_by_group_ids(api_client: APIClient, patched_get_backend: Any) -> None:
    """
    Filter threads by their group IDs. This should return:
    - Threads with the specified group IDs.
    - Threads that do not belong to any group (i.e., group_id=None).
    """
    backend = patched_get_backend
    setup_models(backend=backend)
    for i in range(2, 5):
        time.sleep(0.001)
        backend.create_thread(
            {
                "title": f"Thread {i}",
                "body": f"Thread {i}",
                "course_id": "course1",
                "commentable_id": "CommentThread",
                "author_id": "1",
                "author_username": "user1",
                "abuse_flaggers": [],
                "historical_abuse_flaggers": [],
                "context": "course",
                "group_id": i,
            }
        )

    params = {"course_id": "course1", "group_ids": "2,3"}
    response = api_client.get_json("/api/v2/threads", params)
    assert response.status_code == 200
    results = response.json().get("collection", [])

    # The result includes one thread from setup_models with group_id=None
    # and two threads: Thread 2 and Thread 3 with group_id=2 and group_id=3, respectively.
    assert len(results) == 3
    assert results[0]["group_id"] == 3
    assert results[1]["group_id"] == 2
    assert results[2]["group_id"] is None
