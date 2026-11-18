"""Read RSS and Atom feeds. HTTPS only, no live calls from the tests."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from xml.etree.ElementTree import Element

from newsletter_brief.http_get import HttpError, read_https
from newsletter_brief.inbox import clean_url, extract_links
from newsletter_brief.models import NewsletterItem

MAX_FEED_BYTES = 1_000_000
FEED_TIMEOUT = 10.0
_ACCEPT = "application/atom+xml, application/rss+xml, application/xml, text/xml;q=0.9"


class FeedError(RuntimeError):
    """Raised when a feed cannot be used. The message does not include the body."""


@dataclass(frozen=True, slots=True)
class FeedRequest:
    url: str
    section: str
    hours: int
    max_entries: int


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _children(node: Element, name: str) -> list[Element]:
    return [child for child in list(node) if _local(child.tag) == name]


def _text(node: Element | None) -> str:
    if node is None:
        return ""
    return " ".join("".join(node.itertext()).split())


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_when(value: str) -> datetime | None:
    text = " ".join(value.split())
    if not text:
        return None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError, OverflowError):
        parsed = None
    if parsed is not None:
        try:
            return _as_utc(parsed)
        except (TypeError, ValueError, OverflowError):
            return None
    iso = text.replace("Z", "+00:00")
    try:
        return _as_utc(datetime.fromisoformat(iso))
    except (TypeError, ValueError, OverflowError):
        return None


def _parse_xml(data: bytes) -> Element:
    if len(data) > MAX_FEED_BYTES:
        raise FeedError("feed is too large")
    try:
        from defusedxml.ElementTree import fromstring
        from defusedxml.common import DefusedXmlException
    except ImportError as exc:
        raise FeedError(
            'reading feeds needs defusedxml. Install it with: python -m pip install -e .'
        ) from exc
    try:
        from xml.etree.ElementTree import ParseError
    except ImportError:  # pragma: no cover
        ParseError = Exception  # type: ignore[misc, assignment]
    try:
        return fromstring(data)
    except (DefusedXmlException, ParseError):
        raise FeedError("feed XML was rejected") from None


def _entry_link(node: Element) -> str:
    for child in _children(node, "link"):
        rel = (child.get("rel") or "alternate").casefold()
        href = (child.get("href") or "").strip()
        if rel == "alternate" and href:
            return href
        text = _text(child)
        if text.startswith("https://") and rel in {"alternate", ""}:
            return text
    for child in _children(node, "link"):
        href = (child.get("href") or "").strip()
        if href:
            return href
        text = _text(child)
        if text:
            return text
    guid = _text(_first(node, "guid"))
    if guid.startswith("https://"):
        return guid
    return ""


def _first(node: Element, name: str) -> Element | None:
    found = _children(node, name)
    return found[0] if found else None


def _entry_html(node: Element) -> str:
    for name in ("encoded", "content", "description", "summary"):
        child = _first(node, name)
        if child is not None and _text(child):
            return "".join(child.itertext())
    return ""


def _entry_when(node: Element) -> datetime | None:
    for name in ("published", "updated", "pubDate", "date"):
        child = _first(node, name)
        if child is None:
            continue
        when = parse_when(_text(child))
        if when is not None:
            return when
    return None


def _within(when: datetime | None, *, now: datetime, hours: int) -> bool:
    if when is None:
        return False
    return when >= now - timedelta(hours=hours)


@dataclass(frozen=True, slots=True)
class _Entry:
    title: str
    link: str
    html: str
    when: datetime | None


def _entries(root: Element) -> tuple[str, list[_Entry]]:
    kind = _local(root.tag)
    if kind == "rss":
        channel = _first(root, "channel")
        if channel is None:
            raise FeedError("feed did not contain a channel")
        publication = _text(_first(channel, "title")) or "Feed"
        nodes = _children(channel, "item")
    elif kind == "feed":
        publication = _text(_first(root, "title")) or "Feed"
        nodes = _children(root, "entry")
    elif kind == "RDF":
        publication = _text(_first(root, "title")) or "Feed"
        nodes = _children(root, "item")
    else:
        raise FeedError("feed was not RSS or Atom")
    entries = [
        _Entry(
            title=_text(_first(node, "title")),
            link=_entry_link(node),
            html=_entry_html(node),
            when=_entry_when(node),
        )
        for node in nodes
    ]
    return publication[:120], entries


def items_from_feed(
    data: bytes,
    *,
    section: str,
    hours: int,
    max_entries: int,
    max_chars: int,
    now: datetime,
) -> list[NewsletterItem]:
    publication, entries = _entries(_parse_xml(data))
    fresh = [entry for entry in entries if _within(entry.when, now=now, hours=hours)]
    fresh.sort(key=lambda entry: entry.when or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    chosen = fresh[:max_entries]
    items: list[NewsletterItem] = []
    for entry in chosen:
        title = entry.title or publication
        links = extract_links(entry.html, entry.link, subject=title, max_chars=max_chars)
        if not links and entry.link:
            cleaned = clean_url(entry.link)
            if cleaned:
                links = ((cleaned, title[:180], title[:max_chars]),)
        for url, link_title, excerpt in links:
            items.append(
                NewsletterItem(
                    item_id="",
                    publication=publication,
                    topic=title[:80],
                    title=(link_title or title)[:180],
                    excerpt=excerpt[:max_chars],
                    source_url=url,
                    section=section,
                    origin="feed",
                    published_at=entry.when,
                )
            )
    return items


def read_feeds(
    requests: Sequence[FeedRequest],
    *,
    max_chars: int,
    now: datetime | None = None,
    get: Callable[[str], bytes] | None = None,
    timeout: float = FEED_TIMEOUT,
) -> list[NewsletterItem]:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    items: list[NewsletterItem] = []
    seen_urls: set[str] = set()
    for request in requests:
        host = urlsplit(request.url).hostname or request.url
        try:
            data = read_https(
                request.url,
                timeout=timeout,
                max_bytes=MAX_FEED_BYTES,
                accept=_ACCEPT,
                get=get,
            )
            parsed = items_from_feed(
                data,
                section=request.section,
                hours=request.hours,
                max_entries=request.max_entries,
                max_chars=max_chars,
                now=moment,
            )
        except (HttpError, FeedError) as exc:
            raise FeedError(f"could not read feed {host}: {exc}") from None
        for item in parsed:
            if item.source_url in seen_urls:
                continue
            seen_urls.add(item.source_url)
            items.append(item)
    return items
