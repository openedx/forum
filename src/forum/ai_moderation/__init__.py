"""
AI moderation for forum content.

Classifies each new thread and comment with the configured AI provider, flags
what comes back spam, and soft deletes it when auto-delete is enabled. Both
steps are gated on course waffle flags, and every spam verdict is recorded on a
moderation audit log.
"""
