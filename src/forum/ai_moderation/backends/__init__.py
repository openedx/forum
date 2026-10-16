"""
AI moderation backends.

Each backend adapts one AI provider to the common moderation interface. The
backend in use is chosen with the ``AI_MODERATION_BACKEND`` setting, so nothing
outside this package needs to know which provider is answering.
"""

from forum.ai_moderation.backends.base import (
    BaseModerationBackend,
    HTTPModerationBackend,
)

__all__ = ["BaseModerationBackend", "HTTPModerationBackend"]
