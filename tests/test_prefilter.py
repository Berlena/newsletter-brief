from __future__ import annotations

import logging
import unittest
from datetime import datetime, timezone

from newsletter_brief.models import NewsletterItem
from newsletter_brief.prefilter import finish_prefilter, strip_boilerplate

NOW = datetime(2026, 11, 18, 8, 0, tzinfo=timezone.utc)


def _item(title: str, url: str, excerpt: str, section: str = "City", **kwargs: object) -> NewsletterItem:
    return NewsletterItem(
        item_id="",
        publication="Harbor Daily",
        topic=title,
        title=title,
        excerpt=excerpt,
        source_url=url,
        section=section,
        published_at=kwargs.get("published_at", NOW),  # type: ignore[arg-type]
    )


class PrefilterTests(unittest.TestCase):
    def test_footer_is_removed_before_the_excerpt_is_cut(self) -> None:
        body = ("The council posted the full agenda for Thursday. " * 4) + (
            "Unsubscribe from this list. " * 30
        )
        cleaned = strip_boilerplate(body)
        self.assertNotIn("unsubscribe", cleaned.casefold())
        self.assertIn("agenda", cleaned)
        clipped = finish_prefilter(
            [_item("Library vote", "https://harbor-daily.example/vote", body)],
            max_chars=80,
            max_per_section=5,
        )
        self.assertNotIn("unsubscribe", clipped[0].excerpt.casefold())
        self.assertLessEqual(len(clipped[0].excerpt), 80)
        self.assertTrue(clipped[0].excerpt.startswith("The council"))

    def test_duplicate_links_and_near_duplicate_headlines_are_dropped(self) -> None:
        items = [
            _item(
                "Library budget vote is on Thursday",
                "https://harbor-daily.example/vote",
                "First copy of the vote.",
            ),
            _item(
                "Library budget vote is on Thursday!",
                "https://harbor-daily.example/other",
                "Same headline, different link.",
            ),
            _item(
                "River gauge crossed its line",
                "https://canopy-notes.example/gauge",
                "A different story.",
                section="Climate",
            ),
        ]
        kept = finish_prefilter(items, max_chars=500, max_per_section=5)
        titles = [item.title for item in kept]
        self.assertEqual(
            ["Library budget vote is on Thursday", "River gauge crossed its line"],
            titles,
        )

    def test_section_cap_keeps_the_newest(self) -> None:
        older = datetime(2026, 11, 17, 8, 0, tzinfo=timezone.utc)
        newer = datetime(2026, 11, 18, 7, 0, tzinfo=timezone.utc)
        items = [
            _item("Older one", "https://harbor-daily.example/old", "old", published_at=older),
            _item("Newer one", "https://harbor-daily.example/new", "new", published_at=newer),
            _item(
                "Other section",
                "https://canopy-notes.example/gauge",
                "gauge",
                section="Climate",
                published_at=older,
            ),
        ]
        kept = finish_prefilter(items, max_chars=500, max_per_section=1)
        self.assertEqual(
            ["Newer one", "Other section"],
            [item.title for item in kept],
        )

    def test_run_logs_the_counts(self) -> None:
        records: list[str] = []
        handler = logging.Handler()
        handler.emit = lambda record: records.append(record.getMessage())  # type: ignore[method-assign]
        logger = logging.getLogger("newsletter_brief")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            logger.info("items before prefilter: 4; after: 2")
        finally:
            logger.removeHandler(handler)
        self.assertIn("items before prefilter: 4; after: 2", records)


if __name__ == "__main__":
    unittest.main()
