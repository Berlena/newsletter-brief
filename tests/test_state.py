from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from newsletter_brief.models import NewsletterItem
from newsletter_brief.statefile import drop_seen, load_memory, remember, save_memory

TODAY = date(2026, 11, 18)
NOW = datetime(2026, 11, 18, 8, 0, tzinfo=timezone.utc)


def _item(title: str, url: str) -> NewsletterItem:
    return NewsletterItem(
        item_id="m1-l1",
        publication="Harbor Daily",
        topic="Library",
        title=title,
        excerpt="text",
        source_url=url,
        published_at=NOW,
    )


class StateTests(unittest.TestCase):
    def test_recent_headline_or_link_is_skipped_and_older_than_two_days_is_kept(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.json"
            memory = load_memory(path)
            remember(
                memory,
                [_item("Library budget vote is on Thursday", "https://harbor-daily.example/vote")],
                [],
                today=date(2026, 11, 17),
                days=2,
                sent=False,
            )
            save_memory(path, memory)
            loaded = load_memory(path)
            fresh = [
                _item("Library budget vote is on Thursday", "https://harbor-daily.example/again"),
                _item("River gauge", "https://harbor-daily.example/vote"),
                _item("A new stall", "https://field-table.example/stall"),
            ]
            kept = drop_seen(fresh, loaded, today=TODAY, days=2)
            self.assertEqual(["A new stall"], [item.title for item in kept])

            memory.seen = [
                {
                    "day": "2026-11-10",
                    "title": "a new stall",
                    "url": "https://field-table.example/stall",
                }
            ]
            kept_old = drop_seen(fresh, memory, today=TODAY, days=2)
            self.assertEqual(3, len(kept_old))

    def test_already_sent_flag_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "nested" / "state.json"
            memory = load_memory(path)
            self.assertFalse(memory.already_sent(TODAY))
            remember(memory, [], [], today=TODAY, days=2, sent=True)
            save_memory(path, memory)
            self.assertTrue(load_memory(path).already_sent(TODAY))

    def test_state_file_name_is_gitignored(self) -> None:
        text = Path(__file__).resolve().parents[1].joinpath(".gitignore").read_text(encoding="utf-8")
        self.assertIn("state.json", text)


if __name__ == "__main__":
    unittest.main()
