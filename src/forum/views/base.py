"""Base view for the forum HTTP API."""

from rest_framework.views import APIView

from forum.permissions import IsForumServiceUser


class ForumAPIView(APIView):
    """
    Base class for every view in the forum HTTP API.

    Carrying the permission here rather than repeating it on each view means a
    newly added view is protected by default. Getting that wrong is how this
    API ended up unauthenticated in the first place: most views declared
    ``AllowAny`` outright, and the few that declared nothing inherited DRF's
    ``AllowAny`` default, so neither spelling stood out as the unsafe one.

    Views must not override ``permission_classes`` to widen access.
    ``tests/test_permissions.py`` walks the URLconf and enforces that.
    """

    permission_classes = (IsForumServiceUser,)
