"""Optional Wikipedia summaries for card context. Off unless the config turns it on."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from urllib.parse import quote

from newsletter_brief.http_get import HttpError, read_https
from newsletter_brief.models import NewsletterItem

SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/"
_ACCEPT = "application/json"
_MAX_EXTRACT = 600
_SKIP = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "of",
    "for",
    "in",
    "on",
    "to",
    "from",
    "with",
    "by",
    "at",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "today",
    "tomorrow",
    "yesterday",
}
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9&.'-]*")


@dataclass(frozen=True, slots=True)
class ContextSource:
    url: str
    title: str
    extract: str

    def as_dict(self) -> dict[str, str]:
        return {"url": self.url, "title": self.title, "extract": self.extract}


def names_from_items(items: Sequence[NewsletterItem]) -> list[str]:
    """Capitalized names from publications and titles. Order is stable."""

    found: list[str] = []
    seen: set[str] = set()
    for item in items:
        for raw in (item.publication, item.title):
            for name in _name_runs(raw):
                key = name.casefold()
                if key in seen:
                    continue
                seen.add(key)
                found.append(name)
    return found


def _name_runs(text: str) -> list[str]:
    runs: list[str] = []
    current: list[str] = []
    for token in _TOKEN.findall(text):
        if token[:1].isupper() and token.casefold() not in _SKIP:
            current.append(token)
            continue
        runs.extend(_emit(current))
        current = []
    runs.extend(_emit(current))
    return runs


def _emit(tokens: list[str]) -> list[str]:
    if len(tokens) >= 2:
        return [" ".join(tokens)]
    if len(tokens) == 1 and len(tokens[0]) >= 4:
        return tokens
    return []


def parse_summary(data: bytes) -> tuple[str, str] | None:
    try:
        raw = json.loads(data)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict) or raw.get("type") == "disambiguation":
        return None
    extract = " ".join(str(raw.get("extract") or "").split())
    if not extract:
        return None
    urls = raw.get("content_urls")
    desktop = urls.get("desktop") if isinstance(urls, dict) else None
    page = str(desktop.get("page") or "") if isinstance(desktop, dict) else ""
    if not page.startswith("https://"):
        return None
    return page, extract[:_MAX_EXTRACT]


def lookup_summaries(
    names: Sequence[str],
    *,
    timeout: float,
    max_lookups: int,
    get: Callable[[str], bytes] | None = None,
) -> tuple[ContextSource, ...]:
    """Fetch up to max_lookups Wikipedia summaries. Failures are skipped."""

    found: list[ContextSource] = []
    seen: set[str] = set()
    calls = 0
    for name in names:
        if calls >= max_lookups:
            break
        cleaned = " ".join(name.split())
        key = cleaned.casefold()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        target = SUMMARY_URL + quote(cleaned.replace(" ", "_"), safe="")
        calls += 1
        try:
            data = read_https(
                target,
                timeout=timeout,
                max_bytes=200_000,
                accept=_ACCEPT,
                get=get,
            )
        except HttpError:
            continue
        parsed = parse_summary(data)
        if parsed is None:
            continue
        page, extract = parsed
        found.append(ContextSource(url=page, title=cleaned, extract=extract))
    return tuple(found)
