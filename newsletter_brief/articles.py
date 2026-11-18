"""Fetch a few linked articles. Off unless the config turns it on."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from html.parser import HTMLParser

from newsletter_brief.http_get import HttpError, read_https
from newsletter_brief.inbox import clean_url
from newsletter_brief.models import NewsletterItem
from newsletter_brief.prefilter import strip_boilerplate

_ACCEPT = "text/html, application/xhtml+xml;q=0.9"


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignore = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self._ignore += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._ignore:
            self._ignore -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignore:
            self.parts.append(data)


def article_text(html: bytes, *, max_chars: int) -> str:
    parser = _Text()
    parser.feed(html.decode("utf-8", errors="replace"))
    parser.close()
    visible = strip_boilerplate(" ".join("".join(parser.parts).split()))
    return visible[:max_chars]


def fetch_articles(
    items: Sequence[NewsletterItem],
    *,
    max_articles: int,
    timeout: float,
    max_bytes: int,
    max_chars: int,
    get: Callable[[str], bytes] | None = None,
) -> list[NewsletterItem]:
    """Replace excerpts with article text for the first N https links."""

    fetched = 0
    seen: set[str] = set()
    result: list[NewsletterItem] = []
    for item in items:
        url = clean_url(item.source_url) or ""
        if not url or url in seen or fetched >= max_articles:
            result.append(item)
            continue
        seen.add(url)
        try:
            body = read_https(
                url,
                timeout=timeout,
                max_bytes=max_bytes,
                accept=_ACCEPT,
                get=get,
            )
        except HttpError:
            result.append(item)
            continue
        text = article_text(body, max_chars=max_chars)
        fetched += 1
        if not text:
            result.append(item)
            continue
        result.append(replace(item, source_url=url, excerpt=text))
    return result
