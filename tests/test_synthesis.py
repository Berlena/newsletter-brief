from __future__ import annotations

import copy
import json
import unittest
from datetime import date
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
        "reactions": "",
    }
    return {
        "title": "Your Morning Brief",
        "edition": "Wednesday brief",
        "date": "2026-11-18",
        "read_time_minutes": 3,
        "opening_note": "One letter, about the library.",
        "why_this_matters": "The vote is the only item, and it matches city services.",
        "facts": ["Library budget vote is on Thursday"],
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
        self.assertIn("facts", EDITION_JSON_SCHEMA["properties"])
        self.assertIn("reactions", EDITION_JSON_SCHEMA["properties"]["lead_story"]["properties"])

    def test_prompt_and_schema_require_plain_headlines(self) -> None:
        self.assertIn("who did what", EDITION_INSTRUCTIONS)
        self.assertIn("About 15 words", EDITION_INSTRUCTIONS)
        self.assertIn("why_it_matters is one line in plain words", EDITION_INSTRUCTIONS)
        self.assertIn("Stablecoin wars heat up", EDITION_INSTRUCTIONS)
        self.assertIn("Markets wobble", EDITION_INSTRUCTIONS)
        self.assertIn("The big AI race", EDITION_INSTRUCTIONS)
        self.assertIn(
            "Stripe now lets businesses hold USDC balances, so stablecoin payouts get cheaper",
            EDITION_INSTRUCTIONS,
        )
        self.assertIn(
            "The city council votes Thursday on a 2 million library budget",
            EDITION_INSTRUCTIONS,
        )
        self.assertIn(
            "The river gauge crossed its winter line after 40 mm of rain",
            EDITION_INSTRUCTIONS,
        )
        lead = EDITION_JSON_SCHEMA["properties"]["lead_story"]["properties"]
        card = EDITION_JSON_SCHEMA["properties"]["sections"]["items"]["properties"]["stories"][
            "items"
        ]["properties"]
        self.assertEqual(lead["title"]["description"], card["title"]["description"])
        self.assertIn("who did what", lead["title"]["description"])
        self.assertIn("About 15 words", lead["title"]["description"])
        self.assertIn("vague three-word phrases", lead["title"]["description"])
        self.assertIn("plain words", lead["why_it_matters"]["description"])
        self.assertIn("why it matters", lead["why_it_matters"]["description"])
        self.assertEqual(
            lead["title"]["description"],
            EDITION_JSON_SCHEMA["properties"]["facts"]["items"]["description"],
        )


class RetryAndCostTests(unittest.TestCase):
    def test_a_cut_off_answer_is_retried_once(self) -> None:
        calls: list[str] = []

        class Completions:
            def create(self, **kwargs: object) -> SimpleNamespace:
                calls.append(str(kwargs["model"]))
                if len(calls) == 1:
                    return SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                message=SimpleNamespace(content=""),
                                finish_reason="length",
                            )
                        ],
                        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
                    )
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content=json.dumps(_edition_payload())),
                            finish_reason="stop",
                        )
                    ],
                    usage=SimpleNamespace(prompt_tokens=80, completion_tokens=40),
                )

        brief = live_edition_synthesis(
            _edition_feed(),
            api_key="k",
            model="mock-model",
            base_url=DEFAULT_BASE_URL,
            title="Your Morning Brief",
            client=_client(Completions()),
        )
        self.assertEqual("Library budget vote", brief.lead_story.title)
        self.assertEqual(["mock-model", "mock-model"], calls)

    def test_a_second_schema_failure_writes_nothing(self) -> None:
        class Completions:
            def __init__(self) -> None:
                self.calls = 0

            def create(self, **kwargs: object) -> SimpleNamespace:
                self.calls += 1
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content='{"title":"only"}'),
                            finish_reason="stop",
                        )
                    ]
                )

        completions = Completions()
        with self.assertRaisesRegex(SynthesisError, "no brief was written"):
            live_edition_synthesis(
                _edition_feed(),
                api_key="k",
                model="mock-model",
                base_url=DEFAULT_BASE_URL,
                title="Your Morning Brief",
                client=_client(completions),
            )
        self.assertEqual(2, completions.calls)

    def test_usage_line_uses_the_configured_prices(self) -> None:
        from newsletter_brief.synthesis import Usage, format_usage

        line = format_usage(
            Usage(input_tokens=1000, output_tokens=500, known=True),
            input_per_million=0.40,
            output_per_million=1.60,
        )
        self.assertEqual(
            "tokens: 1000 in, 500 out; estimated cost $0.0012",
            line,
        )
        self.assertEqual(
            "tokens: unavailable",
            format_usage(Usage(), input_per_million=0.4, output_per_million=1.6),
        )

    def test_small_model_filters_before_the_brief(self) -> None:
        from newsletter_brief.models import NewsletterItem
        from newsletter_brief.synthesis import distill_items

        items = (
            NewsletterItem(
                item_id="m1-l1",
                publication="Harbor Daily",
                topic="Library",
                title="Library budget vote",
                excerpt="The council votes on Thursday.",
                source_url="https://harbor-daily.example/library-vote",
                section="City",
            ),
            NewsletterItem(
                item_id="m2-l1",
                publication="Other",
                topic="Ads",
                title="A shoe sale",
                excerpt="Shoes are on sale.",
                source_url="https://other.example/shoes",
                section="City",
            ),
        )

        class Completions:
            def __init__(self) -> None:
                self.models: list[str] = []

            def create(self, **kwargs: object) -> SimpleNamespace:
                model = str(kwargs["model"])
                self.models.append(model)
                if model == "small-model":
                    payload = {
                        "items": [
                            {
                                "id": "m1-l1",
                                "facts": ["The council votes on Thursday."],
                                "relevance": 80,
                            },
                            {"id": "m2-l1", "facts": ["Shoes are on sale."], "relevance": 10},
                        ]
                    }
                else:
                    body = json.loads(kwargs["messages"][1]["content"])  # type: ignore[index]
                    self.seen = [item["id"] for item in body["items"]]
                    payload = _edition_payload()
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content=json.dumps(payload)),
                            finish_reason="stop",
                        )
                    ],
                    usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
                )

        completions = Completions()
        kept = distill_items(
            items,
            api_key="k",
            model="small-model",
            base_url=DEFAULT_BASE_URL,
            interests=("city services",),
            relevance_min=40,
            max_chars=500,
            client=_client(completions),
        )
        self.assertEqual(["m1-l1"], [item.item_id for item in kept])
        self.assertIn("council votes", kept[0].excerpt)
        brief = live_edition_synthesis(
            NewsletterFeed(synthetic=False, edition_date=date(2026, 11, 18), items=kept),
            api_key="k",
            model="main-model",
            base_url=DEFAULT_BASE_URL,
            title="Your Morning Brief",
            client=_client(completions),
        )
        self.assertEqual(["small-model", "main-model"], completions.models)
        self.assertEqual(["m1-l1"], completions.seen)
        self.assertFalse(brief.public_demo)


if __name__ == "__main__":
    unittest.main()
