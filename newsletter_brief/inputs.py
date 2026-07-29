"""Load the deliberately synthetic newsletter feed used by the public demo."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from newsletter_brief.models import NewsletterFeed, NewsletterItem


class InputError(ValueError):
    """Raised when newsletter inputs are malformed or are not marked synthetic."""


_FEED_KEYS = {"synthetic", "edition_date", "items"}
_ITEM_KEYS = {"id", "publication", "topic", "title", "excerpt", "source_url"}


def _text(value: Any, path: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise InputError(f"{path} must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise InputError(f"{path} must not be empty")
    if len(cleaned) > maximum:
        raise InputError(f"{path} must be at most {maximum} characters")
    return cleaned


def _exact_object(value: Any, path: str, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InputError(f"{path} must be an object")
    missing = keys - value.keys()
    extra = value.keys() - keys
    if missing:
        raise InputError(f"{path} is missing: {', '.join(sorted(missing))}")
    if extra:
        raise InputError(f"{path} has unexpected fields: {', '.join(sorted(extra))}")
    return value


def parse_feed(value: Any) -> NewsletterFeed:
    obj = _exact_object(value, "feed", _FEED_KEYS)
    if obj["synthetic"] is not True:
        raise InputError(
            "feed.synthetic must be true; real newsletter data is excluded"
        )

    raw_date = _text(obj["edition_date"], "feed.edition_date", 10)
    try:
        edition_date = date.fromisoformat(raw_date)
    except ValueError as exc:
        raise InputError("feed.edition_date must use YYYY-MM-DD") from exc

    if not isinstance(obj["items"], list) or not obj["items"]:
        raise InputError("feed.items must be a non-empty array")
    if len(obj["items"]) > 20:
        raise InputError("feed.items must contain at most 20 items")

    seen_ids: set[str] = set()
    items: list[NewsletterItem] = []
    for index, raw_item in enumerate(obj["items"]):
        path = f"feed.items[{index}]"
        item = _exact_object(raw_item, path, _ITEM_KEYS)
        item_id = _text(item["id"], f"{path}.id", 80)
        if item_id in seen_ids:
            raise InputError(f"{path}.id must be unique")
        seen_ids.add(item_id)

        source_url = _text(item["source_url"], f"{path}.source_url", 500)
        parsed_url = urlsplit(source_url)
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise InputError(f"{path}.source_url must be an absolute HTTPS URL")
        if parsed_url.username or parsed_url.password:
            raise InputError(f"{path}.source_url must not contain credentials")

        items.append(
            NewsletterItem(
                item_id=item_id,
                publication=_text(item["publication"], f"{path}.publication", 120),
                topic=_text(item["topic"], f"{path}.topic", 80),
                title=_text(item["title"], f"{path}.title", 180),
                excerpt=_text(item["excerpt"], f"{path}.excerpt", 900),
                source_url=source_url,
            )
        )

    return NewsletterFeed(synthetic=True, edition_date=edition_date, items=tuple(items))


def load_feed(path: Path) -> NewsletterFeed:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InputError(f"{path} is not valid JSON: {exc.msg}") from exc
    return parse_feed(value)


def feed_as_dict(feed: NewsletterFeed) -> dict[str, Any]:
    return {
        "synthetic": feed.synthetic,
        "edition_date": feed.edition_date.isoformat(),
        "items": [
            {
                "id": item.item_id,
                "publication": item.publication,
                "topic": item.topic,
                "title": item.title,
                "excerpt": item.excerpt,
                "source_url": item.source_url,
            }
            for item in feed.items
        ],
    }
