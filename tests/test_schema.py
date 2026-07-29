from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from newsletter_brief.schema import SchemaError, load_brief, parse_brief

ROOT = Path(__file__).resolve().parents[1]


class SchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = json.loads((ROOT / "demo" / "prepared_response.json").read_text())

    def test_committed_response_is_valid(self) -> None:
        brief = load_brief(ROOT / "demo" / "prepared_response.json")
        self.assertTrue(brief.synthetic)
        self.assertEqual("Your Morning Brief", brief.title)

    def test_missing_required_field_is_rejected(self) -> None:
        raw = copy.deepcopy(self.raw)
        del raw["lead_story"]["summary"]
        with self.assertRaisesRegex(
            SchemaError, "brief.lead_story is missing: summary"
        ):
            parse_brief(raw)

    def test_unknown_field_is_rejected(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["tracking_id"] = "not-allowed"
        with self.assertRaisesRegex(SchemaError, "unexpected fields"):
            parse_brief(raw)

    def test_unsafe_source_url_is_rejected(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["lead_story"]["source_url"] = "javascript:alert(1)"
        with self.assertRaisesRegex(SchemaError, "absolute HTTPS URL"):
            parse_brief(raw)

    def test_non_synthetic_output_is_rejected(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["synthetic"] = False
        with self.assertRaisesRegex(SchemaError, "must be true"):
            parse_brief(raw)


if __name__ == "__main__":
    unittest.main()
