"""
Common settings for forum app.
"""

from typing import Any

from forum.ai_moderation.defaults import (
    DEFAULT_CONNECTION_TIMEOUT,
    DEFAULT_FLAGGED_CACHE_PREFIX,
    DEFAULT_FLAGGED_CACHE_TTL,
    DEFAULT_READ_TIMEOUT,
    DEFAULT_SYSTEM_MESSAGE,
)


def plugin_settings(settings: Any) -> None:
    """
    Common settings for forum app
    """
    # Search backend
    if getattr(settings, "TYPESENSE_ENABLED", False):
        settings.FORUM_SEARCH_BACKEND = getattr(
            settings,
            "FORUM_SEARCH_BACKEND",
            "forum.search.typesense.TypesenseBackend",
        )
    elif getattr(settings, "MEILISEARCH_ENABLED", False):
        settings.FORUM_SEARCH_BACKEND = getattr(
            settings,
            "FORUM_SEARCH_BACKEND",
            "forum.search.meilisearch.MeilisearchBackend",
        )
    else:
        settings.FORUM_SEARCH_BACKEND = getattr(
            settings, "FORUM_SEARCH_BACKEND", "forum.search.es.ElasticsearchBackend"
        )
        settings.FORUM_ELASTIC_SEARCH_CONFIG = getattr(
            settings, "FORUM_ELASTIC_SEARCH_CONFIG", [{"host": "elasticsearch"}]
        )

    # Unfortunately we can't copy settings from edx-platform because tutor patches have
    # not been applied yet
    settings.FORUM_MONGODB_DATABASE = getattr(
        settings, "FORUM_MONGODB_DATABASE", "cs_comments_service"
    )
    settings.FORUM_MONGODB_CLIENT_PARAMETERS = getattr(
        settings, "FORUM_MONGODB_CLIENT_PARAMETERS", {"host": "mongodb"}
    )

    # Enable forum service
    if "ENABLE_DISCUSSION_SERVICE" not in settings.FEATURES:
        settings.FEATURES["ENABLE_DISCUSSION_SERVICE"] = True

    # URL prefix must match the regex in the url_config of the plugin app
    settings.COMMENTS_SERVICE_URL = getattr(
        settings, "COMMENTS_SERVICE_URL", "http://localhost:8000/forum"
    )

    # Timezone-awareness is required for mysql fields
    settings.USE_TZ = getattr(settings, "USE_TZ", True)

    # AI moderation. These run after the deployment's own configuration has been
    # read, so every one of them defers to an already configured value; they are
    # here to declare the settings and their defaults, not to impose them.
    #
    # AI_MODERATION_BACKEND has no default on purpose: forum defines the moderation
    # interface and ships no provider, so a deployment must name the backend it
    # wants. Neither does AI_MODERATION_API_URL, nor AI_MODERATION_USER_ID, which
    # decides who flagging and deletion are attributed to -- no user is created for
    # you. Whatever else a backend needs is read by that backend and deliberately
    # not declared here: the model name, the credential setting, or whatever else
    # the provider you wrap happens to want.
    settings.AI_MODERATION_BACKEND = getattr(settings, "AI_MODERATION_BACKEND", None)
    settings.AI_MODERATION_API_URL = getattr(settings, "AI_MODERATION_API_URL", None)
    settings.AI_MODERATION_USER_ID = getattr(settings, "AI_MODERATION_USER_ID", None)
    settings.AI_MODERATION_SYSTEM_MESSAGE = getattr(
        settings, "AI_MODERATION_SYSTEM_MESSAGE", DEFAULT_SYSTEM_MESSAGE
    )
    settings.AI_MODERATION_CONNECTION_TIMEOUT = getattr(
        settings, "AI_MODERATION_CONNECTION_TIMEOUT", DEFAULT_CONNECTION_TIMEOUT
    )
    settings.AI_MODERATION_READ_TIMEOUT = getattr(
        settings, "AI_MODERATION_READ_TIMEOUT", DEFAULT_READ_TIMEOUT
    )
    settings.AI_MODERATION_FLAGGED_CACHE_TTL = getattr(
        settings, "AI_MODERATION_FLAGGED_CACHE_TTL", DEFAULT_FLAGGED_CACHE_TTL
    )
    settings.AI_MODERATION_FLAGGED_CACHE_PREFIX = getattr(
        settings, "AI_MODERATION_FLAGGED_CACHE_PREFIX", DEFAULT_FLAGGED_CACHE_PREFIX
    )
