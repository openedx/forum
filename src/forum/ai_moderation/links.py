"""
Handling of trusted links in content before it is classified.

The classifier only ever sees the text of a post, never the course it was
posted in, so it cannot tell a learner sharing their CodePen in a CSS course
from someone dropping a link to advertise. Links to the domains a deployment
trusts are therefore taken out before classification.

Taking the link out is not always enough: a short post such as "register here:
<link>" reads as a lure to the classifier with or without its link. So a post
whose links are all trusted is not classified at all, unless it also gives
readers another way to be contacted or sent elsewhere -- a link to any other
domain, an email address, a phone number or a messaging app. Those are what a
scam needs, so a scam that adds a trusted link is still classified, without the
trusted link.
"""

import bisect
import html
import re
import unicodedata
from functools import lru_cache
from typing import Iterable, Optional, Pattern

# The tags of an HTML anchor, as written by the discussions editor. An anchor
# pointing at a trusted domain is replaced by its text, so the classifier is
# not left looking at an empty link. Opening and closing tags are found
# separately, and an opening tag cannot run past the next "<", so this stays
# linear however malformed the HTML of a post is: moderation runs inside the
# request that creates the post, and posts have no size limit.
_ANCHOR_OPEN_RE = re.compile(r"<a\b[^<>]*>", re.IGNORECASE)
_ANCHOR_CLOSE_RE = re.compile(r"</a\s*>", re.IGNORECASE)
_HREF_RE = re.compile(r"\bhref\s*=\s*(?:\"([^\"]*)\"|'([^']*)')", re.IGNORECASE)

# Markup that carries nothing to classify: tags without attributes, such as the
# <p> and <br> wrapping a post. A tag with attributes, like an <img src=...>,
# is content in its own right.
_BARE_TAG_RE = re.compile(r"</?[a-zA-Z][a-zA-Z0-9]*\s*/?>")

# Top-level domains a bare domain written without "http" or "www." is
# recognised by. Not exhaustive: a bare domain under any other TLD goes
# unnoticed unless a path follows it, as in "codepen.oi/editor/...".
_COMMON_TLDS = (
    "com|net|org|info|biz|edu|gov|co|io|me|ly|us|uk|in|ru|cn|ai|app|dev|xyz"
    "|online|site|shop|store|top|click|link|live|club|vip|tk|cc|tv|ws|pw"
)

# Ways a post can send readers somewhere other than a trusted link: a link with
# a scheme or "www.", a bare domain under a common TLD or followed by a path,
# an anchor or embedded media (trusted anchors have been unwrapped by then), an
# email address, a messaging app, or a spelled-out "dot com". Every alternative
# that can match a long run of characters only starts at the beginning of a
# word, which keeps the search linear.
_RISK_SIGNAL_RE = re.compile(
    r"https?://|www\.|<(?:a|img|iframe|video|embed|object)\b"
    rf"|(?<![\w@.-])(?:[a-z0-9-]+\.)+(?:(?:{_COMMON_TLDS})(?![\w-])|[a-z]{{2,63}}/)"
    r"|(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+"
    r"|\b(?:whats[\W_]*app|telegram|wechat|viber|discord|skype|snapchat)\b"
    r"|\bdot\W{0,3}(?:com|net|org)\b",
    re.IGNORECASE,
)

# Characters that render as nothing, such as a zero-width space inside
# "WhatsApp", used to hide a link or contact detail from a pattern.
_INVISIBLE_RE = re.compile(r"[\u00ad\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]")

# A run of digits that may be a phone number. It only counts as one with at
# least _PHONE_MIN_DIGITS digits, which leaves sizes, versions and the like be.
_PHONE_CANDIDATE_RE = re.compile(r"\+?\(?\d[\d\s().-]{6,}\d")
_PHONE_MIN_DIGITS = 8


@lru_cache(maxsize=8)
def _trusted_link_pattern(domains: tuple[str, ...]) -> Optional[Pattern[str]]:
    """
    Build a pattern matching a URL on any of ``domains``, or a subdomain of one.

    The host has to end exactly at the trusted domain, so ``codepen.io`` matches
    neither ``codepen.io.example.com`` nor ``notcodepen.io``. The scheme is
    optional because learners often type ``codepen.io/...`` without one.
    """
    names = sorted(
        {domain.strip().strip(".").lower() for domain in domains if domain.strip()},
        key=len,
        reverse=True,
    )
    if not names:
        return None

    hosts = "|".join(re.escape(name) for name in names)
    return re.compile(
        rf"(?<![\w.@-])(?:(?:https?:)?//)?(?:[\w-]+\.)*(?:{hosts})(?::\d+)?"
        rf"(?![\w-]|\.[\w-])(?:[/?#][^\s<>\"']*)?",
        re.IGNORECASE,
    )


def strip_trusted_links(content: str, trusted_domains: Optional[Iterable[str]]) -> str:
    """
    Remove every link to a trusted domain from ``content``.

    Args:
        content: The text about to be classified. May contain HTML.
        trusted_domains: Domains whose links, including links to their
            subdomains, are removed.

    Returns:
        ``content`` without the trusted links. Links to any other domain, and
        all other text, are left exactly as they were.
    """
    if not content or not trusted_domains:
        return content

    pattern = _trusted_link_pattern(tuple(trusted_domains))
    if pattern is None:
        return content

    return pattern.sub("", _unwrap_trusted_anchors(content, pattern))


def _unwrap_trusted_anchors(content: str, pattern: Pattern[str]) -> str:
    """
    Replace every anchor whose href matches ``pattern`` by the anchor's text.

    An anchor runs from its opening tag to the first closing tag after it. One
    that is never closed is left as it is.
    """
    closings = [match.span() for match in _ANCHOR_CLOSE_RE.finditer(content)]
    closing_starts = [start for start, _ in closings]
    parts = []
    position = 0
    for opening in _ANCHOR_OPEN_RE.finditer(content):
        opening_start, opening_end = opening.span()
        if opening_start < position:
            # Inside an anchor that has already been replaced by its text.
            continue
        href = _HREF_RE.search(opening.group(0))
        if href is None:
            continue
        url = href.group(1) if href.group(1) is not None else href.group(2)
        if not pattern.fullmatch(url.strip()):
            continue
        index = bisect.bisect_left(closing_starts, opening_end)
        if index == len(closings):
            continue
        closing_start, closing_end = closings[index]
        parts.append(content[position:opening_start])
        parts.append(content[opening_end:closing_start])
        position = closing_end
    parts.append(content[position:])
    return "".join(parts)


def is_blank(content: str) -> bool:
    """Return whether ``content`` holds nothing but whitespace and bare tags."""
    text = _BARE_TAG_RE.sub("", content or "").replace("&nbsp;", " ")
    return not text.strip()


def has_risk_signals(content: str) -> bool:
    """
    Return whether ``content`` gives readers a way to be contacted or redirected.

    Meant for content that trusted links have already been removed from: any
    link left in it, an email address, a phone number or a messaging app
    mention counts. A false match is harmless, since it only means the content
    is classified as usual, whereas a miss means it is not classified at all.
    """
    if not content:
        return False
    # Undo the usual ways of hiding a link or contact from a pattern: HTML
    # entities, full-width letters and invisible characters.
    content = unicodedata.normalize("NFKC", html.unescape(content))
    content = _INVISIBLE_RE.sub("", content)
    if _RISK_SIGNAL_RE.search(content):
        return True
    return any(
        sum(char.isdigit() for char in candidate) >= _PHONE_MIN_DIGITS
        for candidate in _PHONE_CANDIDATE_RE.findall(content)
    )
