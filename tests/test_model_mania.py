"""Model Mania uses saved catalog fixtures. These tests do not touch the network."""

from __future__ import annotations

import json
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from newsletter_brief.email_html import render_email
from newsletter_brief.model_mania import (
    ARTIFICIAL_ANALYSIS_URL,
    HF_URL,
    LMARENA_URL,
    OPENROUTER_URL,
    accept_model_note,
    bind_notes,
    fetch_model_releases,
    note_source_allowlist,
    releases_from_huggingface,
    releases_from_openrouter,
)
from newsletter_brief.models import Brief, ModelNote, ModelRelease, NewsletterFeed, NewsletterItem, Section, Story
from newsletter_brief.renderer import render_html
from newsletter_brief.schema import SchemaError, parse_edition
from newsletter_brief.synthesis import live_edition_synthesis

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def _load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _story() -> dict[str, str]:
    return {
        "title": "The council votes Thursday on a library budget",
        "summary": "Harbor Daily says the vote is Thursday.",
        "why_it_matters": "The vote decides what the library can keep open.",
        "key_fact": "The vote is Thursday",
        "source_label": "Harbor Daily",
        "source_url": "https://harbor-daily.example/library-vote",
        "reactions": "",
        "context": "",
        "context_source": "",
    }


def _edition_payload(notes: list[dict[str, str]]) -> dict[str, object]:
    story = _story()
    return {
        "title": "Your Morning Brief",
        "edition": "Wednesday brief",
        "date": "2026-11-18",
        "read_time_minutes": 3,
        "opening_note": "One letter, about the library.",
        "why_this_matters": "The vote is the only item.",
        "facts": ["The council votes Thursday on a library budget"],
        "lead_story": story,
        "sections": [{"name": "City", "stories": [story]}],
        "events": [],
        "model_notes": notes,
    }


class CatalogFilterTests(unittest.TestCase):
    def test_openrouter_keeps_six_newest_text_models_inside_the_window(self) -> None:
        releases = releases_from_openrouter(
            _load("openrouter-models.json"),
            now=NOW,
            window_hours=60,
            limit=6,
        )
        names = [item.name for item in releases]
        self.assertEqual(
            ["Cedar Large", "Pine Mid", "Birch", "Alder", "Maple", "Ash"],
            names,
        )
        self.assertNotIn("Yew", names)
        self.assertNotIn("Old Oak", names)
        self.assertNotIn("Embed Mini", names)
        self.assertNotIn("Pixel", names)
        cedar = releases[0]
        self.assertEqual("Example Lab", cedar.maker)
        self.assertEqual(128000, cedar.context_length)
        self.assertEqual("$3.00", cedar.input_per_million)
        self.assertEqual("$15.00", cedar.output_per_million)
        self.assertEqual("", cedar.blurb)
        self.assertIn("https://huggingface.co/example-lab/cedar-large", cedar.source_urls)
        self.assertEqual("", releases[-1].input_per_million)
        self.assertIsNone(releases[-1].context_length)

    def test_huggingface_keeps_recent_open_models_above_the_like_floor(self) -> None:
        releases = releases_from_huggingface(
            _load("huggingface-models.json"),
            now=NOW,
            max_age_hours=168,
            min_likes=100,
            limit=6,
        )
        self.assertEqual(
            ["example-lab/cedar-large", "example-lab/spruce-open"],
            [item.model_id for item in releases],
        )
        spruce = releases[1]
        self.assertTrue(spruce.open_weights)
        self.assertEqual(8192, spruce.context_length)
        self.assertEqual("", spruce.input_per_million)
        self.assertEqual("Example Lab", spruce.maker)

    def test_a_failed_fetch_logs_and_returns_nothing(self) -> None:
        def boom(url: str) -> bytes:
            raise OSError(f"down {url}")

        with self.assertLogs("newsletter_brief.model_mania", level="WARNING") as logs:
            releases = fetch_model_releases(
                enabled=True,
                huggingface=True,
                now=NOW,
                get=boom,
            )
        self.assertEqual((), releases)
        text = "\n".join(logs.output).casefold()
        self.assertIn("model mania", text)
        self.assertNotIn("sk-", text)

    def test_fetch_uses_https_fixtures_and_skips_a_failed_second_source(self) -> None:
        calls: list[str] = []

        def get(url: str) -> bytes:
            calls.append(url)
            if url == OPENROUTER_URL:
                return _load("openrouter-models.json")
            raise OSError("open weights down")

        with self.assertLogs("newsletter_brief.model_mania", level="WARNING"):
            releases = fetch_model_releases(
                enabled=True,
                huggingface=True,
                now=NOW,
                get=get,
            )
        self.assertEqual([OPENROUTER_URL, HF_URL], calls)
        self.assertTrue(all(url.startswith("https://") for url in calls))
        self.assertEqual(6, len(releases))
        self.assertFalse(fetch_model_releases(enabled=False, get=get))

    def test_notes_need_a_provided_source_and_an_attribution(self) -> None:
        releases = releases_from_openrouter(
            _load("openrouter-models.json"),
            now=NOW,
            window_hours=60,
            limit=6,
        )
        allowed = note_source_allowlist(releases)
        self.assertIn(LMARENA_URL, allowed)
        self.assertIn(ARTIFICIAL_ANALYSIS_URL, allowed)
        kept = accept_model_note(
            "North Lab says it beats Cedar on a long note.",
            LMARENA_URL,
            allowed,
        )
        self.assertEqual("North Lab says it beats Cedar on a long note.", kept)
        self.assertEqual("", accept_model_note("It beats Cedar on every test.", LMARENA_URL, allowed))
        self.assertEqual(
            "",
            accept_model_note(
                "North Lab says it is careful.",
                "https://invented.example/note",
                allowed,
            ),
        )
        self.assertEqual(
            "",
            accept_model_note("Listed on OpenRouter yesterday.", LMARENA_URL, allowed),
        )
        self.assertEqual("", accept_model_note("A short note.", "", allowed))
        bound = bind_notes(
            releases,
            (
                ModelNote("example-lab/cedar-large", kept, LMARENA_URL),
                ModelNote("example-lab/pine-mid", "It beats Cedar.", LMARENA_URL),
                ModelNote("not-a-model", kept, LMARENA_URL),
            ),
        )
        self.assertEqual(kept, bound[0].note)
        self.assertEqual(LMARENA_URL, bound[0].note_source)
        self.assertEqual("", bound[1].note)

    def test_rendered_block_uses_catalog_facts_and_hides_plumbing(self) -> None:
        releases = releases_from_openrouter(
            _load("openrouter-models.json"),
            now=NOW,
            window_hours=60,
            limit=1,
        )
        bound = bind_notes(
            releases,
            (ModelNote("example-lab/cedar-large", "North Lab says it beats Pine.", LMARENA_URL),),
        )
        story = Story(
            title="A placeholder headline for the fixture",
            summary="Nothing here is a live price.",
            why_it_matters="The block is the thing under test.",
            key_fact="One fixture model",
            source_label="Example Notes",
            source_url="https://example-notes.example/story",
        )
        brief = Brief(
            synthetic=False,
            title="Your Morning Brief",
            edition="Wednesday",
            edition_date=date(2026, 11, 18),
            read_time_minutes=2,
            opening_note="One line.",
            top_lines=("One fixture model", "A second line", "A third line"),
            lead_story=story,
            sections=(Section(name="AI", stories=(story,)),),
            public_demo=False,
            model_releases=bound,
        )
        html = render_html(brief)
        email = render_email(brief)
        for rendered in (html, email):
            self.assertIn("Model mania", rendered)
            self.assertIn("Cedar Large", rendered)
            self.assertIn("Example Lab", rendered)
            self.assertIn("128,000 tokens", rendered)
            self.assertIn("$3.00", rendered)
            self.assertIn("$15.00", rendered)
            self.assertIn("North Lab says it beats Pine.", rendered)
            self.assertIn(LMARENA_URL, rendered)
            self.assertIn(ARTIFICIAL_ANALYSIS_URL, rendered)
            self.assertNotIn("openrouter", rendered.casefold())
            self.assertNotIn("Listed on", rendered)


class NoteSchemaTests(unittest.TestCase):
    def test_many_sections_parse_and_a_bad_note_url_does_not_fail_the_brief(self) -> None:
        payload = _edition_payload(
            [{"model_id": "example-lab/cedar-large", "note": "A sentence.", "source_url": "not a url"}]
        )
        sections = []
        story = _story()
        for name in (
            "AI",
            "Tech & SaaS",
            "Fintech",
            "VC & Funds",
            "Markets & Big Tech",
            "Politics",
            "Weekend",
            "Read Longer",
        ):
            sections.append({"name": name, "stories": [story]})
        payload["sections"] = sections
        brief = parse_edition(payload, expect_notes=True)
        self.assertEqual(8, len(brief.sections))
        self.assertEqual("Read Longer", brief.sections[-1].name)
        self.assertEqual("", brief.model_notes[0].source_url)
        too_many = dict(payload)
        too_many["sections"] = sections + [{"name": f"Extra {index}", "stories": [story]} for index in range(5)]
        with self.assertRaisesRegex(SchemaError, "1 to 12"):
            parse_edition(too_many, expect_notes=True)

    def test_synthesis_drops_unsourced_notes_and_keeps_an_attributed_one(self) -> None:
        releases = releases_from_openrouter(
            _load("openrouter-models.json"),
            now=NOW,
            window_hours=60,
            limit=1,
        )
        payload = _edition_payload(
            [
                {
                    "model_id": "example-lab/cedar-large",
                    "note": "North Lab says it beats Pine.",
                    "source_url": LMARENA_URL,
                },
                {
                    "model_id": "example-lab/cedar-large",
                    "note": "It beats Pine.",
                    "source_url": LMARENA_URL,
                },
                {
                    "model_id": "example-lab/missing",
                    "note": "North Lab says it beats Pine.",
                    "source_url": ARTIFICIAL_ANALYSIS_URL,
                },
            ]
        )

        class Completions:
            def __init__(self) -> None:
                self.request = None

            def create(self, **kwargs: object) -> dict[str, object]:
                self.request = kwargs
                return {"choices": [{"message": {"content": json.dumps(payload)}}]}

        completions = Completions()
        feed = NewsletterFeed(
            synthetic=False,
            edition_date=date(2026, 11, 18),
            items=(
                NewsletterItem(
                    item_id="m1",
                    publication="Harbor Daily",
                    topic="Library",
                    title="Library budget vote",
                    excerpt="The council votes on Thursday.",
                    source_url="https://harbor-daily.example/library-vote",
                ),
            ),
        )
        brief = live_edition_synthesis(
            feed,
            api_key="test-key",
            model="mock-model",
            base_url="https://api.openai.com/v1",
            title="Your Morning Brief",
            client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
            model_catalog=releases,
        )
        self.assertEqual(1, len(brief.model_notes))
        self.assertEqual("North Lab says it beats Pine.", brief.model_notes[0].text)
        self.assertEqual(LMARENA_URL, brief.model_notes[0].source_url)
        assert completions.request is not None
        self.assertIn("model_notes", completions.request["response_format"]["json_schema"]["schema"]["properties"])
        self.assertIn("North Lab says it beats", completions.request["messages"][0]["content"])
        sent = json.loads(completions.request["messages"][1]["content"])
        self.assertEqual("", sent["model_catalog"][0]["description"])
        self.assertNotIn("openrouter", json.dumps(sent).casefold())


if __name__ == "__main__":
    unittest.main()
