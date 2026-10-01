"""
An AI moderation backend for tests.

Forum ships the moderation interface and no provider, so anything that
exercises moderation has to bring a backend of its own. This is one written the
way an Open edX operator would write one: a subclass of ``HTTPModerationBackend``
that describes a single provider's request and response and is selected by
dotted path. Living outside the ``forum`` package is the point -- it proves the
extension point works from out of tree.

Its provider is imaginary: a bearer-token JSON API answering
``{"verdict": {"text": "<classifier JSON>"}}``.
"""

from typing import Any, Dict, Optional
from unittest.mock import Mock

from django.conf import settings

from forum.ai_moderation.backends import HTTPModerationBackend

STUB_PROVIDER_BACKEND = "test_utils.moderation.StubProviderBackend"


class StubProviderBackend(HTTPModerationBackend):
    """Classify content with the imaginary provider described above."""

    @property
    def api_key(self) -> Optional[str]:
        """Credential for the provider."""
        return getattr(settings, "AI_MODERATION_API_KEY", None)

    def classify(self, content: str) -> Optional[Dict[str, Any]]:
        """Classify content, returning the common moderation result."""
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response_data = self.post(
            {"prompt": self.system_message, "input": content}, headers
        )
        if response_data is None:
            return None

        return self.parse_moderation_payload(
            response_data.get("verdict", {}).get("text"), response_data
        )


def stub_provider_response(payload: str) -> Mock:
    """
    Build a mocked provider response, in the shape StubProviderBackend reads.

    Args:
        payload: The JSON document the classifier answered with.
    """
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"verdict": {"text": payload}}
    return response
