"""Strict validation and the public demo's JSON Schema."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from newsletter_brief.models import Brief, Event, Section, Story


class SchemaError(ValueError):
    """Raised when structured synthesis does not match the public schema."""


_STORY_KEYS = {
    "title",
    "summary",
    "why_it_matters",
    "key_fact",
    "source_label",
    "source_url",
}
_SECTION_KEYS = {"name", "stories"}
_BRIEF_KEYS = {
    "synthetic",
    "title",
    "edition",
    "date",
    "read_time_minutes",
    "opening_note",
    "top_lines",
    "lead_story",
    "sections",
}


def _object(value: Any, path: str, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise SchemaError(f"{path} must be an object")
    missing = keys - value.keys()
    extra = value.keys() - keys
    if missing:
        raise SchemaError(f"{path} is missing: {', '.join(sorted(missing))}")
    if extra:
        raise SchemaError(f"{path} has unexpected fields: {', '.join(sorted(extra))}")
    return value


def _text(value: Any, path: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise SchemaError(f"{path} must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise SchemaError(f"{path} must not be empty")
    if len(cleaned) > maximum:
        raise SchemaError(f"{path} must be at most {maximum} characters")
    return cleaned


def _https_url(value: Any, path: str) -> str:
    url = _text(value, path, maximum=500)
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise SchemaError(f"{path} must be an absolute HTTPS URL")
    if parsed.username or parsed.password:
        raise SchemaError(f"{path} must not contain credentials")
    return url


def _story(value: Any, path: str) -> Story:
    obj = _object(value, path, _STORY_KEYS)
    return _story_fields(obj, path)


def _optional_text(value: Any, path: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise SchemaError(f"{path} must be a string")
    cleaned = value.strip()
    if len(cleaned) > maximum:
        raise SchemaError(f"{path} must be at most {maximum} characters")
    return cleaned


def _story_fields(obj: Mapping[str, Any], path: str, *, reactions: str = "") -> Story:
    return Story(
        title=_text(obj["title"], f"{path}.title", maximum=140),
        summary=_text(obj["summary"], f"{path}.summary", maximum=420),
        why_it_matters=_text(
            obj["why_it_matters"], f"{path}.why_it_matters", maximum=300
        ),
        key_fact=_text(obj["key_fact"], f"{path}.key_fact", maximum=160),
        source_label=_text(obj["source_label"], f"{path}.source_label", maximum=140),
        source_url=_https_url(obj["source_url"], f"{path}.source_url"),
        reactions=reactions,
    )


def _edition_story(value: Any, path: str) -> Story:
    obj = _object(value, path, _STORY_KEYS | {"reactions"})
    return _story_fields(
        obj,
        path,
        reactions=_optional_text(obj["reactions"], f"{path}.reactions", maximum=300),
    )


def parse_brief(value: Any) -> Brief:
    """Validate untrusted structured data and return an immutable Brief."""

    obj = _object(value, "brief", _BRIEF_KEYS)
    if obj["synthetic"] is not True:
        raise SchemaError("brief.synthetic must be true for this public demo")

    raw_date = _text(obj["date"], "brief.date", maximum=10)
    try:
        edition_date = date.fromisoformat(raw_date)
    except ValueError as exc:
        raise SchemaError("brief.date must use YYYY-MM-DD") from exc

    read_time = obj["read_time_minutes"]
    if isinstance(read_time, bool) or not isinstance(read_time, int):
        raise SchemaError("brief.read_time_minutes must be an integer")
    if not 1 <= read_time <= 30:
        raise SchemaError("brief.read_time_minutes must be between 1 and 30")

    raw_top_lines = obj["top_lines"]
    if not isinstance(raw_top_lines, list):
        raise SchemaError("brief.top_lines must be an array")
    if not 3 <= len(raw_top_lines) <= 5:
        raise SchemaError("brief.top_lines must contain 3 to 5 items")
    top_lines = tuple(
        _text(line, f"brief.top_lines[{index}]", maximum=120)
        for index, line in enumerate(raw_top_lines)
    )

    raw_sections = obj["sections"]
    if not isinstance(raw_sections, list):
        raise SchemaError("brief.sections must be an array")
    if not 1 <= len(raw_sections) <= 6:
        raise SchemaError("brief.sections must contain 1 to 6 sections")

    sections: list[Section] = []
    section_names: set[str] = set()
    for section_index, raw_section in enumerate(raw_sections):
        section_path = f"brief.sections[{section_index}]"
        section_obj = _object(raw_section, section_path, _SECTION_KEYS)
        name = _text(section_obj["name"], f"{section_path}.name", maximum=70)
        normalized_name = name.casefold()
        if normalized_name in section_names:
            raise SchemaError(f"{section_path}.name must be unique")
        section_names.add(normalized_name)

        raw_stories = section_obj["stories"]
        if not isinstance(raw_stories, list):
            raise SchemaError(f"{section_path}.stories must be an array")
        if not 1 <= len(raw_stories) <= 3:
            raise SchemaError(f"{section_path}.stories must contain 1 to 3 stories")
        stories = tuple(
            _story(story, f"{section_path}.stories[{story_index}]")
            for story_index, story in enumerate(raw_stories)
        )
        sections.append(Section(name=name, stories=stories))

    return Brief(
        synthetic=True,
        title=_text(obj["title"], "brief.title", maximum=80),
        edition=_text(obj["edition"], "brief.edition", maximum=80),
        edition_date=edition_date,
        read_time_minutes=read_time,
        opening_note=_text(obj["opening_note"], "brief.opening_note", maximum=360),
        top_lines=top_lines,
        lead_story=_story(obj["lead_story"], "brief.lead_story"),
        sections=tuple(sections),
        public_demo=True,
    )


def load_brief(path: Path) -> Brief:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SchemaError(f"{path} is not valid JSON: {exc.msg}") from exc
    return parse_brief(value)


_STORY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string", "maxLength": 140},
        "summary": {"type": "string", "maxLength": 420},
        "why_it_matters": {"type": "string", "maxLength": 300},
        "key_fact": {"type": "string", "maxLength": 160},
        "source_label": {"type": "string", "maxLength": 140},
        "source_url": {"type": "string", "maxLength": 500},
    },
    "required": sorted(_STORY_KEYS),
}

BRIEF_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "synthetic": {"type": "boolean", "const": True},
        "title": {"type": "string", "maxLength": 80},
        "edition": {"type": "string", "maxLength": 80},
        "date": {"type": "string", "maxLength": 10},
        "read_time_minutes": {
            "type": "integer",
            "minimum": 1,
            "maximum": 30,
        },
        "opening_note": {"type": "string", "maxLength": 360},
        "top_lines": {
            "type": "array",
            "minItems": 3,
            "maxItems": 5,
            "items": {"type": "string", "maxLength": 120},
        },
        "lead_story": _STORY_SCHEMA,
        "sections": {
            "type": "array",
            "minItems": 1,
            "maxItems": 6,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "maxLength": 70},
                    "stories": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 3,
                        "items": _STORY_SCHEMA,
                    },
                },
                "required": sorted(_SECTION_KEYS),
            },
        },
    },
    "required": sorted(_BRIEF_KEYS),
}


_EVENT_KEYS = {"title", "when", "detail", "source_label", "source_url"}
_EDITION_KEYS = {
    "title",
    "edition",
    "date",
    "read_time_minutes",
    "opening_note",
    "why_this_matters",
    "facts",
    "lead_story",
    "sections",
    "events",
}


def _event(value: Any, path: str) -> Event:
    obj = _object(value, path, _EVENT_KEYS)
    return Event(
        title=_text(obj["title"], f"{path}.title", maximum=140),
        when=_text(obj["when"], f"{path}.when", maximum=80),
        detail=_text(obj["detail"], f"{path}.detail", maximum=300),
        source_label=_text(obj["source_label"], f"{path}.source_label", maximum=140),
        source_url=_https_url(obj["source_url"], f"{path}.source_url"),
    )


def parse_edition(value: Any, *, fact_count: int = 5, max_cards: int = 3) -> Brief:
    """Validate a personal-inbox brief. This path is not the synthetic demo."""

    obj = _object(value, "brief", _EDITION_KEYS)
    raw_date = _text(obj["date"], "brief.date", maximum=10)
    try:
        edition_date = date.fromisoformat(raw_date)
    except ValueError as exc:
        raise SchemaError("brief.date must use YYYY-MM-DD") from exc

    read_time = obj["read_time_minutes"]
    if isinstance(read_time, bool) or not isinstance(read_time, int):
        raise SchemaError("brief.read_time_minutes must be an integer")
    if not 1 <= read_time <= 30:
        raise SchemaError("brief.read_time_minutes must be between 1 and 30")

    raw_facts = obj["facts"]
    if not isinstance(raw_facts, list):
        raise SchemaError("brief.facts must be an array")
    if not 1 <= len(raw_facts) <= fact_count:
        raise SchemaError(f"brief.facts must contain 1 to {fact_count} items")
    top_lines = tuple(
        _text(line, f"brief.facts[{index}]", maximum=120)
        for index, line in enumerate(raw_facts)
    )

    raw_sections = obj["sections"]
    if not isinstance(raw_sections, list):
        raise SchemaError("brief.sections must be an array")
    if not 1 <= len(raw_sections) <= 6:
        raise SchemaError("brief.sections must contain 1 to 6 sections")

    sections: list[Section] = []
    section_names: set[str] = set()
    for section_index, raw_section in enumerate(raw_sections):
        section_path = f"brief.sections[{section_index}]"
        section_obj = _object(raw_section, section_path, _SECTION_KEYS)
        name = _text(section_obj["name"], f"{section_path}.name", maximum=70)
        normalized_name = name.casefold()
        if normalized_name in section_names:
            raise SchemaError(f"{section_path}.name must be unique")
        section_names.add(normalized_name)
        raw_stories = section_obj["stories"]
        if not isinstance(raw_stories, list):
            raise SchemaError(f"{section_path}.stories must be an array")
        if not 1 <= len(raw_stories) <= max_cards:
            raise SchemaError(
                f"{section_path}.stories must contain 1 to {max_cards} stories"
            )
        stories = tuple(
            _edition_story(story, f"{section_path}.stories[{story_index}]")
            for story_index, story in enumerate(raw_stories)
        )
        sections.append(Section(name=name, stories=stories))

    raw_events = obj["events"]
    if not isinstance(raw_events, list):
        raise SchemaError("brief.events must be an array")
    if len(raw_events) > 8:
        raise SchemaError("brief.events must contain at most 8 events")
    events = tuple(
        _event(event, f"brief.events[{index}]") for index, event in enumerate(raw_events)
    )

    return Brief(
        synthetic=False,
        title=_text(obj["title"], "brief.title", maximum=80),
        edition=_text(obj["edition"], "brief.edition", maximum=80),
        edition_date=edition_date,
        read_time_minutes=read_time,
        opening_note=_text(obj["opening_note"], "brief.opening_note", maximum=360),
        why_this_matters=_text(
            obj["why_this_matters"], "brief.why_this_matters", maximum=400
        ),
        top_lines=top_lines,
        lead_story=_edition_story(obj["lead_story"], "brief.lead_story"),
        sections=tuple(sections),
        events=events,
        public_demo=False,
    )


_EVENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string", "maxLength": 140},
        "when": {"type": "string", "maxLength": 80},
        "detail": {"type": "string", "maxLength": 300},
        "source_label": {"type": "string", "maxLength": 140},
        "source_url": {"type": "string", "maxLength": 500},
    },
    "required": sorted(_EVENT_KEYS),
}

_HEADLINE_RULE = (
    "A plain, complete statement of who did what, with the key number if there is one. "
    "About 15 words. Everyday words. No teasers, jargon, puns, clickbait, or vague three-word phrases."
)
_WHY_LINE_RULE = "One line, in plain words, saying why it matters."


def _edition_story_schema() -> dict[str, Any]:
    properties = {key: dict(value) for key, value in _STORY_SCHEMA["properties"].items()}
    properties["title"]["description"] = _HEADLINE_RULE
    properties["why_it_matters"]["description"] = _WHY_LINE_RULE
    properties["reactions"] = {"type": "string", "maxLength": 300}
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": sorted(_STORY_KEYS | {"reactions"}),
    }


def build_edition_schema(*, fact_count: int = 5, max_cards: int = 3) -> dict[str, Any]:
    """Personal-run schema. There is no figures field: code fills that box."""

    story = _edition_story_schema()
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string", "maxLength": 80},
            "edition": {"type": "string", "maxLength": 80},
            "date": {"type": "string", "maxLength": 10},
            "read_time_minutes": {"type": "integer", "minimum": 1, "maximum": 30},
            "opening_note": {"type": "string", "maxLength": 360},
            "why_this_matters": {"type": "string", "maxLength": 400},
            "facts": {
                "type": "array",
                "minItems": 1,
                "maxItems": fact_count,
                "items": {
                    "type": "string",
                    "maxLength": 120,
                    "description": _HEADLINE_RULE,
                },
            },
            "lead_story": story,
            "sections": {
                "type": "array",
                "minItems": 1,
                "maxItems": 6,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string", "maxLength": 70},
                        "stories": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": max_cards,
                            "items": story,
                        },
                    },
                    "required": sorted(_SECTION_KEYS),
                },
            },
            "events": {
                "type": "array",
                "minItems": 0,
                "maxItems": 8,
                "items": _EVENT_SCHEMA,
            },
        },
        "required": sorted(_EDITION_KEYS),
    }


# Defaults: five short facts, at most three cards in a section.
EDITION_JSON_SCHEMA: dict[str, Any] = build_edition_schema()
