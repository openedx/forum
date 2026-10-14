"""Permissions for the forum HTTP API."""

from rest_framework.permissions import IsAdminUser


class IsForumServiceUser(IsAdminUser):
    """
    Allow only a trusted backend service to call the forum HTTP API.

    These endpoints take the acting user from a ``user_id`` parameter rather
    than from the session: the caller declares who it is acting for. That is a
    service-to-service contract, so what gets authenticated here is the caller,
    not the end user, and it has to be a privileged account.

    Authentication itself comes from the DRF defaults. Inside edx-platform
    those are JWT and session auth, so a service presenting a JWT for a staff
    service account satisfies this.

    An end user's own credentials deliberately do not. Honouring a learner's
    session while still reading the acting user out of ``user_id`` would let
    any authenticated learner act as anybody else, which would turn a pre-auth
    flaw into a post-auth one rather than fixing it.

    The staff check itself is DRF's ``IsAdminUser``; this subclass exists to
    carry the reasoning above and a message that tells a caller what it got
    wrong.
    """

    message = (
        "The forum HTTP API may only be called by a trusted backend service "
        "authenticating as a staff account."
    )
