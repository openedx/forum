Configure AI moderation
#######################

Forum can classify new threads and comments as spam and flag them, using an AI
provider of your choosing. Forum ships the interface; you supply a backend that
wraps your provider.


1. Write a backend
******************

Subclass ``HTTPModerationBackend`` and describe three things: how to
authenticate, what the request body looks like, and where the verdict sits in
the response.

.. code-block:: python

    from django.conf import settings

    from forum.ai_moderation.backends import HTTPModerationBackend


    class MyProviderBackend(HTTPModerationBackend):
        def classify(self, content):
            headers = {
                "content-type": "application/json",
                "Authorization": f"Bearer {settings.MY_PROVIDER_API_KEY}",
            }
            payload = {
                "model": settings.MY_PROVIDER_MODEL,
                "messages": [
                    {"role": "system", "content": self.system_message},
                    {"role": "user", "content": content},
                ],
            }

            response = self.post(payload, headers)
            if response is None:
                return None

            answer = response["choices"][0]["message"]["content"]
            return self.parse_moderation_payload(answer, response)

``self.post()`` and ``self.parse_moderation_payload()`` handle the endpoint,
timeouts, network failures and parsing; ``self.system_message`` is the prompt.
See ``forum.ai_moderation.backends.base`` for the interface and what
``classify()`` must return.

If your provider is not a JSON HTTP API, subclass ``BaseModerationBackend`` and
implement ``classify()`` however you like.

Put the class anywhere the LMS can import.


2. Configure it
***************

.. code-block:: python

    AI_MODERATION_BACKEND = "myproject.moderation.MyProviderBackend"
    AI_MODERATION_API_URL = "https://api.myprovider.example.com/v1/chat/completions"
    AI_MODERATION_USER_ID = 42

    # Read by your backend, named however you like.
    MY_PROVIDER_API_KEY = "..."
    MY_PROVIDER_MODEL = "..."

All three forum settings are required and have no defaults.
``AI_MODERATION_USER_ID`` is the user that flagging and deletion are attributed
to; no user is created for you.

Set them however your deployment sets Django settings -- with Tutor, a plugin
patching ``openedx-lms-production-settings``. Forum declares these settings in
its own plugin settings, so there is nothing to add to edx-platform.

Optional:

``AI_MODERATION_SYSTEM_MESSAGE``
    Your own prompt. Defaults to forum's, which asks for the JSON that
    ``parse_moderation_payload()`` expects.

``AI_MODERATION_CONNECTION_TIMEOUT``, ``AI_MODERATION_READ_TIMEOUT``
    Default to 1.0 and 30 seconds. Moderation runs inline with posting, so keep
    them low.

``AI_MODERATION_FLAGGED_CACHE_TTL``, ``AI_MODERATION_FLAGGED_CACHE_PREFIX``
    Spam verdicts are cached by content hash for 24 hours, so an identical
    repost costs no second API call. Clean verdicts are never cached.


3. Turn it on
*************

Two course waffle flags, both off by default:

``discussions.enable_ai_moderation``
    Classify new threads and comments, and flag what comes back spam.

``discussions.enable_ai_auto_delete_spam``
    Also delete what was flagged. Has no effect on its own.

Enable them site-wide in Django admin under ``waffle/flag``, or per course with
a "Waffle flag course override" at
``/admin/waffle_utils/waffleflagcourseoverridemodel/``.
