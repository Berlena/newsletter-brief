"""Strict validation and the public demo's JSON Schema."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from newsletter_brief.models import Brief, Event, ModelNote, Section, Story


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


def _story_fields(
    obj: Mapping[str, Any],
    path: str,
    *,
    reactions: str = "",
    context: str = "",
    context_source: str = "",
) -> Story:
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
        context=context,
        context_source=context_source,
    )


def _context_pair(obj: Mapping[str, Any], path: str) -> tuple[str, str]:
    context = _optional_text(obj["context"], f"{path}.context", maximum=220)
    if len(context.split()) > 25:
        raise SchemaError(f"{path}.context must be at most about 25 words")
    source = obj["context_source"]
    if not isinstance(source, str):
        raise SchemaError(f"{path}.context_source must be a string")
    source = source.strip()
    if context and not source:
        raise SchemaError(f"{path}.context needs a context_source URL")
    if source and not context:
        raise SchemaError(f"{path}.context_source needs context text")
    if source:
        source = _https_url(source, f"{path}.context_source")
    return context, source


def _edition_story(value: Any, path: str) -> Story:
    obj = _object(value, path, _STORY_KEYS | {"reactions", "context", "context_source"})
    context, context_source = _context_pair(obj, path)
    return _story_fields(
        obj,
        path,
        reactions=_optional_text(obj["reactions"], f"{path}.reactions", maximum=300),
        context=context,
        context_source=context_source,
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


def _model_note(value: Any, path: str) -> ModelNote | None:
    """A note with a bad URL is kept unsourced so the caller can drop it."""

    obj = _object(value, path, {"model_id", "note", "source_url"})
    model_id = _text(obj["model_id"], f"{path}.model_id", maximum=200)
    note = _optional_text(obj["note"], f"{path}.note", maximum=280)
    source = obj["source_url"]
    if not isinstance(source, str):
        raise SchemaError(f"{path}.source_url must be a string")
    source = source.strip()
    if not note:
        return None
    if source:
        try:
            source = _https_url(source, f"{path}.source_url")
        except SchemaError:
            source = ""
    return ModelNote(model_id=model_id, text=note, source_url=source)


def _model_notes(value: Any) -> tuple[ModelNote, ...]:
    if not isinstance(value, list):
        raise SchemaError("brief.model_notes must be an array")
    if len(value) > 6:
        raise SchemaError("brief.model_notes must contain at most 6 notes")
    notes: list[ModelNote] = []
    for index, item in enumerate(value):
        note = _model_note(item, f"brief.model_notes[{index}]")
        if note is not None:
            notes.append(note)
    return tuple(notes)


def parse_edition(
    value: Any,
    *,
    fact_count: int = 5,
    max_cards: int = 3,
    expect_notes: bool = False,
) -> Brief:
    """Validate a personal-inbox brief. This path is not the synthetic demo."""

    if not isinstance(value, dict):
        raise SchemaError("brief must be an object")
    raw_notes = value.get("model_notes") if expect_notes else None
    payload = dict(value)
    payload.pop("model_notes", None)
    obj = _object(payload, "brief", _EDITION_KEYS)
    model_notes = _model_notes(raw_notes) if expect_notes else ()
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
    if not 1 <= len(raw_sections) <= 12:
        raise SchemaError("brief.sections must contain 1 to 12 sections")

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
        model_notes=model_notes,
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
_CONTEXT_RULE = (
    "Optional. One plain line, about 25 words: who a lesser-known company or person is and why they matter, "
    "or one useful perspective fact that is not in the newsletter text. "
    "Empty unless a provided source supports it. Not trivia."
)
_CONTEXT_SOURCE_RULE = (
    "HTTPS URL of the provided source for context: a fetched article, another item in this edition, "
    "or a lookup. Empty when context is empty."
)


def _edition_story_schema() -> dict[str, Any]:
    properties = {key: dict(value) for key, value in _STORY_SCHEMA["properties"].items()}
    properties["title"]["description"] = _HEADLINE_RULE
    properties["why_it_matters"]["description"] = _WHY_LINE_RULE
    properties["reactions"] = {"type": "string", "maxLength": 300}
    properties["context"] = {"type": "string", "maxLength": 220, "description": _CONTEXT_RULE}
    properties["context_source"] = {
        "type": "string",
        "maxLength": 500,
        "description": _CONTEXT_SOURCE_RULE,
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": sorted(_STORY_KEYS | {"reactions", "context", "context_source"}),
    }


def build_edition_schema(
    *,
    fact_count: int = 5,
    max_cards: int = 3,
    include_notes: bool = False,
) -> dict[str, Any]:
    """Personal-run schema. There is no figures field: code fills that box."""

    story = _edition_story_schema()
    properties: dict[str, Any] = {
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
            "maxItems": 12,
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
    }
    required = set(_EDITION_KEYS)
    if include_notes:
        properties["model_notes"] = {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "model_id": {"type": "string", "maxLength": 200},
                    "note": {"type": "string", "maxLength": 280},
                    "source_url": {"type": "string", "maxLength": 500},
                },
                "required": ["model_id", "note", "source_url"],
            },
        }
        required.add("model_notes")
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": sorted(required),
    }


# Defaults: five short facts, at most three cards in a section.
EDITION_JSON_SCHEMA: dict[str, Any] = build_edition_schema()
