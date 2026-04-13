"""Forum Comments API Views."""

from edx_django_utils.monitoring import set_custom_attribute  # type: ignore[import-untyped]
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.views import APIView

from forum.api import (
    create_child_comment,
    create_parent_comment,
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

    def get(self, request: Request, comment_id: str) -> Response:
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
        set_custom_attribute("forum.operation", "get_comment")
        set_custom_attribute("forum.comment_id", comment_id)

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
        set_custom_attribute("forum.operation", "create_child_comment")
        set_custom_attribute("forum.parent_comment_id", comment_id)

        request_data = request.data
        if "course_id" in request_data:
            set_custom_attribute("forum.course_id", request_data["course_id"])
        if "user_id" in request_data:
            set_custom_attribute("forum.author_id", request_data["user_id"])

        try:
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
        set_custom_attribute("forum.operation", "update_comment")
        set_custom_attribute("forum.comment_id", comment_id)

        # Track what fields are being updated
        request_data = request.data
        if request_data:
            update_fields = [
                k for k in request_data.keys() if request_data.get(k) is not None
            ]
            set_custom_attribute("forum.update_fields", ",".join(update_fields))
            if "course_id" in request_data:
                set_custom_attribute("forum.course_id", request_data["course_id"])

        try:
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
                request_data.get("course_id"),
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

    def delete(self, request: Request, comment_id: str) -> Response:
        """
        Deletes a comment.

        Parameters:
            request (Request): The incoming request.
            comment_id: The ID of the comment to be deleted.
        Body:
            deleted_by: Optional ID of the user performing the delete (defaults to authenticated user).
        Response:
            The details of the comment that is deleted.
        """
        set_custom_attribute("forum.operation", "delete_comment")
        set_custom_attribute("forum.comment_id", comment_id)

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
        set_custom_attribute("forum.operation", "create_parent_comment")
        set_custom_attribute("forum.thread_id", thread_id)

        request_data = request.data
        if "course_id" in request_data:
            set_custom_attribute("forum.course_id", request_data["course_id"])
        if "user_id" in request_data:
            set_custom_attribute("forum.author_id", request_data["user_id"])

        try:
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
