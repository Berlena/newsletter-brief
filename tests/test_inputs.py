from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from newsletter_brief.inputs import InputError, load_feed, parse_feed

ROOT = Path(__file__).resolve().parents[1]


class InputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = json.loads((ROOT / "demo" / "newsletters.json").read_text())

    def test_committed_feed_is_synthetic_and_valid(self) -> None:
        feed = load_feed(ROOT / "demo" / "newsletters.json")
        self.assertTrue(feed.synthetic)
        self.assertEqual(7, len(feed.items))

    def test_real_data_flag_is_rejected(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["synthetic"] = False
        with self.assertRaisesRegex(InputError, "real newsletter data is excluded"):
            parse_feed(raw)

    def test_duplicate_ids_are_rejected(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["items"][1]["id"] = raw["items"][0]["id"]
        with self.assertRaisesRegex(InputError, "must be unique"):
            parse_feed(raw)

    def test_unexpected_fields_are_rejected(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["items"][0]["sender_email"] = "excluded value"
        with self.assertRaisesRegex(InputError, "unexpected fields"):
            parse_feed(raw)


if __name__ == "__main__":
    unittest.main()
