"""
Example Django settings for AI Moderation.

Add these settings to your Django configuration to customize AI moderation behavior.
"""

# AI Moderation API Configuration
AI_MODERATION_API_URL = "https://xpert-api-services.prod.ai.2u.com/v1/message"
AI_MODERATION_CLIENT_ID = "edx-harvard-forum-spam"
AI_MODERATION_SYSTEM_MESSAGE = (
    "Filter posts from a discussion forum platform to identify and flag content "
    "that is likely to be spam or a scam. Output JSON with properties: reasoning "
    "for Detailed explanation of why this post may or may not be spam/scam, "
    "referencing specific features of the post. Minimum 2 sentences and "
    "classification of spam or not_spam."
)
AI_MODERATION_TIMEOUT = 30  # seconds

# Example of how to add these to your settings.py:
"""
# AI Moderation Settings
AI_MODERATION_API_URL = env.str(
    "AI_MODERATION_API_URL", 
    default="https://xpert-api-services.prod.ai.2u.com/v1/message"
)
AI_MODERATION_CLIENT_ID = env.str(
    "AI_MODERATION_CLIENT_ID", 
    default="edx-harvard-forum-spam"
)
AI_MODERATION_TIMEOUT = env.int("AI_MODERATION_TIMEOUT", default=30)
"""