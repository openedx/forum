"""
Vote Views
"""

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from forum.api.votes import (
    delete_comment_vote,
    delete_thread_vote,
    update_comment_votes,
    update_thread_votes,
)
from forum.utils import ForumV2RequestError


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

    def put(self, request: Request, thread_id: str) -> Response:
        """
        Handles the upvote or downvote on a thread.

        Args:
            request (Request): The incoming request object.
            thread_id (str): The ID of the thread to vote on.

        Returns:
            Response: The HTTP response with the result of the vote operation.
        """
        try:
            thread_response = update_thread_votes(
                thread_id, request.data["user_id"], request.data["value"]
            )
        except (ForumV2RequestError, KeyError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(thread_response, status=status.HTTP_200_OK)

    def delete(self, request: Request, thread_id: str) -> Response:
        """
        Handles removing a vote from a thread.

        Args:
            request (Request): The incoming request object.
            thread_id (str): The ID of the thread to remove the vote from.

        Returns:
            Response: The HTTP response with the result of the remove vote operation.
        """
        try:
            user_id = request.query_params.get("user_id", "")
            thread_response = delete_thread_vote(thread_id, user_id)
        except (ForumV2RequestError, KeyError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(thread_response, status=status.HTTP_200_OK)


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

    def put(self, request: Request, comment_id: str) -> Response:
        """
        Handles the upvote or downvote on a comment.

        Args:
            request (Request): The incoming request object.
            comment_id (str): The ID of the comment to vote on.

        Returns:
            Response: The HTTP response with the result of the vote operation.
        """
        try:
            comment_response = update_comment_votes(
                comment_id, request.data["user_id"], request.data["value"]
            )
        except (ForumV2RequestError, KeyError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(comment_response, status=status.HTTP_200_OK)

    def delete(self, request: Request, comment_id: str) -> Response:
        """
        Handles removing a vote from a comment.

        Args:
            request (Request): The incoming request object.
            comment_id (str): The ID of the comment to remove the vote from.

        Returns:
            Response: The HTTP response with the result of the remove vote operation.
        """
        try:
            user_id = request.query_params.get("user_id", "")
            comment_response = delete_comment_vote(comment_id, user_id)
        except (ForumV2RequestError, KeyError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(comment_response, status=status.HTTP_200_OK)
