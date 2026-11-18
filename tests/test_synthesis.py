from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from newsletter_brief.provider import DEFAULT_BASE_URL
from newsletter_brief.inputs import load_feed
from newsletter_brief.models import NewsletterFeed, NewsletterItem
from newsletter_brief.schema import EDITION_JSON_SCHEMA, parse_brief, parse_edition
from newsletter_brief.synthesis import (
    EDITION_INSTRUCTIONS,
    SynthesisError,
    ensure_grounded,
    live_edition_synthesis,
    live_synthesis,
)

ROOT = Path(__file__).resolve().parents[1]


class FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.request = None

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.request = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


def _client(completions: FakeCompletions) -> SimpleNamespace:
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


class SynthesisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.feed = load_feed(ROOT / "demo" / "newsletters.json")
        self.raw = json.loads((ROOT / "demo" / "prepared_response.json").read_text())

    def test_live_path_uses_mocked_structured_response(self) -> None:
        completions = FakeCompletions(json.dumps(self.raw))
        brief = live_synthesis(
            self.feed,
            api_key="ci-placeholder",
            model="mock-model",
            base_url=DEFAULT_BASE_URL,
            client=_client(completions),
        )

        self.assertEqual("Your Morning Brief", brief.title)
        self.assertEqual("mock-model", completions.request["model"])
        self.assertFalse(completions.request["store"])
        response_format = completions.request["response_format"]
        self.assertEqual("json_schema", response_format["type"])
        self.assertTrue(response_format["json_schema"]["strict"])
        self.assertNotIn("ci-placeholder", json.dumps(completions.request))

    def test_output_cannot_invent_a_source_url(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["lead_story"]["source_url"] = "https://invented-source.example/story"
        brief = parse_brief(raw)
        with self.assertRaisesRegex(SynthesisError, "absent from the input feed"):
            ensure_grounded(brief, self.feed)

    def test_api_key_is_not_copied_into_a_live_error(self) -> None:
        class Boom:
            def create(self, **kwargs: object) -> None:
                raise RuntimeError("rejected key super-secret-key")

        with self.assertRaises(SynthesisError) as caught:
            live_synthesis(
                self.feed,
                api_key="super-secret-key",
                model="mock-model",
                base_url=DEFAULT_BASE_URL,
                client=_client(Boom()),  # type: ignore[arg-type]
            )
        self.assertNotIn("super-secret-key", str(caught.exception))
        self.assertIn("[redacted]", str(caught.exception))

    def test_output_date_must_match_inputs(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["date"] = "2026-07-27"
        brief = parse_brief(raw)
        with self.assertRaisesRegex(SynthesisError, "date does not match"):
            ensure_grounded(brief, self.feed)


def _edition_feed() -> NewsletterFeed:
    from datetime import date

    url = "https://harbor-daily.example/library-vote"
    return NewsletterFeed(
        synthetic=False,
        edition_date=date(2026, 11, 18),
        items=(
            NewsletterItem(
                item_id="m1",
                publication="Harbor Daily",
                topic="Library",
                title="Library budget vote",
                excerpt="The council votes on Thursday.",
                source_url=url,
            ),
        ),
    )


def _edition_payload() -> dict[str, object]:
    url = "https://harbor-daily.example/library-vote"
    story = {
        "title": "Library budget vote",
        "summary": "The council votes on the library budget on Thursday.",
        "why_it_matters": "It decides what the library can keep open.",
        "key_fact": "The vote is Thursday",
        "source_label": "Harbor Daily",
        "source_url": url,
    }
    return {
        "title": "Your Morning Brief",
        "edition": "Wednesday brief",
        "date": "2026-11-18",
        "read_time_minutes": 3,
        "opening_note": "One letter, about the library.",
        "why_this_matters": "The vote is the only item, and it matches city services.",
        "top_lines": ["Library budget vote is on Thursday"],
        "lead_story": story,
        "sections": [{"name": "City", "stories": [story]}],
        "events": [
            {
                "title": "Library budget vote",
                "when": "Thursday",
                "detail": "The council votes on the library budget.",
                "source_label": "Harbor Daily",
                "source_url": url,
            }
        ],
    }


class EditionGroundingTests(unittest.TestCase):
    def test_events_and_why_box_must_use_input_links(self) -> None:
        feed = _edition_feed()
        brief = parse_edition(_edition_payload())
        ensure_grounded(brief, feed)

        invented = _edition_payload()
        invented["why_this_matters"] = (
            "See https://invented.example/context for a claim nobody sent."
        )
        with self.assertRaisesRegex(SynthesisError, "absent from the input feed"):
            ensure_grounded(parse_edition(invented), feed)

        bad_event = _edition_payload()
        bad_event["events"][0]["source_url"] = "https://invented.example/event"  # type: ignore[index]
        with self.assertRaisesRegex(SynthesisError, "https://invented.example/event"):
            ensure_grounded(parse_edition(bad_event), feed)

    def test_edition_schema_has_no_figures_field(self) -> None:
        self.assertIn("why_this_matters", EDITION_JSON_SCHEMA["properties"])
        self.assertIn("events", EDITION_JSON_SCHEMA["properties"])
        self.assertNotIn("figures", EDITION_JSON_SCHEMA["properties"])
        self.assertNotIn("market prices", EDITION_JSON_SCHEMA["properties"])
        payload = _edition_payload()
        payload["figures"] = [{"value": "1.1000"}]
        from newsletter_brief.schema import SchemaError

        with self.assertRaisesRegex(SchemaError, "unexpected fields"):
            parse_edition(payload)

    def test_live_edition_keeps_store_false_and_drops_the_key(self) -> None:
        completions = FakeCompletions(json.dumps(_edition_payload()))
        brief = live_edition_synthesis(
            _edition_feed(),
            api_key="super-secret-key",
            model="mock-model",
            base_url=DEFAULT_BASE_URL,
            title="Your Morning Brief",
            interests=("city services",),
            client=_client(completions),
        )
        self.assertEqual("Library budget vote", brief.events[0].title)
        self.assertFalse(brief.public_demo)
        self.assertFalse(completions.request["store"])
        self.assertTrue(completions.request["response_format"]["json_schema"]["strict"])
        self.assertEqual(
            EDITION_JSON_SCHEMA,
            completions.request["response_format"]["json_schema"]["schema"],
        )
        self.assertIn("Do not write market prices", EDITION_INSTRUCTIONS)
        self.assertEqual(EDITION_INSTRUCTIONS, completions.request["messages"][0]["content"])
        self.assertNotIn("super-secret-key", json.dumps(completions.request))
        self.assertIn("city services", completions.request["messages"][1]["content"])


if __name__ == "__main__":
    unittest.main()
