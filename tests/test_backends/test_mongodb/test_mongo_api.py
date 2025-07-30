"""
Test suit for MongoDB backend API functionalities.
"""

import unittest

from forum.backends.mongodb import CommentThread
from forum.backends.mongodb.api import MongoBackend
from forum.serializers.thread import ThreadSerializer


class TestMongoAPI(unittest.TestCase):
    """
    Test suite for MongoDB backend API functionalities.
    """

    def setUp(self) -> None:
        self.thread_1 = CommentThread().insert(
            "Thread 1",
            "Body 1",
            "course_id",
            "id_1",
            "1",
            "user1",
        )
        self.thread_2 = CommentThread().insert(
            "Thread 2",
            "Body 2",
            "course_id",
            "id_2",
            "1",
            "user1",
        )
        self.thread_3 = CommentThread().insert(
            "Thread 3",
            "Body 3",
            "course_id",
            "id_2",
            "user1",
        )

    def test_filter_by_commentable_ids(self) -> None:
        """
        Test filtering threads by commentable_ids.
        """
        threads = MongoBackend.get_threads(
            user_id="",
            params={"commentable_ids": ["id_2"], "course_id": "course_id"},
            serializer=ThreadSerializer,
            thread_ids=[self.thread_1, self.thread_2, self.thread_3],
        )
        # make sure the threads are filtered correctly by commentable_ids aka Topics ids
        assert threads["thread_count"] == 2
        for thread in threads["collection"]:
            assert thread["commentable_id"] == "id_2"
