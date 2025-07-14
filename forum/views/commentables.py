"""Forum Comments API Views."""

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from forum.api.commentables import get_commentables_stats


class CommentablesCountAPIView(APIView):
    """
    API View to handle GET request for commentables count.
    """

    permission_classes = (AllowAny,)

    def get(self, request: Request, course_id: str) -> Response:  # pylint: disable=W0613
        """
        Retrieves a the threads count based on thread_type.

        Parameters:
            request (Request): The incoming request.
            course_id: The ID of the course.
        Body:
            Empty.
        Response:
            The threads count for the given course_id based on thread_type.
        """
        commentable_counts = get_commentables_stats(course_id)
        return Response(
            commentable_counts,
            status=status.HTTP_200_OK,
        )
