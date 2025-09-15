"""Subscriptions API Views."""

from typing import Any

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from forum.api.subscriptions import (
    create_subscription,
    delete_subscription,
    get_thread_subscriptions,
    get_user_subscriptions,
)
from forum.pagination import ForumPagination
from forum.utils import ForumV2RequestError


class SubscriptionAPIView(APIView):
    """
    API View for managing subscriptions.

    This view provides endpoints for subscribing and unsubscribing users to/from sources.
    """

    permission_classes = (AllowAny,)

    def post(self, request: Request, user_id: str) -> Response:
        """
        Subscribe a user to a source.

        Args:
            request (HttpRequest): The HTTP request object.
            user_id (str): The ID of the user to subscribe.

        Returns:
            Response: A Response object with the subscription data.

        Raises:
            HTTP_400_BAD_REQUEST: If the user or content does not exist.
        """
        request_data = request.data
        try:
            serilized_data = create_subscription(user_id, request_data["source_id"])
        except ForumV2RequestError as e:
            return Response(data={"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(data=serilized_data, status=status.HTTP_200_OK)

    def delete(self, request: Request, user_id: str) -> Response:
        """
        Unsubscribe a user from a source.

        Args:
            request (HttpRequest): The HTTP request object.
            user_id (str): The ID of the user to unsubscribe.

        Returns:
            Response: A Response object with the subscription data.

        Raises:
            HTTP_400_BAD_REQUEST: If the user or subscription does not exist.
        """
        try:
            params = request.query_params
            serilized_data = delete_subscription(user_id, params["source_id"])
        except ForumV2RequestError as e:
            return Response(data={"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(data=serilized_data, status=status.HTTP_200_OK)


class UserSubscriptionAPIView(APIView):
    """
    API View for managing user subscriptions.

    This view provides an endpoint for retrieving a user's subscriptions.
    """

    permission_classes = (AllowAny,)

    def get(self, request: Request, user_id: str) -> Response:
        """
        Retrieve a user's subscriptions.

        Args:
            request (HttpRequest): The HTTP request object.
            user_id (str): The ID of the user to retrieve subscriptions for.

        Returns:
            Response: A Response object with the subscription data.

        Raises:
            HTTP_400_BAD_REQUEST: If the user does not exist.
        """
        params: dict[str, Any] = request.GET.dict()
        course_id = params.pop("course_id")
        try:
            serilized_data = get_user_subscriptions(
                user_id,
                course_id,
                **params,
            )
        except ForumV2RequestError as e:
            return Response(data={"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(data=serilized_data, status=status.HTTP_200_OK)


class ThreadSubscriptionAPIView(APIView):
    """
    API View for managing thread subscriptions.

    This view provides an endpoint for retrieving subscriptions to a specific thread.
    """

    permission_classes = (AllowAny,)
    pagination_class = ForumPagination

    def get(self, request: Request, thread_id: str) -> Response:
        """
        Retrieve subscriptions to a specific thread.

        Args:
            request (HttpRequest): The HTTP request object.
            thread_id (str): The ID of the thread to retrieve subscriptions for.

        Returns:
            Response: A paginated Response object with the subscription data.
        """
        page = int(request.GET.get("page", 1))
        per_page = int(request.GET.get("per_page", 20))
        subscriptions_data = get_thread_subscriptions(thread_id, page, per_page)
        return Response(subscriptions_data, status=status.HTTP_200_OK)
