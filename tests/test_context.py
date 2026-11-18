from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

from newsletter_brief.context_lookup import (
    SUMMARY_URL,
    lookup_summaries,
    names_from_items,
    parse_summary,
)
from newsletter_brief.models import Brief, NewsletterFeed, NewsletterItem, Section, Story
from newsletter_brief.renderer import render_html
from newsletter_brief.schema import SchemaError, parse_edition
from newsletter_brief.synthesis import EDITION_INSTRUCTIONS, SynthesisError, ensure_grounded

FIXTURES = Path(__file__).parent / "fixtures"
URL = "https://harbor-daily.example/library-vote"
WIKI = "https://en.wikipedia.org/wiki/Example_Company"


def _story(**overrides: str) -> dict[str, str]:
    story = {
        "title": "The council votes Thursday on a 2 million library budget",
        "summary": "Harbor Daily says the council votes on the library budget on Thursday.",
        "why_it_matters": "The vote decides what the library can keep open.",
        "key_fact": "The vote is Thursday",
        "source_label": "Harbor Daily",
        "source_url": URL,
        "reactions": "",
        "context": "",
        "context_source": "",
    }
    story.update(overrides)
    return story


def _payload(story: dict[str, str]) -> dict[str, object]:
    return {
        "title": "Your Morning Brief",
        "edition": "Wednesday brief",
        "date": "2026-11-18",
        "read_time_minutes": 3,
        "opening_note": "One letter, about the library.",
        "why_this_matters": "The vote is the only item, and it matches city services.",
        "facts": ["The council votes Thursday on a 2 million library budget"],
        "lead_story": story,
        "sections": [{"name": "City", "stories": [story]}],
        "events": [],
    }


def _feed() -> NewsletterFeed:
    return NewsletterFeed(
        synthetic=False,
        edition_date=date(2026, 11, 18),
        items=(
            NewsletterItem(
                item_id="m1-l1",
                publication="Harbor Daily",
                topic="Library",
                title="Library budget vote",
                excerpt="The council votes on Thursday. Last year's budget was 1.8 million.",
                source_url=URL,
            ),
            NewsletterItem(
                item_id="m2-l1",
                publication="Example Company",
                topic="Payments",
                title="Example Company adds a new payout rail",
                excerpt="Example Company processes card payments for online businesses.",
                source_url="https://example-company.example/payouts",
            ),
        ),
    )


class ContextRuleTests(unittest.TestCase):
    def test_prompt_and_schema_require_a_sourced_context_line(self) -> None:
        self.assertIn("about 25 words", EDITION_INSTRUCTIONS)
        self.assertIn("who a lesser-known company or person is", EDITION_INSTRUCTIONS)
        self.assertIn("Do not add trivia", EDITION_INSTRUCTIONS)
        self.assertIn("Fun fact: the logo is blue.", EDITION_INSTRUCTIONS)
        self.assertIn("Interesting company.", EDITION_INSTRUCTIONS)
        self.assertIn("Stripe was founded by two brothers.", EDITION_INSTRUCTIONS)
        self.assertIn(
            "Stripe processes card payments for online businesses, which is why a USDC balance can lower their payout costs.",
            EDITION_INSTRUCTIONS,
        )
        self.assertIn(
            "USDC was about 30 percent of stablecoin transfer volume last quarter, up from 22 percent the quarter before.",
            EDITION_INSTRUCTIONS,
        )
        self.assertIn(
            "The library budget was 1.8 million last year, so 2 million is a small increase.",
            EDITION_INSTRUCTIONS,
        )
        from newsletter_brief.schema import EDITION_JSON_SCHEMA

        context = EDITION_JSON_SCHEMA["properties"]["lead_story"]["properties"]["context"]
        source = EDITION_JSON_SCHEMA["properties"]["lead_story"]["properties"]["context_source"]
        self.assertIn("about 25 words", context["description"])
        self.assertIn("Not trivia", context["description"])
        self.assertIn("provided source", source["description"])
        self.assertIn("context", EDITION_JSON_SCHEMA["properties"]["lead_story"]["required"])
        self.assertIn("context_source", EDITION_JSON_SCHEMA["properties"]["lead_story"]["required"])

    def test_context_without_a_source_is_rejected(self) -> None:
        story = _story(context="The library budget was 1.8 million last year, so 2 million is a small increase.")
        with self.assertRaisesRegex(SchemaError, "context_source"):
            parse_edition(_payload(story))

    def test_a_long_context_line_is_rejected(self) -> None:
        story = _story(
            context=" ".join(["word"] * 26),
            context_source=URL,
        )
        with self.assertRaisesRegex(SchemaError, "25 words"):
            parse_edition(_payload(story))

    def test_context_from_another_item_is_grounded(self) -> None:
        other = "https://example-company.example/payouts"
        line = "Example Company processes card payments for online businesses."
        story = _story(context=line, context_source=other)
        brief = parse_edition(_payload(story))
        ensure_grounded(brief, _feed())
        invented = _story(context=line, context_source="https://invented.example/context")
        with self.assertRaisesRegex(SynthesisError, "absent from the input feed"):
            ensure_grounded(parse_edition(_payload(invented)), _feed())

    def test_wikipedia_fixture_is_capped_and_https_only(self) -> None:
        payload = (FIXTURES / "wiki-summary.json").read_bytes()
        page, extract = parse_summary(payload) or ("", "")
        self.assertEqual(WIKI, page)
        self.assertIn("card payments", extract)
        self.assertIsNone(parse_summary(b'{"type": "disambiguation", "extract": "no"}'))
        calls: list[str] = []

        def get(url: str) -> bytes:
            calls.append(url)
            if "Missing_Name" in url:
                raise TimeoutError(url)
            return payload

        found = lookup_summaries(
            ["Example Company", "Example Company", "Missing Name", "Third Name", "Fourth Name"],
            timeout=8,
            max_lookups=2,
            get=get,
        )
        self.assertEqual(2, len(calls))
        self.assertTrue(all(url.startswith(SUMMARY_URL) for url in calls))
        self.assertTrue(all(url.startswith("https://") for url in calls))
        self.assertEqual([WIKI], [item.url for item in found])
        self.assertEqual(["Example Company"], names_from_items([
            NewsletterItem(
                item_id="m1",
                publication="Example Company",
                topic="Payments",
                title="Thursday update from the desk",
                excerpt="",
                source_url=URL,
            )
        ]))

    def test_card_renders_a_small_source_link_and_an_empty_field_adds_nothing(self) -> None:
        story = Story(
            title="The council votes Thursday on a 2 million library budget",
            summary="Harbor Daily says the vote is Thursday.",
            why_it_matters="The vote decides what the library can keep open.",
            key_fact="The vote is Thursday",
            source_label="Harbor Daily",
            source_url=URL,
            context="The library budget was 1.8 million last year, so 2 million is a small increase.",
            context_source=WIKI,
        )
        brief = Brief(
            synthetic=False,
            title="Your Morning Brief",
            edition="Wednesday",
            edition_date=date(2026, 11, 18),
            read_time_minutes=2,
            opening_note="One letter.",
            why_this_matters="The vote matches city services.",
            top_lines=("The council votes Thursday on a 2 million library budget",),
            lead_story=story,
            sections=(Section(name="City", stories=(story,)),),
            public_demo=False,
        )
        html = render_html(brief)
        self.assertIn('class="context"', html)
        self.assertIn(WIKI, html)
        self.assertIn("en.wikipedia.org", html)
        self.assertIn("1.8 million", html)
        empty = Story(
            title=story.title,
            summary=story.summary,
            why_it_matters=story.why_it_matters,
            key_fact=story.key_fact,
            source_label=story.source_label,
            source_url=story.source_url,
        )
        quiet = Brief(
            synthetic=False,
            title=brief.title,
            edition=brief.edition,
            edition_date=brief.edition_date,
            read_time_minutes=brief.read_time_minutes,
            opening_note=brief.opening_note,
            why_this_matters=brief.why_this_matters,
            top_lines=brief.top_lines,
            lead_story=empty,
            sections=(Section(name="City", stories=(empty,)),),
            public_demo=False,
        )
        self.assertNotIn('class="context"', render_html(quiet))

    def test_a_lookup_error_is_skipped(self) -> None:
        def get(url: str) -> bytes:
            raise TimeoutError(url)

        self.assertEqual((), lookup_summaries(["Example Company"], timeout=8, max_lookups=1, get=get))


if __name__ == "__main__":
    unittest.main()
