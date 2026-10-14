"""
Common settings for forum app.
"""

from typing import Any


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

    # .. toggle_name: FORUM_ENABLE_HTTP_API
    # .. toggle_implementation: DjangoSetting
    # .. toggle_default: False
    # .. toggle_description: Route the legacy forum HTTP API under the plugin's
    #   URL prefix. These endpoints are a compatibility layer from when the forum
    #   ran as a standalone cs_comments_service on a private network. They read
    #   the acting user from a request parameter, so a caller may act on behalf
    #   of any user and is required to authenticate as a staff service account.
    #   edx-platform does not use them -- it calls forum.api in process -- so they
    #   are disabled by default. Only enable this if you serve the forum as a
    #   separate HTTP service, and prefer to keep it off the public internet even
    #   so, since a single leaked staff credential reaches every user's content.
    # .. toggle_use_cases: opt_in
    # .. toggle_creation_date: 2026-09-21
    settings.FORUM_ENABLE_HTTP_API = getattr(settings, "FORUM_ENABLE_HTTP_API", False)

    # Timezone-awareness is required for mysql fields
    settings.USE_TZ = getattr(settings, "USE_TZ", True)
