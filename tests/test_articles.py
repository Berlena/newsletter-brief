from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from newsletter_brief.articles import fetch_articles
from newsletter_brief.http_get import HttpError, read_https
from newsletter_brief.models import NewsletterItem

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 18, 8, 0, tzinfo=timezone.utc)


def _item(url: str) -> NewsletterItem:
    return NewsletterItem(
        item_id="m1-l1",
        publication="Harbor Daily",
        topic="Library",
        title="Library budget vote",
        excerpt="Short mail excerpt.",
        source_url=url,
        published_at=NOW,
    )


class ArticleTests(unittest.TestCase):
    def test_fetch_is_https_only_capped_and_strips_tracking(self) -> None:
        seen: list[str] = []

        def get(url: str) -> bytes:
            seen.append(url)
            return (FIXTURES / "article.html").read_bytes()

        items = fetch_articles(
            [
                _item("https://harbor-daily.example/library-vote?utm_source=nl"),
                _item("https://harbor-daily.example/minutes"),
                _item("http://harbor-daily.example/insecure"),
            ],
            max_articles=1,
            timeout=8,
            max_bytes=100_000,
            max_chars=500,
            get=get,
        )
        self.assertEqual(["https://harbor-daily.example/library-vote"], seen)
        self.assertIn("full vote text", items[0].excerpt)
        self.assertNotIn("Unsubscribe", items[0].excerpt)
        self.assertEqual("Short mail excerpt.", items[1].excerpt)
        self.assertTrue(items[2].source_url.startswith("http://"))

    def test_oversize_response_is_rejected(self) -> None:
        def get(url: str) -> bytes:
            return b"x" * 50

        with self.assertRaisesRegex(HttpError, "too large"):
            read_https(
                "https://harbor-daily.example/library-vote",
                timeout=5,
                max_bytes=20,
                accept="text/html",
                get=get,
            )

    def test_http_is_refused_before_a_connection(self) -> None:
        with patch("newsletter_brief.http_get.urllib.request.urlopen") as urlopen:
            with self.assertRaisesRegex(HttpError, "https"):
                read_https(
                    "http://harbor-daily.example/feed.xml",
                    timeout=5,
                    max_bytes=1000,
                    accept="text/html",
                )
        urlopen.assert_not_called()

    def test_live_reader_passes_the_timeout(self) -> None:
        captured: dict[str, object] = {}

        class Response:
            def __enter__(self) -> "Response":
                return self

            def __exit__(self, *args: object) -> bool:
                return False

            def geturl(self) -> str:
                return "https://harbor-daily.example/library-vote"

            def read(self, size: int) -> bytes:
                return b"<p>hello</p>"

            status = 200

        class Opener:
            def open(self, request: object, timeout: float) -> Response:
                captured["timeout"] = timeout
                captured["url"] = getattr(request, "full_url", "")
                return Response()

        with patch("newsletter_brief.http_get.urllib.request.build_opener", return_value=Opener()):
            data = read_https(
                "https://harbor-daily.example/library-vote",
                timeout=8,
                max_bytes=1000,
                accept="text/html",
            )
        self.assertEqual(b"<p>hello</p>", data)
        self.assertEqual(8, captured["timeout"])
        self.assertEqual("https://harbor-daily.example/library-vote", captured["url"])


if __name__ == "__main__":
    unittest.main()
