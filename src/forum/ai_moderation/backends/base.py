"""
Provider-agnostic interface for AI moderation backends.

A moderation backend is the only part of AI moderation that knows how to talk to
a particular AI provider. It takes a piece of forum content and returns the
common moderation result described by :meth:`BaseModerationBackend.classify`;
everything downstream of that -- caching, flagging, deletion, audit logging --
is provider independent and lives in :mod:`forum.ai_moderation.service`.
"""

import json
import logging
from typing import Any, Dict, Optional, Tuple

import requests
from django.conf import settings

from forum.ai_moderation.defaults import (
    DEFAULT_CONNECTION_TIMEOUT,
    DEFAULT_READ_TIMEOUT,
    DEFAULT_REASONING,
    DEFAULT_SYSTEM_MESSAGE,
)

log = logging.getLogger(__name__)

CLASSIFICATION_SPAM = "spam_or_scam"
CLASSIFICATION_NOT_SPAM = "not_spam"

# Classifications that count as spam. "spam" is accepted alongside the
# documented "spam_or_scam" because prompts in the wild return either.
SPAM_CLASSIFICATIONS = ("spam", CLASSIFICATION_SPAM)


class BaseModerationBackend:
    """
    Interface implemented by every AI moderation backend.
    """

    def classify(self, content: str) -> Optional[Dict[str, Any]]:
        """
        Classify a piece of forum content.

        Args:
            content: The text content to classify.

        Returns:
            A moderation result::

                {
                    "classification": "spam_or_scam" | "not_spam",
                    "reasoning": "...",
                    "confidence_score": float | None,
                    "full_api_response": <raw provider response, for auditing>,
                }

            or None if the provider could not be reached or answered with
            something that could not be understood. Returning None must never
            raise: a failing classifier degrades moderation, it does not break
            posting.
        """
        raise NotImplementedError


class HTTPModerationBackend(BaseModerationBackend):  # pylint: disable=abstract-method
    """
    Base class for backends that call an HTTP moderation API.

    It owns the concerns that are the same whichever provider is in use --
    reading the endpoint, prompt and timeouts from Django settings, POSTing
    JSON, and turning the classifier's JSON payload into the common moderation
    result. Subclasses only describe the provider's request and response shape.
    """

    @property
    def api_url(self) -> Optional[str]:
        """Endpoint the classifier is served from."""
        return getattr(settings, "AI_MODERATION_API_URL", None)

    @property
    def system_message(self) -> str:
        """Prompt describing the classification task and its output format."""
        return (
            getattr(settings, "AI_MODERATION_SYSTEM_MESSAGE", None)
            or DEFAULT_SYSTEM_MESSAGE
        )

    @property
    def timeout(self) -> Tuple[float, float]:
        """Connection and read timeouts, in seconds."""
        return (
            getattr(
                settings, "AI_MODERATION_CONNECTION_TIMEOUT", DEFAULT_CONNECTION_TIMEOUT
            ),
            getattr(settings, "AI_MODERATION_READ_TIMEOUT", DEFAULT_READ_TIMEOUT),
        )

    def post(self, payload: Dict[str, Any], headers: Dict[str, str]) -> Optional[Any]:
        """
        POST a JSON payload to the configured endpoint and decode the response.

        Returns the decoded JSON body, or None if the request failed.
        """
        if not self.api_url:
            log.error("AI_MODERATION_API_URL setting is not configured")
            return None

        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except (
            requests.RequestException,
            requests.Timeout,
            requests.ConnectionError,
        ) as e:
            log.error(f"AI moderation API request failed: {e}")
            return None
        except ValueError as e:
            log.error(f"AI moderation API returned a non-JSON response: {e}")
            return None

    def parse_moderation_payload(
        self, raw_content: Any, full_api_response: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Turn the JSON document produced by the classifier into a moderation result.

        Args:
            raw_content: The classifier's answer, as a JSON string. Models
                routinely wrap it in a Markdown code fence, which is stripped.
            full_api_response: The provider's whole response, kept for auditing.

        Returns:
            The common moderation result, or None if it could not be parsed.
        """
        if not isinstance(raw_content, str) or not raw_content.strip():
            log.error("AI moderation response did not contain any content")
            return None

        try:
            parsed = json.loads(strip_code_fence(raw_content))
        except json.JSONDecodeError as e:
            log.error(f"Failed to parse AI moderation response JSON: {e}")
            return None

        if not isinstance(parsed, dict):
            log.error(
                f"Expected a JSON object from the AI moderation API, got {type(parsed)}"
            )
            return None

        return normalize_moderation_result(parsed, full_api_response)


def normalize_moderation_result(
    parsed: Dict[str, Any], full_api_response: Any
) -> Dict[str, Any]:
    """
    Fill in the keys the rest of AI moderation relies on.

    Any additional keys the classifier returned are preserved: they end up on
    the audit log, where they are worth having.
    """
    result = dict(parsed)
    result["classification"] = parsed.get("classification", CLASSIFICATION_NOT_SPAM)
    result["reasoning"] = parsed.get("reasoning", DEFAULT_REASONING)
    result["confidence_score"] = parsed.get("confidence_score")
    result["full_api_response"] = full_api_response
    return result


def strip_code_fence(text: str) -> str:
    """Remove a surrounding Markdown code fence, if the model added one."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    # Drop the opening fence, which may carry a language hint such as ```json.
    lines = stripped.splitlines()[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()
