"""Forum Views."""

from django.http import HttpRequest
from rest_framework.response import Response

from forum.utils import handle_proxy_requests
from forum.views.base import ForumAPIView


class ForumProxyAPIView(ForumAPIView):
    """
    A Proxy API View to Redirect All API requests to forum/cs_comments_service urls.
    """

    def post(self, request: HttpRequest, suffix: str) -> Response:
        """
        Catches post requests and sends them to forum/cs_comments_service post URLs.
        """
        response = handle_proxy_requests(request, suffix, "post")
        return Response(data=response.json(), status=response.status_code)

    def get(self, request: HttpRequest, suffix: str) -> Response:
        """
        Catches get requests and sends them to forum/cs_comments_service get URLs.
        """
        response = handle_proxy_requests(request, suffix, "get")
        if response.content:
            return Response(data=response.json(), status=response.status_code)
        else:
            return Response(data={}, status=response.status_code)

    def delete(self, request: HttpRequest, suffix: str) -> Response:
        """
        Catches delete requests and sends them to forum/cs_comments_service delete URLs.
        """
        response = handle_proxy_requests(request, suffix, "delete")
        return Response(data=response.json(), status=response.status_code)

    def put(self, request: HttpRequest, suffix: str) -> Response:
        """
        Catches put requests and sends them to forum/cs_comments_service put URLs.
        """
        response = handle_proxy_requests(request, suffix, "put")
        return Response(data=response.json(), status=response.status_code)
