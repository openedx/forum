"""
These settings are here to use during tests, because django requires them.

In a real-world use case, apps in this project are installed into other
Django applications, so these settings will not be used.
"""

from os.path import abspath, dirname, join


def root(*args: str) -> str:
    """
    Get the absolute path of the given path relative to the project root.
    """
    return join(abspath(dirname(__file__)), *args)


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "default.db",
        "USER": "",
        "PASSWORD": "",
        "HOST": "",
        "PORT": "",
    }
}

INSTALLED_APPS = (
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.messages",
    "django.contrib.sessions",
    "forum",
)

LOCALE_PATHS = [
    root("forum", "conf", "locale"),
]

ROOT_URLCONF = "forum.urls"

SECRET_KEY = "insecure-secret-key"

MIDDLEWARE = (
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
)

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": False,
        "OPTIONS": {
            "context_processors": [
                "django.contrib.auth.context_processors.auth",  # this is required for admin
                "django.contrib.messages.context_processors.messages",  # this is required for admin
            ],
        },
    }
]

FORUM_MONGODB_DATABASE = "testdb"
FORUM_MONGODB_CLIENT_PARAMETERS: dict[str, str] = {}

FORUM_SEARCH_BACKEND = "forum.search.es.ElasticsearchBackend"
FORUM_ELASTIC_SEARCH_CONFIG = [
    {
        "host": "localhost",
        "port": "5200",
        "use_ssl": False,
    }
]

# Meilisearch connection parameters
MEILISEARCH_URL = "http://localhost:5700"
MEILISEARCH_API_KEY = "MEILISEARCH_MASTER_KEY"

USE_TZ = True

TYPESENSE_COLLECTION_PREFIX = "forum_unittest_prefix_"
TYPESENSE_API_KEY = "example-typesense-api-key"
TYPESENSE_URLS = ["http://0.0.0.0:8108"]
