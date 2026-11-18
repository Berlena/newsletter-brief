"""Local memory of recent headlines, links, and days a brief was already sent."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from newsletter_brief.models import NewsletterItem
from newsletter_brief.prefilter import headline_key


class StateError(RuntimeError):
    """Raised when the state file cannot be trusted. The run stops."""


@dataclass
class Memory:
    seen: list[dict[str, str]]
    sent: list[str]

    def already_sent(self, day: date) -> bool:
        return day.isoformat() in self.sent


def load_memory(path: Path) -> Memory:
    if not path.exists():
        return Memory(seen=[], sent=[])
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError(f"could not read the state file {path.name}") from exc
    if not isinstance(raw, dict):
        raise StateError(f"state file {path.name} is not a table")
    seen_raw = raw.get("seen", [])
    sent_raw = raw.get("sent", [])
    if not isinstance(seen_raw, list) or not isinstance(sent_raw, list):
        raise StateError(f"state file {path.name} is not usable")
    seen: list[dict[str, str]] = []
    for entry in seen_raw:
        if not isinstance(entry, dict):
            continue
        day = str(entry.get("day", ""))
        title = str(entry.get("title", ""))
        url = str(entry.get("url", ""))
        if day and (title or url):
            seen.append({"day": day, "title": title, "url": url})
    sent = [str(item) for item in sent_raw if isinstance(item, str)]
    return Memory(seen=seen, sent=sent)


def _fresh(entries: list[dict[str, str]], *, today: date, days: int) -> list[dict[str, str]]:
    earliest = today - timedelta(days=days)
    kept: list[dict[str, str]] = []
    for entry in entries:
        try:
            day = date.fromisoformat(entry["day"])
        except ValueError:
            continue
        if day >= earliest:
            kept.append(entry)
    return kept


def drop_seen(
    items: list[NewsletterItem],
    memory: Memory,
    *,
    today: date,
    days: int,
) -> list[NewsletterItem]:
    recent = _fresh(memory.seen, today=today, days=days)
    urls = {entry["url"] for entry in recent if entry.get("url")}
    titles = {entry["title"] for entry in recent if entry.get("title")}
    kept: list[NewsletterItem] = []
    for item in items:
        key = headline_key(item.title)
        if item.source_url in urls or (key and key in titles):
            continue
        kept.append(item)
    return kept


def remember(
    memory: Memory,
    items: list[NewsletterItem],
    titles: list[str],
    *,
    today: date,
    days: int,
    sent: bool,
) -> None:
    day = today.isoformat()
    for item in items:
        memory.seen.append(
            {
                "day": day,
                "title": headline_key(item.title),
                "url": item.source_url,
            }
        )
    for title in titles:
        key = headline_key(title)
        if key:
            memory.seen.append({"day": day, "title": key, "url": ""})
    memory.seen = _fresh(memory.seen, today=today, days=days)
    if sent and day not in memory.sent:
        memory.sent.append(day)
    earliest = today - timedelta(days=max(days, 14))
    memory.sent = [
        item
        for item in memory.sent
        if _is_on_or_after(item, earliest)
    ]


def _is_on_or_after(value: str, earliest: date) -> bool:
    try:
        return date.fromisoformat(value) >= earliest
    except ValueError:
        return False


def save_memory(path: Path, memory: Memory) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "seen": memory.seen,
        "sent": memory.sent,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def local_day(moment: datetime) -> date:
    if moment.tzinfo is None:
        moment = moment.astimezone()
    else:
        moment = moment.astimezone()
    return moment.date()
