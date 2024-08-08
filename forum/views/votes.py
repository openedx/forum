"""
Vote Views
"""

from bson import ObjectId
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from forum.models import Comment, CommentThread, Users
from forum.mongo_utils import downvote_content, remove_vote, upvote_content
from forum.serializers.votes import UserCommentSerializer, UserThreadSerializer, VoteSerializer


class ThreadVoteView(APIView):
    """
    API view to handle voting on threads.

    Endpoint:
    PUT /forum/api/v2/threads/{thread_id}/votes/
    DELETE /forum/api/v2/threads/{thread_id}/votes/

    Example:
    PUT : /forum/api/v2/threads/66af33634a1e1f001b7ed57f/votes/
    Body::

        {
            "user_id": "4",
            "value": "up"
        }

    DELETE : /forum/api/v2/threads/66af33634a1e1f001b7ed57f/votes/
    Params::

        {
            "user_id": "4"
        }
    """

    def _get_thread_and_user(self, thread_id, user_id):
        """
        Fetches the thread and user based on provided IDs.

        Args:
            thread_id (str): The ID of the thread.
            user_id (str): The ID of the user.

        Returns:
            tuple: The thread and user objects.

        Raises:
            ValueError: If the thread or user is not found.
        """
        thread = CommentThread().get(_id=ObjectId(thread_id))
        if not thread:
            raise ValueError("Thread not found")

        user = Users().get(_id=user_id)
        if not user:
            raise ValueError("User not found")

        return thread, user

    def _prepare_response(self, thread, user):
        """
        Prepares the serialized response data after voting.

        Args:
            thread (dict): The thread data.
            user (dict): The user data.

        Returns:
            dict: The serialized response data.

        Raises:
            ValueError: If serialization fails.
        """
        context = {
            **thread,
            "user_id": user["_id"],
            "username": user["username"],
            "type": "thread",
        }
        serializer = UserThreadSerializer(data=context)
        if not serializer.is_valid():
            raise ValueError(serializer.errors)
        return serializer.data

    def put(self, request, thread_id):
        """
        Handles the upvote or downvote on a thread.

        Args:
            request (Request): The incoming request object.
            thread_id (str): The ID of the thread to vote on.

        Returns:
            Response: The HTTP response with the result of the vote operation.
        """
        try:
            vote_serializer = VoteSerializer(data=request.data)
            if not vote_serializer.is_valid():
                return Response(
                    vote_serializer.errors, status=status.HTTP_400_BAD_REQUEST
                )

            thread, user = self._get_thread_and_user(
                thread_id, request.data.get("user_id")
            )

            if vote_serializer.data["value"] == "up":
                is_updated = upvote_content(thread, user)
            else:
                is_updated = downvote_content(thread, user)

            if is_updated:
                thread = CommentThread().get(_id=ObjectId(thread_id))

            return Response(self._prepare_response(thread, user))

        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:  # pylint: disable=broad-exception-caught
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def delete(self, request, thread_id):
        """
        Handles removing a vote from a thread.

        Args:
            request (Request): The incoming request object.
            thread_id (str): The ID of the thread to remove the vote from.

        Returns:
            Response: The HTTP response with the result of the remove vote operation.
        """
        try:
            thread, user = self._get_thread_and_user(
                thread_id, request.query_params.get("user_id")
            )

            if remove_vote(thread, user):
                thread = CommentThread().get(_id=ObjectId(thread_id))

            return Response(self._prepare_response(thread, user))

        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:  # pylint: disable=broad-exception-caught
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CommentVoteView(APIView):
    """
    API view to handle voting on comments.

    Endpoint:
    PUT /forum/api/v2/comments/{comment_id}/votes/
    DELETE /forum/api/v2/comments/{comment_id}/votes/

    Example:
    PUT : /forum/api/v2/comments/66af33634a1e1f001b7ed57f/votes/
    Body::

        {
            "user_id": "4",
            "value": "up"
        }

    DELETE : /forum/api/v2/comments/66af33634a1e1f001b7ed57f/votes/
    Params::

        {
            "user_id": "4"
        }
    """

    def _get_comment_and_user(self, comment_id, user_id):
        """
        Fetches the comment and user based on provided IDs.

        Args:
            comment_id (str): The ID of the comment.
            user_id (str): The ID of the user.

        Returns:
            tuple: The comment and user objects.

        Raises:
            ValueError: If the comment or user is not found.
        """
        comment = Comment().get(_id=ObjectId(comment_id))
        if not comment:
            raise ValueError("Comment not found")

        user = Users().get(_id=user_id)
        if not user:
            raise ValueError("User not found")

        return comment, user

    def _prepare_response(self, comment, user):
        """
        Prepares the serialized response data after voting.

        Args:
            comment (dict): The comment data.
            user (dict): The user data.

        Returns:
            dict: The serialized response data.

        Raises:
            ValueError: If serialization fails.
        """
        context = {
            **comment,
            "user_id": user["_id"],
            "username": user["username"],
            "type": "comment",
            "thread_id": str(comment.get("comment_thread_id", None)),
        }
        serializer = UserCommentSerializer(data=context)
        if not serializer.is_valid():
            raise ValueError(serializer.errors)
        return serializer.data

    def put(self, request, comment_id):
        """
        Handles the upvote or downvote on a comment.

        Args:
            request (Request): The incoming request object.
            comment_id (str): The ID of the comment to vote on.

        Returns:
            Response: The HTTP response with the result of the vote operation.
        """
        try:
            vote_serializer = VoteSerializer(data=request.data)
            if not vote_serializer.is_valid():
                return Response(
                    vote_serializer.errors, status=status.HTTP_400_BAD_REQUEST
                )

            comment, user = self._get_comment_and_user(
                comment_id, request.data.get("user_id")
            )

            if vote_serializer.data["value"] == "up":
                is_updated = upvote_content(comment, user)
            else:
                is_updated = downvote_content(comment, user)

            if is_updated:
                comment = Comment().get(_id=ObjectId(comment_id))

            return Response(self._prepare_response(comment, user))

        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:  # pylint: disable=broad-exception-caught
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def delete(self, request, comment_id):
        """
        Handles removing a vote from a comment.

        Args:
            request (Request): The incoming request object.
            comment_id (str): The ID of the comment to remove the vote from.

        Returns:
            Response: The HTTP response with the result of the remove vote operation.
        """
        try:
            comment, user = self._get_comment_and_user(
                comment_id, request.query_params.get("user_id")
            )

            if remove_vote(comment, user):
                comment = Comment().get(_id=ObjectId(comment_id))

            return Response(self._prepare_response(comment, user))

        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:  # pylint: disable=broad-exception-caught
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )