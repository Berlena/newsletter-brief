"""Email fallback and a long section list, for the page and the message."""

from __future__ import annotations

import re
import unittest
from datetime import date
from html import escape

from newsletter_brief.email_html import render_email
from newsletter_brief.models import Brief, Figure, Section, Story
from newsletter_brief.presentation import PILL_COLORS
from newsletter_brief.renderer import render_html

NAMES = (
    "AI",
    "Tech & SaaS",
    "Fintech",
    "VC & Funds",
    "Markets & Big Tech",
    "Politics",
    "Weekend",
    "Read Longer",
)


def _story(title: str) -> Story:
    return Story(
        title=title,
        summary="A placeholder sentence about the section.",
        why_it_matters="It belongs in the brief.",
        key_fact="One placeholder",
        source_label="Example Notes",
        source_url="https://example-notes.example/story",
    )


def _brief() -> Brief:
    lead = _story("A lead sentence for the long list")
    return Brief(
        synthetic=False,
        title="Your Morning Brief",
        edition="Wednesday",
        edition_date=date(2026, 11, 18),
        read_time_minutes=4,
        opening_note="One quiet line.",
        why_this_matters="The section list is the thing under test.",
        top_lines=("First fact", "Second fact", "Third fact"),
        lead_story=lead,
        sections=tuple(Section(name=name, stories=(_story(name),)) for name in NAMES),
        public_demo=False,
        figures=(
            Figure(
                figure_id="eur-usd",
                label="EUR to USD",
                value="1.1000",
                source_name="ECB reference rate",
                source_url="https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html",
                as_of="2026-11-17",
                available=True,
            ),
            Figure(
                figure_id="btc-usd",
                label="Bitcoin",
                value="unavailable",
                source_name="CoinGecko",
                source_url="https://www.coingecko.com/en/coins/bitcoin",
                as_of="",
                available=False,
            ),
        ),
    )


def _gmail(html: str) -> str:
    """Drop the style block and unwrap details, the way Gmail strips them."""

    html = re.sub(r"<style\b[^>]*>.*?</style>", "", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"</?details\b[^>]*>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"</?summary\b[^>]*>", "", html, flags=re.IGNORECASE)
    return html


class MarketsFallbackTests(unittest.TestCase):
    def test_email_keeps_a_compact_line_when_details_are_stripped(self) -> None:
        html = render_email(_brief())
        self.assertIn("<details", html)
        self.assertIn("<summary", html)
        self.assertIn('class="markets-compact"', html)
        self.assertIn('class="sum-label"', html)
        self.assertIn('class="markets-full"', html)
        self.assertIn("details.markets-details > summary .sum-label", html)
        self.assertIn("details.markets-details[open] .markets-full", html)
        self.assertIn("details.markets-details + .markets-compact", html)
        self.assertRegex(html, r'class="sum-label"[^>]*style="[^"]*display:none')
        self.assertRegex(html, r'class="markets-full"[^>]*style="[^"]*display:none')
        compact = html.split('class="markets-compact"', 1)[1]
        self.assertIn("EUR/USD 1.1000", compact)
        self.assertIn("Bitcoin unavailable", compact)
        self.assertNotIn("display:none", compact.split(">", 1)[0])

        stripped = _gmail(html)
        self.assertNotIn("<details", stripped.casefold())
        self.assertNotIn("<summary", stripped.casefold())
        self.assertIn("EUR/USD 1.1000", stripped)
        self.assertIn("Bitcoin unavailable", stripped)
        self.assertRegex(stripped, r'class="markets-full"[^>]*style="[^"]*display:none')
        self.assertRegex(stripped, r'class="sum-label"[^>]*style="[^"]*display:none')
        self.assertNotIn("Show the figures", stripped)

    def test_page_toggle_is_closed_until_the_reader_opens_it(self) -> None:
        html = render_html(_brief())
        self.assertIn('<details class="markets-toggle">', html)
        self.assertNotIn('<details class="markets-toggle" open', html)
        self.assertIn("EUR/USD 1.1000", html)
        self.assertIn(">Show<", html)
        self.assertIn(">Hide<", html)
        self.assertIn("Not written by the summary.", html)


class ManySectionTests(unittest.TestCase):
    def test_sections_keep_config_order_and_cycle_pill_colors(self) -> None:
        page = render_html(_brief())
        email = render_email(_brief())
        for html in (page, email):
            markers = [f">{escape(name)}<" for name in NAMES]
            positions = [html.index(marker) for marker in markers]
            self.assertEqual(sorted(positions), positions)
            self.assertGreaterEqual(html.count(PILL_COLORS[0][0]), 2)
            self.assertGreaterEqual(html.count(PILL_COLORS[1][0]), 2)
            first = html.index(PILL_COLORS[0][0])
            second = html.index(PILL_COLORS[1][0])
            self.assertLess(first, second)
        self.assertIn("Inter", page)
        self.assertIn("#4a1028", page)
        self.assertIn("#d0e79b", page)


if __name__ == "__main__":
    unittest.main()
