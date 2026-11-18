from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from newsletter_brief.feeds import FeedError, FeedRequest, items_from_feed, read_feeds
from newsletter_brief.models import NewsletterFeed, NewsletterItem
from newsletter_brief.schema import parse_edition
from newsletter_brief.synthesis import SynthesisError, ensure_grounded

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 18, 8, 0, tzinfo=timezone.utc)
HARBOR = "https://harbor-daily.example/feed.xml"
CANOPY = "https://canopy-notes.example/feed.xml"


class FeedParseTests(unittest.TestCase):
    def test_rss_and_atom_keep_recent_links_and_strip_tracking(self) -> None:
        def get(url: str) -> bytes:
            if url == HARBOR:
                return (FIXTURES / "harbor-rss.xml").read_bytes()
            if url == CANOPY:
                return (FIXTURES / "canopy-atom.xml").read_bytes()
            raise AssertionError(url)

        items = read_feeds(
            (
                FeedRequest(url=HARBOR, section="City", hours=24, max_entries=8),
                FeedRequest(url=CANOPY, section="Climate", hours=24, max_entries=8),
            ),
            max_chars=2000,
            now=NOW,
            get=get,
        )
        urls = [item.source_url for item in items]
        self.assertIn("https://harbor-daily.example/library-vote?id=3", urls)
        self.assertIn("https://harbor-daily.example/minutes", urls)
        self.assertIn("https://canopy-notes.example/river-gauge", urls)
        self.assertIn("https://canopy-notes.example/gauge-log", urls)
        self.assertNotIn("https://harbor-daily.example/old-dredging", urls)
        self.assertNotIn("https://canopy-notes.example/old-note", urls)
        self.assertTrue(all("utm_" not in url for url in urls))
        self.assertTrue(all(item.origin == "feed" for item in items))
        self.assertEqual("City", items[0].section)
        self.assertTrue(any(item.section == "Climate" for item in items))

    def test_entry_cap_keeps_the_newest(self) -> None:
        items = items_from_feed(
            (FIXTURES / "harbor-rss.xml").read_bytes(),
            section="City",
            hours=24 * 30,
            max_entries=2,
            max_chars=500,
            now=NOW,
        )
        urls = {item.source_url for item in items}
        self.assertIn("https://harbor-daily.example/library-vote?id=3", urls)
        self.assertNotIn("https://harbor-daily.example/old-dredging", urls)

    def test_hostile_xml_is_rejected(self) -> None:
        with self.assertRaisesRegex(FeedError, "rejected"):
            items_from_feed(
                (FIXTURES / "hostile-feed.xml").read_bytes(),
                section="",
                hours=24,
                max_entries=5,
                max_chars=500,
                now=NOW,
            )

    def test_feed_links_go_through_the_same_link_rule(self) -> None:
        items = items_from_feed(
            (FIXTURES / "harbor-rss.xml").read_bytes(),
            section="City",
            hours=24,
            max_entries=5,
            max_chars=500,
            now=NOW,
        )
        feed = NewsletterFeed(
            synthetic=False,
            edition_date=NOW.date(),
            items=tuple(items),
        )
        url = "https://harbor-daily.example/library-vote?id=3"
        story = {
            "title": "Library budget vote",
            "summary": "The council posted the agenda.",
            "why_it_matters": "The vote is the item in the feed.",
            "key_fact": "Thursday",
            "source_label": "Harbor Daily",
            "source_url": url,
            "reactions": "",
            "context": "",
            "context_source": "",
        }
        payload = {
            "title": "Brief",
            "edition": "Wednesday",
            "date": "2026-11-18",
            "read_time_minutes": 2,
            "opening_note": "One feed item.",
            "why_this_matters": "The library vote is the item in the feed.",
            "facts": ["Library budget vote is on Thursday"],
            "lead_story": story,
            "sections": [{"name": "City", "stories": [story]}],
            "events": [],
        }
        ensure_grounded(parse_edition(payload), feed)
        payload["lead_story"] = dict(story, source_url="https://invented.example/nope")
        payload["sections"] = [{"name": "City", "stories": [payload["lead_story"]]}]
        with self.assertRaises(SynthesisError):
            ensure_grounded(parse_edition(payload), feed)

    def test_mail_and_feed_with_the_same_url_collapse(self) -> None:
        from newsletter_brief.prefilter import dedupe_links

        shared = "https://harbor-daily.example/library-vote"
        mail = NewsletterItem(
            item_id="",
            publication="Harbor Daily",
            topic="Library",
            title="From the inbox",
            excerpt="Mail text",
            source_url=shared,
            origin="mail",
            section="City",
        )
        feed = NewsletterItem(
            item_id="",
            publication="Harbor Daily",
            topic="Library",
            title="From the feed",
            excerpt="Feed text",
            source_url=shared,
            origin="feed",
            section="City",
        )
        kept = dedupe_links([feed, mail])
        self.assertEqual(1, len(kept))
        self.assertEqual("mail", kept[0].origin)
        self.assertEqual("From the inbox", kept[0].title)


if __name__ == "__main__":
    unittest.main()
