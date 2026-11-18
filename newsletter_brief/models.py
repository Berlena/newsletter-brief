"""Small immutable models shared by synthesis, validation and rendering."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class NewsletterItem:
    item_id: str
    publication: str
    topic: str
    title: str
    excerpt: str
    source_url: str
    section: str = ""
    origin: str = "mail"
    published_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class NewsletterFeed:
    synthetic: bool
    edition_date: date
    items: tuple[NewsletterItem, ...]


@dataclass(frozen=True, slots=True)
class Story:
    title: str
    summary: str
    why_it_matters: str
    key_fact: str
    source_label: str
    source_url: str
    reactions: str = ""
    context: str = ""
    context_source: str = ""


@dataclass(frozen=True, slots=True)
class Section:
    name: str
    stories: tuple[Story, ...]


@dataclass(frozen=True, slots=True)
class Event:
    title: str
    when: str
    detail: str
    source_label: str
    source_url: str


@dataclass(frozen=True, slots=True)
class Figure:
    """A market figure taken from a data fetch. The model does not fill this in."""

    figure_id: str
    label: str
    value: str
    source_name: str
    source_url: str
    as_of: str
    available: bool


@dataclass(frozen=True, slots=True)
class ModelNote:
    """One optional sentence about a model. Kept only when its source was provided."""

    model_id: str
    text: str
    source_url: str


@dataclass(frozen=True, slots=True)
class ModelRelease:
    """Facts taken from a public catalog. The summary model does not fill these in."""

    model_id: str
    name: str
    maker: str
    context_length: int | None
    input_per_million: str
    output_per_million: str
    source_urls: tuple[str, ...] = ()
    blurb: str = ""
    open_weights: bool = False
    note: str = ""
    note_source: str = ""


@dataclass(frozen=True, slots=True)
class Brief:
    synthetic: bool
    title: str
    edition: str
    edition_date: date
    read_time_minutes: int
    opening_note: str
    top_lines: tuple[str, ...]
    lead_story: Story
    sections: tuple[Section, ...]
    why_this_matters: str = ""
    events: tuple[Event, ...] = ()
    figures: tuple[Figure, ...] = ()
    public_demo: bool = True
    input_note: str = ""
    model_releases: tuple[ModelRelease, ...] = ()
    model_notes: tuple[ModelNote, ...] = ()
