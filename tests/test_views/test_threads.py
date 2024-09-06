"""Test threads api endpoints."""

from typing import Optional

from forum.models import Comment, CommentThread, Users
from test_utils.client import APIClient


def setup_models(
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
    Users().insert(user_id, username=username, email="email1")
    comment_thread_id = CommentThread().insert(
        title="Thread 1",
        body="Thread 1",
        course_id=course_id,
        commentable_id="CommentThread",
        author_id=user_id,
        author_username=username,
        abuse_flaggers=[],
        historical_abuse_flaggers=[],
        thread_type=thread_type or "discussion",
    )
    return user_id, comment_thread_id


def create_comments_in_a_thread(thread_id: str) -> tuple[str, str]:
    """create comments in a thread."""
    user_id = "1"
    username = "user1"
    course_id = "course1"
    comment_id_1 = Comment().insert(
        body="Comment 1",
        course_id=course_id,
        author_id=user_id,
        comment_thread_id=thread_id,
        author_username=username,
    )
    comment_id_2 = Comment().insert(
        body="Comment 2",
        course_id=course_id,
        author_id=user_id,
        comment_thread_id=thread_id,
        author_username=username,
    )
    return comment_id_1, comment_id_2


def test_update_thread(api_client: APIClient) -> None:
    user_id, thread_id = setup_models()
    response = api_client.put_json(
        f"/api/v2/threads/{thread_id}",
        data={
            "body": "new thread body",
            "title": "new thread title",
            "commentable_id": "new_commentable_id",
            "thread_type": "question",
            "user_id": user_id,
        },
    )
    assert response.status_code == 200
    updated_thread = response.json()
    updated_thread_from_db = CommentThread().get(updated_thread["id"])
    assert updated_thread_from_db is not None
    assert updated_thread_from_db["body"] == "new thread body"
    assert updated_thread_from_db["title"] == "new thread title"
    assert updated_thread_from_db["commentable_id"] == "new_commentable_id"
    assert updated_thread_from_db["thread_type"] == "question"


def test_update_thread_without_user_id(api_client: APIClient) -> None:
    _, thread_id = setup_models()
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
    updated_thread_from_db = CommentThread().get(updated_thread["id"])
    assert updated_thread_from_db is not None
    assert updated_thread_from_db["body"] == "new thread body"
    assert updated_thread_from_db["title"] == "new thread title"
    assert updated_thread_from_db["commentable_id"] == "new_commentable_id"
    assert updated_thread_from_db["thread_type"] == "question"


def test_update_close_reason(api_client: APIClient) -> None:
    user_id, thread_id = setup_models()
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
    updated_thread_from_db = CommentThread().get(updated_thread["id"])
    assert updated_thread_from_db is not None
    assert updated_thread_from_db["closed"]
    assert updated_thread_from_db["close_reason_code"] == "test_code"
    assert updated_thread_from_db["closed_by_id"] == user_id


def test_closing_and_reopening_thread_clears_reason_code(api_client: APIClient) -> None:
    user_id, thread_id = setup_models()
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
    updated_thread_from_db = CommentThread().get(updated_thread["id"])
    assert updated_thread_from_db is not None
    assert not updated_thread_from_db["closed"]
    assert updated_thread_from_db["close_reason_code"] is None
    assert updated_thread_from_db["closed_by_id"] is None


def test_update_thread_not_exist(api_client: APIClient) -> None:
    wrong_thread_id = "66cd75eba3a68c001d51927b"
    response = api_client.put_json(
        f"/api/v2/threads/{wrong_thread_id}",
        data={
            "body": "new thread body",
            "title": "new thread title",
        },
    )
    assert response.status_code == 400
    assert response.data["error"] == "thread does not exist"


def test_unicode_data(api_client: APIClient) -> None:
    user_id, thread_id = setup_models()
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
        updated_thread_from_db = CommentThread().get(updated_thread["id"])
        assert updated_thread_from_db is not None
        assert updated_thread_from_db["body"] == text
        assert updated_thread_from_db["title"] == text


def test_delete_thread(api_client: APIClient) -> None:
    _, thread_id = setup_models()
    comment_id_1, comment_id_2 = create_comments_in_a_thread(thread_id)
    thread_from_db = CommentThread().get(thread_id)
    assert thread_from_db is not None
    assert thread_from_db["comment_count"] == 2
    response = api_client.delete_json(f"/api/v2/threads/{thread_id}")
    assert response.status_code == 200
    assert CommentThread().get(thread_id) is None
    assert Comment().get(comment_id_1) is None
    assert Comment().get(comment_id_2) is None


def test_delete_thread_not_exist(api_client: APIClient) -> None:
    wrong_thread_id = "66cd75eba3a68c001d51927b"
    response = api_client.delete_json(f"/api/v2/threads/{wrong_thread_id}")
    assert response.status_code == 400
    assert response.data["error"] == "thread does not exist"


def test_filter_by_course(api_client: APIClient) -> None:
    setup_models()
    params = {"course_id": "course1"}
    response = api_client.get_json("/api/v2/threads", params)
    assert response.status_code == 200
    results = response.json().get("collection", [])

    assert len(results) == 1
    for _, res in enumerate(results):
        assert res["course_id"] == "course1"


def test_filter_exclude_standalone(api_client: APIClient) -> None:
    setup_models()
    CommentThread().insert(
        title="Thread 2",
        body="Thread 2",
        course_id="course1",
        commentable_id="CommentThread",
        author_id="1",
        author_username="user1",
        abuse_flaggers=[],
        historical_abuse_flaggers=[],
        context="standalone",
    )
    params = {"course_id": "course1"}
    response = api_client.get_json("/api/v2/threads", params)
    assert response.status_code == 200
    results = response.json().get("collection", [])

    assert len(results) == 1
    for _, res in enumerate(results):
        assert res["course_id"] == "course1"
        assert res["context"] == "course"


def test_no_matching_course_id(api_client: APIClient) -> None:
    setup_models()
    wrong_course_id = "abc"
    params = {"course_id": wrong_course_id}
    response = api_client.get_json("/api/v2/threads", params)
    assert response.status_code == 200
    results = response.json().get("collection", [])
    assert len(results) == 0


def test_filter_flagged_posts(api_client: APIClient) -> None:
    user_id, thread_id = setup_models()
    tests_flags = [(True, "1"), (False, "0")]
    for flagged, abuse_flaggers in tests_flags:
        action = "flag" if flagged else "unflag"
        response = api_client.put_json(
            path=f"/api/v2/threads/{thread_id}/abuse_{action}",
            data={"user_id": str(user_id)},
        )
        params = {"course_id": "course1", "flagged": flagged}
        response = api_client.get_json("/api/v2/threads", params)
        assert response.status_code == 200
        if action == "unflag":
            assert response.json()["collection"] == []
        else:
            result = response.json()["collection"][0]
            assert result["abuse_flaggers"] == [abuse_flaggers]


def test_filter_by_author(api_client: APIClient) -> None:
    user_id1, _ = setup_models()
    user_id2, _ = setup_models("2", "user2", "course2")

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


def test_filter_by_post_type(api_client: APIClient) -> None:
    setup_models()
    setup_models("2", "user2", "course1")
    CommentThread().insert(
        title="Thread 3",
        body="Thread 3",
        course_id="course1",
        commentable_id="CommentThread",
        author_id="3",
        author_username="user3",
        abuse_flaggers=[],
        historical_abuse_flaggers=[],
        thread_type="question",
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


def test_filter_unanswered_questions(api_client: APIClient) -> None:
    _, thread1 = setup_models(thread_type="question")
    _, thread2 = setup_models("2", "user2", thread_type="question")
    CommentThread().insert(
        title="Thread 3",
        body="Thread 3",
        course_id="course1",
        commentable_id="CommentThread",
        author_id="1",
        author_username="user1",
        abuse_flaggers=[],
        historical_abuse_flaggers=[],
        thread_type="question",
    )

    params = {"course_id": "course1", "unanswered": True}
    response = api_client.get_json("/api/v2/threads", params)
    assert response.status_code == 200
    results = response.json()["collection"]
    assert len(results) == 3

    api_client.put_json(
        f"/api/v2/threads/{thread1}",
        data={"endorsed": True},
    )
    api_client.put_json(
        f"/api/v2/threads/{thread2}",
        data={"endorsed": True},
    )

    params = {"course_id": "course1", "unanswered": True}
    response = api_client.get_json("/api/v2/threads", params)
    assert response.status_code == 200
    results = response.json()["collection"]
    assert len(results) == 1
    for thread in results:
        assert thread["title"] == "Thread 3"
        assert thread["body"] == "Thread 3"


def test_get_thread(api_client: APIClient) -> None:
    _, thread_id = setup_models()
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


def test_computes_endorsed_correctly(api_client: APIClient) -> None:
    _, thread_id = setup_models()
    comment_id = Comment().insert(
        body="Comment 1",
        course_id="course1",
        author_id="1",
        comment_thread_id=thread_id,
        author_username="user1",
    )
    Comment().update(comment_id=comment_id, endorsed=True)
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


def test_no_children_for_informational_request(api_client: APIClient) -> None:
    _, thread_id = setup_models()
    Comment().insert(
        body="Comment 1",
        course_id="course1",
        author_id="1",
        comment_thread_id=thread_id,
        author_username="user1",
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


def test_mark_as_read(api_client: APIClient) -> None:
    _, thread_id = setup_models()
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


def test_thread_with_comments(api_client: APIClient) -> None:
    user_id, thread_id = setup_models()
    response = api_client.post_json(
        f"/api/v2/threads/{thread_id}/comments",
        data={
            "body": "<p>Parent Comment 1</p>",
            "course_id": "course1",
            "user_id": user_id,
        },
    )
    assert response.status_code == 200

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
    assert thread["children"] is not None
