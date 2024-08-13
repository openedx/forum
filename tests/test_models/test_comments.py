#!/usr/bin/env python
"""
Tests for the `Comment` model.
"""
from forum.models import Comment


def test_insert(comment_model: Comment) -> None:
    """Test insert a comment into MongoDB."""
    comment_id = comment_model.insert(
        body="<p>This is a test comment</p>",
        course_id="course1",
        comment_thread_id="66af33634a1e1f001b7ed57f",
        author_id="author1",
        author_username="author_user",
    )
    assert comment_id is not None
    comment_data = comment_model.get(_id=comment_id)
    assert comment_data is not None
    assert comment_data["body"] == "<p>This is a test comment</p>"


def test_delete(comment_model: Comment) -> None:
    """Test delete a comment from MongoDB."""
    comment_id = comment_model.insert(
        body="<p>This is a test comment</p>",
        course_id="course1",
        comment_thread_id="66af33634a1e1f001b7ed57f",
        author_id="author1",
        author_username="author_user",
    )
    result = comment_model.delete(comment_id)
    assert result == 1
    comment_data = comment_model.get(_id=comment_id)
    assert comment_data is None


def test_list(comment_model: Comment) -> None:
    """Test list all comments from MongoDB."""
    course_id = "course-xyz"
    thread_id = "66af33634a1e1f001b7ed57f"
    author_id = "4"
    author_username = "edly"

    comment_model.insert(
        "<p>Comment 1</p>", course_id, thread_id, author_id, author_username
    )
    comment_model.insert(
        "<p>Comment 2</p>", course_id, thread_id, author_id, author_username
    )
    comment_model.insert(
        "<p>Comment 3</p>", course_id, thread_id, author_id, author_username
    )

    comments_list = comment_model.list()
    assert len(list(comments_list)) == 3
    assert all(comment["body"].startswith("<p>Comment") for comment in comments_list)


def test_update(comment_model: Comment) -> None:
    """Test update a comment in MongoDB."""
    comment_id = comment_model.insert(
        body="<p>This is a test comment</p>",
        course_id="course1",
        comment_thread_id="66af33634a1e1f001b7ed57f",
        author_id="author1",
        author_username="author_user",
    )

    result = comment_model.update(
        comment_id=comment_id,
        body="<p>Updated comment</p>",
    )
    assert result == 1
    comment_data = comment_model.get(_id=comment_id) or {}
    assert comment_data.get("body", "") == "<p>Updated comment</p>"