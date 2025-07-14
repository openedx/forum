"""Subscriptions API Views."""

import logging
from typing import Any

from rest_framework import status
from rest_framework.exceptions import ParseError
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from forum.api import get_user
from forum.api.users import (
    create_user,
    get_user_active_threads,
    get_user_course_stats,
    mark_thread_as_read,
    retire_user,
    update_user,
    update_username,
    update_users_in_course,
)
from forum.utils import ForumV2RequestError, get_group_ids_from_params, str_to_bool

log = logging.getLogger(__name__)


class UserAPIView(APIView):
    """Users API View."""

    permission_classes = (AllowAny,)

    def get(self, request: Request, user_id: str) -> Response:
        """Get user data."""
        params = request.GET.dict()
        course_id = params.get("course_id", "")
        group_ids = get_group_ids_from_params(params)
        complete = str_to_bool(params.get("complete", False))

        try:
            user_data: dict[str, Any] = get_user(
                user_id, group_ids, course_id, complete
            )
        except ForumV2RequestError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)

        return Response(user_data, status=status.HTTP_200_OK)

    def put(self, request: Request, user_id: str) -> Response:
        """Update user data."""
        try:
            params = request.data
            username = params.get("username")
            default_sort_key = params.get("default_sort_key")
            course_id = params.get("course_id")
            group_ids = params.get("group_ids")
            complete = params.get("complete")
            updated_user = update_user(
                user_id,
                username,
                default_sort_key,
                course_id,
                group_ids,
                complete,
            )
        except ForumV2RequestError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(updated_user, status=status.HTTP_200_OK)


class UserCreateAPIView(APIView):
    """Create users api."""

    permission_classes = (AllowAny,)

    def post(self, request: Request) -> Response:
        """Create user."""
        params = request.data
        for key in params:
            if key not in ["id", "username"]:
                return Response(
                    {"error": f"Invalid parameter: {key}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        try:
            data: dict[str, Any] = {
                "user_id": params.get("id"),
                "username": params.get("username"),
                "default_sort_key": params.get("default_sort_key", "date"),
                "course_id": params.get("course_id"),
                "group_ids": params.get("group_ids"),
                "complete": params.get("complete"),
            }
            user_data = create_user(**data)
        except ForumV2RequestError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(user_data, status=status.HTTP_200_OK)


class UserEditAPIView(APIView):
    """Edit user api."""

    def post(self, request: Request, user_id: str) -> Response:
        """Edit user."""
        error_500_response = Response(
            {"message": "Missing new_username param."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        try:
            params = request.data
        except ParseError:
            return error_500_response
        new_username = params.get("new_username")
        if not new_username:
            return error_500_response
        try:
            update_username(user_id, new_username)
        except ForumV2RequestError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_200_OK)


class UserRetireAPIView(APIView):
    """Retire user api."""

    permission_classes = (AllowAny,)

    def post(self, request: Request, user_id: str) -> Response:
        """Retire user."""
        error_500_response = Response(
            {"message": "Missing retired_username param."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        try:
            params = request.data
        except ParseError:
            return error_500_response
        retired_username = params.get("retired_username")
        if not retired_username:
            return error_500_response
        try:
            retire_user(user_id, retired_username)
        except ForumV2RequestError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_200_OK)


class UserReadAPIView(APIView):
    """User read api."""

    permission_classes = (AllowAny,)

    def post(self, request: Request, user_id: str) -> Response:
        """User read."""
        params = request.data
        data = {
            "source_id": params.get("source_id", ""),
            "complete": params.get("complete"),
            "course_id": params.get("course_id"),
            "group_ids": params.get("group_ids"),
        }
        try:
            serialized_data = mark_thread_as_read(user_id, **data)
        except ForumV2RequestError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serialized_data, status=status.HTTP_200_OK)


class UserActiveThreadsAPIView(APIView):
    """User active threads api."""

    permission_classes = (AllowAny,)

    def get(self, request: Request, user_id: str) -> Response:
        """User active threads."""
        params: dict[str, Any] = request.GET.dict()
        course_id = params.pop("course_id", None)

        if page := params.get("page"):
            params["page"] = int(page)
        if per_page := params.get("per_page"):
            params["per_page"] = int(per_page)
        if flagged := params.get("flagged"):
            params["flagged"] = str_to_bool(flagged)
        if unread := params.get("unread"):
            params["unread"] = str_to_bool(unread)
        if unanswered := params.get("unanswered"):
            params["unanswered"] = str_to_bool(unanswered)
        if unresponded := params.get("unresponded"):
            params["unresponded"] = str_to_bool(unresponded)
        if count_flagged := params.get("count_flagged"):
            params["count_flagged"] = str_to_bool(count_flagged)
        if group_id := params.get("group_id"):
            params["group_id"] = int(group_id)
        try:
            serialized_data = get_user_active_threads(user_id, course_id, **params)
        except ForumV2RequestError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serialized_data)


class UserCourseStatsAPIView(APIView):
    """User Course stats API."""

    permission_classes = (AllowAny,)

    def get(self, request: Request, course_id: str) -> Response:  # pylint: disable=W0613
        """Get user course stats."""
        params: dict[str, Any] = request.GET.dict()
        if page := params.get("page"):
            params["page"] = int(page)
        if per_page := params.get("per_page"):
            params["per_page"] = int(per_page)
        if with_timestamps := params.get("with_timestamps"):
            params["with_timestamps"] = str_to_bool(with_timestamps)

        response = get_user_course_stats(
            course_id,
            **params,
        )
        return Response(response, status=status.HTTP_200_OK)

    def post(self, request: Request, course_id: str) -> Response:
        """Update user stats for a course."""
        updated_users = update_users_in_course(course_id)
        return Response(updated_users, status=status.HTTP_200_OK)
