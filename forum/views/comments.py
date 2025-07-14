"""Forum Comments API Views."""

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.views import APIView

from forum.api import (
    create_parent_comment,
    create_child_comment,
    delete_comment,
    get_parent_comment,
    update_comment,
)
from forum.utils import ForumV2RequestError, str_to_bool


class CommentsAPIView(APIView):
    """
    API View to handle GET, POST, PUT, and DELETE requests for comments.
    """

    permission_classes = (AllowAny,)

    def get(self, request: Request, comment_id: str) -> Response:  # pylint: disable=W0613
        """
        Retrieves a parent comment.
        For chile comments, below API is called that return all child comments in children field
        url: http://localhost:8000/forum/api/v2/threads/66ab94950dead7001deb947a

        Parameters:
            request (Request): The incoming request.
            comment_id: The ID of the comment.
        Body:
            Empty.
        Response:
            The details of the comment for the given comment_id.
        """
        try:
            data = get_parent_comment(comment_id)
        except ForumV2RequestError:
            return Response(
                {"error": f"Comment does not exist with Id: {comment_id}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(data, status=status.HTTP_200_OK)

    def post(self, request: Request, comment_id: str) -> Response:
        """
        Creates a new child comment.
        For parent comment below API is called.
        url: http://localhost:8000/forum/api/v2/threads/66ab94950dead7001deb947a/comments

        Parameters:
            request (Request): The incoming request.
            comment_id: The ID of the parent comment for creating it's child comment.
        Body:
            body: The content of the comment.
            course_id: The Id of the respective course.
            user_id: The requesting user id.
            anonymous: anonymous flag(True or False).
            anonymous_to_peers: anonymous to peers flag(True or False).
        Response:
            The details of the comment that is created.
        """
        try:
            request_data = request.data
            comment = create_child_comment(
                comment_id,
                request_data["body"],
                request_data["user_id"],
                request_data["course_id"],
                str_to_bool(request_data.get("anonymous", False)),
                str_to_bool(request_data.get("anonymous_to_peers", False)),
            )
        except ForumV2RequestError:
            return Response(
                {"error": f"Comment does not exist with Id: {comment_id}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValidationError as e:
            return Response(
                {"error": e.detail},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(comment, status=status.HTTP_200_OK)

    def put(self, request: Request, comment_id: str) -> Response:
        """
        Updates an existing child/parent comment.

        Parameters:
            request (Request): The incoming request.
            comment_id: The ID of the comment to be edited.
        Body:
            fields to be updated.
        Response:
            The details of the comment that is updated.
        """
        try:
            request_data = request.data
            if anonymous := request_data.get("anonymous"):
                anonymous = str_to_bool(anonymous)
            if anonymous_to_peers := request_data.get("anonymous_to_peers"):
                anonymous_to_peers = str_to_bool(anonymous_to_peers)
            if endorsed := request_data.get("endorsed"):
                endorsed = str_to_bool(endorsed)
            if closed := request_data.get("closed"):
                closed = str_to_bool(closed)
            comment = update_comment(
                comment_id,
                request_data.get("body"),
                request_data.get("user_id"),
                anonymous,
                anonymous_to_peers,
                endorsed,
                closed,
                request_data.get("editing_user_id"),
                request_data.get("edit_reason_code"),
                request_data.get("endorsement_user_id"),
            )
        except ForumV2RequestError:
            return Response(
                {"error": f"Comment does not exist with Id: {comment_id}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValidationError as e:
            return Response(
                {"error": e.detail},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(comment, status=status.HTTP_200_OK)

    def delete(self, request: Request, comment_id: str) -> Response:  # pylint: disable=W0613
        """
        Deletes a comment.

        Parameters:
            request (Request): The incoming request.
            comment_id: The ID of the comment to be deleted.
        Body:
            Empty.
        Response:
            The details of the comment that is deleted.
        """
        try:
            deleted_comment = delete_comment(comment_id)
        except ForumV2RequestError:
            return Response(
                {"error": f"Comment does not exist with Id: {comment_id}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(deleted_comment, status=status.HTTP_200_OK)


class CreateThreadCommentAPIView(APIView):
    """
    API View to handle POST request for parent comments.
    """

    permission_classes = (AllowAny,)

    def post(self, request: Request, thread_id: str) -> Response:
        """
        Creates a new parent comment.

        Parameters:
            request (Request): The incoming request.
            thread_id: The ID of the thread for creating a comment on it.
        Body:
            body: The content of the comment.
            course_id: The Id of the respective course.
            user_id: The requesting user id.
            anonymous: anonymous flag(True or False).
            anonymous_to_peers: anonymous to peers flag(True or False).
        Response:
            The details of the comment that is created.
        """
        try:
            request_data = request.data
            comment = create_parent_comment(
                thread_id,
                request_data["body"],
                request_data["user_id"],
                request_data["course_id"],
                str_to_bool(request_data.get("anonymous", False)),
                str_to_bool(request_data.get("anonymous_to_peers", False)),
            )
        except ForumV2RequestError:
            return Response(
                {"error": f"Thread does not exist with Id: {thread_id}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValueError as e:
            return Response(
                {"error": e},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValidationError as e:
            return Response(
                {"error": e.detail},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(comment, status=status.HTTP_200_OK)
