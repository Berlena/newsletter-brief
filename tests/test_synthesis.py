from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from newsletter_brief.inputs import load_feed
from newsletter_brief.schema import parse_brief
from newsletter_brief.synthesis import (
    SynthesisError,
    ensure_grounded,
    live_synthesis,
)

ROOT = Path(__file__).resolve().parents[1]


class FakeResponses:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text
        self.request = None

    def create(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(output_text=self.output_text)


class SynthesisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.feed = load_feed(ROOT / "demo" / "newsletters.json")
        self.raw = json.loads((ROOT / "demo" / "prepared_response.json").read_text())

    def test_live_path_uses_mocked_structured_response(self) -> None:
        responses = FakeResponses(json.dumps(self.raw))
        client = SimpleNamespace(responses=responses)

        brief = live_synthesis(
            self.feed,
            api_key="ci-placeholder",
            model="mock-model",
            client=client,
        )

        self.assertEqual("The Morning Edit", brief.title)
        self.assertEqual("mock-model", responses.request["model"])
        self.assertFalse(responses.request["store"])
        response_format = responses.request["text"]["format"]
        self.assertEqual("json_schema", response_format["type"])
        self.assertTrue(response_format["strict"])
        self.assertNotIn("ci-placeholder", json.dumps(responses.request))

    def test_output_cannot_invent_a_source_url(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["lead_story"]["source_url"] = "https://invented-source.example/story"
        brief = parse_brief(raw)
        with self.assertRaisesRegex(SynthesisError, "absent from the input feed"):
            ensure_grounded(brief, self.feed)

    def test_output_date_must_match_inputs(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["date"] = "2026-07-27"
        brief = parse_brief(raw)
        with self.assertRaisesRegex(SynthesisError, "date does not match"):
            ensure_grounded(brief, self.feed)


if __name__ == "__main__":
    unittest.main()
