"""Forum Pin/Unpin thread API Views."""

import logging
from typing import Any

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from forum.api import pin_thread, unpin_thread
from forum.utils import ForumV2RequestError
from forum.views.base import ForumAPIView

log = logging.getLogger(__name__)


class PinThreadAPIView(ForumAPIView):
    """
    API View to Pin thread.
    Handles PUT requests to pin a thread.
    """

    def put(self, request: Request, thread_id: str) -> Response:
        """
        Pins a thread.
        Parameters:
            request (Request): The incoming request.
            thread_id (str): The ID of the thread to pin.
        Body:
            user_id: requesting user's id
        Response:
            A response with the updated thread data.
        """
        try:
            thread_data: dict[str, Any] = pin_thread(
                request.data.get("user_id", ""), thread_id
            )
        except ForumV2RequestError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(thread_data, status=status.HTTP_200_OK)


class UnpinThreadAPIView(ForumAPIView):
    """
    API View to Unpin a thread.
    Handles PUT requests to unpin a thread.
    """

    def put(self, request: Request, thread_id: str) -> Response:
        """
        Unpins a thread.
        Parameters:
            request (Request): The incoming request.
            thread_id (str): The ID of the thread to unpin.
        Body:
            user_id: requesting user's id
        Response:
            A response with the updated thread data.
        """
        try:
            thread_data: dict[str, Any] = unpin_thread(
                request.data.get("user_id", ""), thread_id
            )
        except ForumV2RequestError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(thread_data, status=status.HTTP_200_OK)
