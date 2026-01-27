"""
Test functionality used in settings.
"""

from unittest.mock import MagicMock

from forum.settings.production import plugin_settings


def test_plugin_settings_typesense() -> None:
    settings = MagicMock(
        spec=["TYPESENSE_ENABLED", "FEATURES"], TYPESENSE_ENABLED=True, FEATURES={}
    )

    # This function changes settings in-place.
    plugin_settings(settings)

    assert settings.FORUM_SEARCH_BACKEND == "forum.search.typesense.TypesenseBackend"
