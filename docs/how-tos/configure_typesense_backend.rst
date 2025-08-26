Configuring Typesense Search Backend
====================================

Forum also supports Typesense as the search backend.
Typesense as both a single node and as a HA cluster is supported.

This is not the default though; Meilisearch is the default backend.

To configure, you can set the following Django settings for LMS and CMS:

.. code-block:: python

    TYPESENSE_ENABLED = True
    TYPESENSE_API_KEY = "your-secret-api-key-for-typesense"
    TYPESENSE_URLS = ["https://typesense-1.example.com:8108", "https://typesense-2.example.com:8108"]
    # Optional: if you need to manually override the backend path for testing
    #FORUM_SEARCH_BACKEND = "forum.search.typesense.TypesenseBackend"

Alternately, if you deploy using Tutor, you can use the `tutor-contrib-typesense`_
plugin, which will automatically deploy a single node Typesense instance
and configure forum to use it.

.. _tutor-contrib-typesense: https://github.com/open-craft/tutor-contrib-typesense/
