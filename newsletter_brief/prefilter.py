"""Drop duplicates and boilerplate before any model call. No network."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence

from newsletter_brief.models import NewsletterItem

# Cut the footer only after this much text, so a short note that mentions
# unsubscribing is not thrown away.
_FOOTER_START = 80
_FOOTER_MARKERS = (
    "unsubscribe",
    "manage your preferences",
    "manage preferences",
    "email preferences",
    "view in your browser",
    "view in browser",
    "view this email",
    "you are receiving this",
    "you're receiving this",
    "you’re receiving this",
    "to stop receiving",
    "update your subscription",
    "update subscription preferences",
)
_WORDS = re.compile(r"[a-z0-9]+")


def strip_boilerplate(text: str) -> str:
    """Remove a trailing unsubscribe or view-in-browser block."""

    lowered = text.casefold()
    cut = len(text)
    for marker in _FOOTER_MARKERS:
        index = lowered.find(marker)
        if index >= _FOOTER_START:
            cut = min(cut, index)
    return text[:cut].strip()


def headline_key(title: str) -> str:
    return " ".join(_WORDS.findall(title.casefold()))


def _near_duplicate(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    a = set(left.split())
    b = set(right.split())
    union = a | b
    if not union:
        return False
    return len(a & b) / len(union) >= 0.8


def dedupe_links(items: Sequence[NewsletterItem]) -> list[NewsletterItem]:
    """One item per cleaned URL. A mail item wins over a feed item."""

    chosen: dict[str, NewsletterItem] = {}
    order: list[str] = []
    for item in items:
        url = item.source_url
        if not url:
            continue
        current = chosen.get(url)
        if current is None:
            chosen[url] = item
            order.append(url)
            continue
        if current.origin != "mail" and item.origin == "mail":
            chosen[url] = item
    return [chosen[url] for url in order]


def _clip(item: NewsletterItem, *, max_chars: int) -> NewsletterItem:
    excerpt = strip_boilerplate(item.excerpt)
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars].rstrip()
    if excerpt == item.excerpt:
        return item
    return NewsletterItem(
        item_id=item.item_id,
        publication=item.publication,
        topic=item.topic,
        title=item.title,
        excerpt=excerpt,
        source_url=item.source_url,
        section=item.section,
        origin=item.origin,
        published_at=item.published_at,
    )


def drop_near_duplicate_headlines(items: Sequence[NewsletterItem]) -> list[NewsletterItem]:
    kept: list[NewsletterItem] = []
    keys: list[str] = []
    for item in items:
        key = headline_key(item.title)
        if any(_near_duplicate(key, previous) for previous in keys):
            continue
        kept.append(item)
        keys.append(key)
    return kept


def cap_sections(
    items: Sequence[NewsletterItem], *, max_per_section: int
) -> list[NewsletterItem]:
    """Keep the newest items in each section, up to the cap."""

    grouped: dict[str, list[NewsletterItem]] = defaultdict(list)
    for item in items:
        grouped[item.section].append(item)
    limited: dict[str, set[int]] = {}
    for name, group in grouped.items():
        ordered = sorted(
            enumerate(group),
            key=lambda pair: pair[1].published_at.timestamp() if pair[1].published_at else 0,
            reverse=True,
        )
        limited[name] = {index for index, _item in ordered[:max_per_section]}
    result: list[NewsletterItem] = []
    seen_counts: dict[str, int] = defaultdict(int)
    # Rebuild in original order, skipping items that were not among the newest.
    counters: dict[str, int] = defaultdict(int)
    for item in items:
        index = counters[item.section]
        counters[item.section] += 1
        if index in limited[item.section]:
            result.append(item)
            seen_counts[item.section] += 1
    return result


def finish_prefilter(
    items: Sequence[NewsletterItem],
    *,
    max_chars: int,
    max_per_section: int,
) -> list[NewsletterItem]:
    clipped = [_clip(item, max_chars=max_chars) for item in items]
    unique = drop_near_duplicate_headlines(clipped)
    return cap_sections(unique, max_per_section=max_per_section)
