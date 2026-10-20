"""Tests for handling trusted links in content before it is classified."""

import time

import pytest

from forum.ai_moderation.links import has_risk_signals, is_blank, strip_trusted_links

TRUSTED = ("codepen.io", "github.com", "developer.mozilla.org")


class TestStripTrustedLinks:
    """Tests for strip_trusted_links."""

    @pytest.mark.parametrize(
        "content, expected",
        [
            (
                "My pen: https://codepen.io/learner/pen/abcXYZ can you help?",
                "My pen:  can you help?",
            ),
            ("http://codepen.io/learner/pen/abcXYZ", ""),
            ("See codepen.io/learner/pen/abcXYZ please", "See  please"),
            ("Try https://www.codepen.io/pen/1.", "Try "),
            ("Docs: https://developer.mozilla.org/en-US/docs/Web/CSS/flex", "Docs: "),
            ("Fork https://gist.github.com/someone/123", "Fork "),
            ("HTTPS://CODEPEN.IO/LEARNER/PEN/1 thanks", " thanks"),
            ("https://codepen.io:443/pen/1?editors=1100#top done", " done"),
            ("I love codepen.io.", "I love ."),
        ],
    )
    def test_trusted_urls_are_removed(self, content: str, expected: str) -> None:
        """A trusted URL is removed whatever its scheme, case, subdomain or path."""
        assert strip_trusted_links(content, TRUSTED) == expected

    @pytest.mark.parametrize(
        "content",
        [
            "Visit https://top-grade-helpers.example/order now",
            "https://codepen.io.evil.example/pen/1",
            "https://notcodepen.io/pen/1",
            "https://codepen-io.example/pen/1",
            "mail me at someone@codepen.io",
            "www.example.com and https://example.org/codepen",
        ],
    )
    def test_other_urls_are_left_alone(self, content: str) -> None:
        """Lookalike and untrusted hosts are left for the classifier to judge."""
        assert strip_trusted_links(content, TRUSTED) == content

    def test_untrusted_host_stays_visible_when_a_trusted_url_is_embedded(
        self,
    ) -> None:
        """
        Removing a trusted URL that sits inside another URL never hides the
        untrusted host around it.
        """
        content = "Go to https://evil.example/?next=https://codepen.io/pen/1"

        assert "https://evil.example/" in strip_trusted_links(content, TRUSTED)

    def test_trusted_anchor_is_replaced_by_its_text(self) -> None:
        """The editor writes links as anchors; a trusted one becomes plain text."""
        content = (
            '<p>Here is <a href="https://codepen.io/learner/pen/abc" '
            'target="_blank" rel="noopener">my pen</a>, what is wrong?</p>'
        )

        assert strip_trusted_links(content, TRUSTED) == (
            "<p>Here is my pen, what is wrong?</p>"
        )

    def test_autolinked_trusted_url_is_removed_entirely(self) -> None:
        """An autolinked URL is both the href and the text; neither is left."""
        content = (
            '<p><a href="https://codepen.io/learner/pen/abc">'
            "https://codepen.io/learner/pen/abc</a></p>"
        )

        assert strip_trusted_links(content, TRUSTED) == "<p></p>"

    def test_single_quoted_and_uppercase_anchors_are_unwrapped(self) -> None:
        """Quote style and tag case do not matter."""
        content = "<P>See <A HREF='https://codepen.io/learner/pen/abc'>my pen</A></P>"

        assert strip_trusted_links(content, TRUSTED) == "<P>See my pen</P>"

    def test_every_trusted_anchor_is_unwrapped(self) -> None:
        """Each trusted anchor is replaced by its own text."""
        content = (
            '<p><a href="https://codepen.io/learner/pen/1">one</a> and '
            '<a href="https://github.com/learner/repo">two</a></p>'
        )

        assert strip_trusted_links(content, TRUSTED) == "<p>one and two</p>"

    def test_unclosed_trusted_anchor_is_left_in_place(self) -> None:
        """
        An anchor that is never closed keeps its tag, so the post is still
        classified; only the trusted URL is taken out of it.
        """
        content = '<p><a href="https://codepen.io/learner/pen/abc">my pen</p>'

        assert strip_trusted_links(content, TRUSTED) == '<p><a href="">my pen</p>'

    def test_untrusted_anchor_is_kept(self) -> None:
        """
        An anchor to an untrusted host is kept, even when its text is a trusted
        URL: the href is what a reader would actually follow.
        """
        content = (
            '<p><a href="https://evil.example/landing">'
            "https://codepen.io/learner/pen/abc</a></p>"
        )

        assert strip_trusted_links(content, TRUSTED) == (
            '<p><a href="https://evil.example/landing"></a></p>'
        )

    def test_rest_of_a_spam_post_is_kept(self) -> None:
        """A trusted link does not take the spam around it out of the post."""
        content = "Guaranteed A grades! WhatsApp +1-555-0199 https://codepen.io/pen/1"

        assert strip_trusted_links(content, TRUSTED) == (
            "Guaranteed A grades! WhatsApp +1-555-0199 "
        )

    @pytest.mark.parametrize("domains", [(), [], None, ("", "  ")])
    def test_no_trusted_domains_leaves_content_unchanged(self, domains: object) -> None:
        """With nothing trusted, every link is classified like any other text."""
        content = "My pen: https://codepen.io/learner/pen/abc"

        assert strip_trusted_links(content, domains) == content  # type: ignore[arg-type]

    def test_domains_are_normalized(self) -> None:
        """Domains configured with odd case, padding or dots still match."""
        content = "My pen: https://codepen.io/learner/pen/abc"

        assert strip_trusted_links(content, [" .CodePen.IO. "]) == "My pen: "

    def test_reported_case(self) -> None:
        """Pens a learner shares in a CSS course are removed, as on-topic links."""
        content = "<p>My solution: https://codepen.io/learner/pen/abc</p>"

        assert strip_trusted_links(content, TRUSTED) == "<p>My solution: </p>"


class TestIsBlank:
    """Tests for is_blank."""

    @pytest.mark.parametrize(
        "content", ["", "   ", "<p></p>", "<p> </p>\n<p>&nbsp;</p>", "<br/><br />"]
    )
    def test_blank_content(self, content: str) -> None:
        """Whitespace and bare wrapping tags leave nothing to classify."""
        assert is_blank(content) is True

    @pytest.mark.parametrize(
        "content",
        [
            "hi",
            "<p>hi</p>",
            '<p><img src="https://spam.example/ad.png"></p>',
            '<p><a href="https://evil.example"></a></p>',
        ],
    )
    def test_content_to_classify(self, content: str) -> None:
        """Text, or any tag carrying attributes, is still worth classifying."""
        assert is_blank(content) is False


class TestHasRiskSignals:
    """Tests for has_risk_signals."""

    @pytest.mark.parametrize(
        "content",
        [
            "Order now at https://top-grade-helpers.example/order",
            "Cheap essays at www.essays.example",
            "Best grades: bestessays.com",
            "Message me: wa.me/15550199",
            "Join t.me/scamgroup",
            "Visit zoom.us.in for details",
            "Fork it at codepen.oi/editor/learner/pen/019f1be8",
            "Free grades: bit.ly/free-grades",
            "See example.zz/offer for more",
            '<p><a href="https://evil.example/landing">register</a></p>',
            '<p><a href="/courses/other">this</a></p>',
            '<p><img src="https://spam.example/ad.png"></p>',
            '<iframe src="https://evil.example"></iframe>',
            "Email tutor@example.com for answers",
            "Call +1-555-0199 today",
            "Reach me on +91 98765 43210",
            "Contact (555) 123-4567",
            "Add me on WhatsApp",
            "Ping me on whats app",
            "Join our Telegram group",
            "I am on WeChat and Viber",
            "Join discord.gg/abc123",
            "Everything is on linktr.ee/helper",
            "Sign up at forms.gle/abc",
            "Shortened: shorturl.at/abc",
            "Email tutor at gmail dot com",
            "Visit evil&#46;com",
            "What\u200bsApp me",
            "Whats-App me",
            "Ｗｈａｔｓａｐｐ me",
        ],
    )
    def test_ways_to_contact_or_redirect(self, content: str) -> None:
        """Any other link, contact detail or messaging app is a risk signal."""
        assert has_risk_signals(content) is True

    @pytest.mark.parametrize(
        "content",
        [
            "",
            "<p>Use this like fo registation : URL</p>",
            "<p>My solution:  why is the footer not sticky?</p>",
            "<p>Join our study session on Monday at 5pm in room 101</p>",
            "Edit style.css and index.html, then reload",
            'Use document.getElementById("nav") and node.js 18',
            "body { margin: 0 auto; width: 960px; color: #333; }",
            "e.g. flexbox, i.e. the 2024 spec, version 1.2.3",
            "Week 3, question 5 of 10",
            "Open src/app.js and ../css/style.css",
            "width: calc(100% / 3);",
        ],
    )
    def test_ordinary_posts(self, content: str) -> None:
        """Everyday post text, code included, carries no risk signal."""
        assert has_risk_signals(content) is False

    def test_long_post_is_checked_quickly(self) -> None:
        """A long post without a risk signal does not stall the request."""
        start = time.perf_counter()
        assert has_risk_signals("a" * 50_000) is False
        assert time.perf_counter() - start < 1

    def test_reported_case_passes_once_its_trusted_link_is_removed(self) -> None:
        """A meeting registration link with a short note, a lure to the classifier."""
        content = (
            "<p>Use this like fo registation : "
            '<a href="https://us02web.zoom.us/meeting/register/tJ0kcuGrqTsiE'
            '#/registration" target="_blank" rel="noopener">URL</a></p>'
        )
        stripped = strip_trusted_links(content, ["zoom.us"])

        assert stripped == "<p>Use this like fo registation : URL</p>"
        assert has_risk_signals(stripped) is False

    def test_scam_keeps_its_risk_once_its_trusted_link_is_removed(self) -> None:
        """A scam that adds a trusted link still offers another way to reach it."""
        content = (
            "Guaranteed A grades! WhatsApp +1-555-0199 https://us02web.zoom.us/j/1"
        )
        stripped = strip_trusted_links(content, ["zoom.us"])

        assert stripped == "Guaranteed A grades! WhatsApp +1-555-0199 "
        assert has_risk_signals(stripped) is True


class TestHostilePosts:
    """
    Moderation runs inside the request that creates a post, and posts have no
    size limit, so link handling has to stay linear on hostile input.
    """

    @pytest.mark.parametrize(
        "content",
        [
            "a" * 50_000,
            "a." * 25_000,
            "1 " * 25_000 + "x",
            ("whats" + " " * 50) * 1_000,
            '<a href="x" ' * 5_000,
            '<a href="https://codepen.io/x">y' * 2_000,
            "</a" + " " * 50_000,
            ("<a" + " " * 50) * 1_000,
        ],
    )
    def test_hostile_post_is_handled_quickly(self, content: str) -> None:
        """Stripping, the blank check and the risk check all finish quickly."""
        start = time.perf_counter()
        stripped = strip_trusted_links(content, TRUSTED)
        is_blank(stripped)
        has_risk_signals(stripped)
        assert time.perf_counter() - start < 1
