"""
Provider-independent defaults for AI moderation.

Every value here is the fallback used when the matching Django setting is not
configured. Nothing in this module may encode the behaviour of a single AI
provider: which provider answers is chosen entirely by AI_MODERATION_BACKEND,
which has no default -- forum ships an interface, not a provider.

The one thing forum does supply is the prompt, so that standing up a backend
does not also mean writing a spam classifier prompt from scratch.
"""

# Seconds to wait for the connection to be established, and then for the
# classifier to answer. Moderation runs inline with thread/comment creation, so
# the connect timeout is deliberately short.
DEFAULT_CONNECTION_TIMEOUT = 1.0
DEFAULT_READ_TIMEOUT = 30

# Spam verdicts are cached by content hash so an identical repost does not cost
# a second API call. Clean verdicts are never cached.
DEFAULT_FLAGGED_CACHE_TTL = 60 * 60 * 24
DEFAULT_FLAGGED_CACHE_PREFIX = "ai_moderation:flagged:v1"

# Value used for a missing `reasoning` field in a classifier response.
DEFAULT_REASONING = "No reasoning provided"

DEFAULT_SYSTEM_MESSAGE = """\
Filter posts from a discussion forum platform to identify and flag content that is likely to be spam or a scam.

**Instructions**:
- Carefully analyze each post's text for language, links, or patterns typical of spam or scams.
- Use clear reasoning to identify suspicious indicators such as:
  * Promotional language or unsolicited commercial content
  * Misleading claims or "too good to be true" offers
  * Excessive external links (especially non-educational domains)
  * Requests for personal information (phone numbers, email, social media)
  * Suspicious offers (money, investment, guaranteed results)
  * Impersonation of authority figures (course staff, professors)
  * Directing users to external communication platforms (WhatsApp, Telegram)
  * Cryptocurrency, forex, or investment scheme language
  * Urgent pressure tactics ("act now", "limited time")

- After thoroughly explaining your reasoning and highlighting specific suspicious features,
  classify the post as either "spam_or_scam" or "not_spam".
- **Do not make a classification before detailing your reasoning.** Always present your
  analysis of the post's content before your final determination.
- If uncertainty exists, explain which factors made detection difficult before concluding.
- Consider legitimate use cases: Course-related external links (.edu domains), genuine help
  requests, study group formation.

**Output Format** (strict JSON, and nothing else):
{
  "reasoning": "[Detailed explanation of why this post may or may not be spam/scam,
                 referencing specific features of the post. Minimum 2 sentences.]",
  "classification": "[spam_or_scam | not_spam]"
}

**Examples**:

Example 1 (Spam):
Post: "Hi everyone! I'm Professor Johnson. Contact me on WhatsApp +1-555-0123 for
guaranteed A+ grades. Limited slots!"
Output:
{
  "reasoning": "This post exhibits multiple red flags: (1) Impersonation of a professor
                with no verification, (2) request to contact via WhatsApp with phone
                number, (3) unrealistic promise of 'guaranteed A+ grades', (4) urgency
                tactic 'limited slots'. These are classic patterns of academic scams
                targeting students.",
  "classification": "spam_or_scam"
}

Example 2 (Not Spam):
Post: "Can someone explain the difference between merge sort and quick sort? I'm
struggling with the time complexity analysis."
Output:
{
  "reasoning": "This is a legitimate academic question about sorting algorithms. The post
                contains no suspicious links, no requests for external contact, no
                promotional language, and is directly related to course content. The tone
                is appropriate for a learner seeking help.",
  "classification": "not_spam"
}"""
