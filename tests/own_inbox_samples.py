"""Synthetic newsletters for the personal-run tests. Not a real inbox."""

from __future__ import annotations

import json
from pathlib import Path

from newsletter_brief.figures import ECB_DAILY_URL, COINGECKO_URL

EDITION_DAY = "2026-11-18"
MODEL_NUMBER = "424242"

ECB_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <Cube>
    <Cube time="2026-11-17">
      <Cube currency="USD" rate="1.1000"/>
      <Cube currency="GBP" rate="0.8500"/>
    </Cube>
  </Cube>
</gesmes:Envelope>
"""

# Bitcoin is missing on purpose so that figure is unavailable.
COIN_JSON = json.dumps(
    {"ethereum": {"usd": 2000, "last_updated_at": 1795000000}}
).encode("utf-8")

LETTERS = (
    {
        "name": "Harbor Daily",
        "address": "desk@harbor-daily.example",
        "subject": "Library budget vote is on Thursday",
        "href": "https://harbor-daily.example/library-vote?utm_source=newsletter&utm_medium=email",
        "url": "https://harbor-daily.example/library-vote",
        "link": "Library budget vote",
        "paragraph": "The council votes on the library budget on Thursday.",
    },
    {
        "name": "Canopy Notes",
        "address": "ed@canopy-notes.example",
        "subject": "The river gauge crossed its winter line",
        "href": "https://canopy-notes.example/river-gauge",
        "url": "https://canopy-notes.example/river-gauge",
        "link": "River gauge update",
        "paragraph": "The winter line on the river gauge was crossed.",
    },
    {
        "name": "North Stand",
        "address": "desk@north-stand.example",
        "subject": "Saturday's match moved to the small ground",
        "href": "https://north-stand.example/saturday-ground",
        "url": "https://north-stand.example/saturday-ground",
        "link": "Match moved to the small ground",
        "paragraph": "Saturday's match is at the small ground.",
    },
    {
        "name": "Field Table",
        "address": "desk@field-table.example",
        "subject": "The market adds a winter vegetable stall",
        "href": "https://field-table.example/winter-stall",
        "url": "https://field-table.example/winter-stall",
        "link": "Winter vegetable stall",
        "paragraph": "A winter vegetable stall was added to the market.",
    },
    {
        "name": "Quiet Shelf",
        "address": "desk@quiet-shelf.example",
        "subject": "Three short novels for a long commute",
        "href": "https://quiet-shelf.example/three-novels",
        "url": "https://quiet-shelf.example/three-novels",
        "link": "Three short novels",
        "paragraph": "Three short novels for a long commute.",
    },
)


def eml_bytes(letter: dict[str, str]) -> bytes:
    lines = [
        f"From: {letter['name']} <{letter['address']}>",
        "To: you@example.com",
        f"Subject: {letter['subject']}",
        "Date: Wed, 18 Nov 2026 07:00:00 +0000",
        "MIME-Version: 1.0",
        "Content-Type: text/html; charset=utf-8",
        "",
        "<html><body>",
        f"<p>{letter['paragraph']}</p>",
        f'<p><a href="{letter["href"]}">{letter["link"]}</a></p>',
        "</body></html>",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def write_sample_mail(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for index, letter in enumerate(LETTERS, start=1):
        (folder / f"{index:02d}-{letter['name'].split()[0].lower()}.eml").write_bytes(
            eml_bytes(letter)
        )


def sample_edition() -> dict[str, object]:
    harbor, canopy, stand, field, shelf = LETTERS
    return {
        "title": "A title the code will replace",
        "edition": "Wednesday brief",
        "date": EDITION_DAY,
        "read_time_minutes": 4,
        "opening_note": "Two of the letters are about the city, and the rest can wait.",
        "why_this_matters": (
            "The library vote and the river gauge match the topics you listed, "
            "city services and climate. The match, the stall and the book list "
            "are there if you want them."
        ),
        "facts": [letter["subject"] for letter in LETTERS],
        "lead_story": {
            "title": "The library budget vote is on Thursday",
            "summary": (
                "Harbor Daily says the council votes on the library budget on Thursday. "
                f"{MODEL_NUMBER} is a count written by the model."
            ),
            "why_it_matters": "A library budget decides what stays open.",
            "key_fact": "The vote is Thursday",
            "source_label": "Harbor Daily",
            "source_url": harbor["url"],
            "reactions": "",
            "context": "",
            "context_source": "",
        },
        "sections": [
            {
                "name": "Climate",
                "stories": [
                    {
                        "title": canopy["subject"],
                        "summary": "Canopy Notes says the winter line on the river gauge was crossed.",
                        "why_it_matters": "The gauge is the climate item in today's mail.",
                        "key_fact": "The winter line was crossed",
                        "source_label": "Canopy Notes",
                        "source_url": canopy["url"],
                        "reactions": "",
                        "context": "",
                        "context_source": "",
                    }
                ],
            },
            {
                "name": "Local life",
                "stories": [
                    {
                        "title": stand["subject"],
                        "summary": "North Stand says Saturday's match is at the small ground.",
                        "why_it_matters": "The ground change matters if you were going.",
                        "key_fact": "Small ground on Saturday",
                        "source_label": "North Stand",
                        "source_url": stand["url"],
                        "reactions": "",
                        "context": "",
                        "context_source": "",
                    },
                    {
                        "title": field["subject"],
                        "summary": "Field Table says a winter vegetable stall was added.",
                        "why_it_matters": "It is a small change to the weekly market.",
                        "key_fact": "One new stall",
                        "source_label": "Field Table",
                        "source_url": field["url"],
                        "reactions": "",
                        "context": "",
                        "context_source": "",
                    },
                    {
                        "title": shelf["subject"],
                        "summary": "Quiet Shelf names three short novels.",
                        "why_it_matters": "Useful if the commute is when you read.",
                        "key_fact": "Three novels",
                        "source_label": "Quiet Shelf",
                        "source_url": shelf["url"],
                        "reactions": "",
                        "context": "",
                        "context_source": "",
                    },
                ],
            },
        ],
        "events": [
            {
                "title": "Library budget vote",
                "when": "Thursday",
                "detail": "The council votes on the library budget.",
                "source_label": "Harbor Daily",
                "source_url": harbor["url"],
            },
            {
                "title": "Match at the small ground",
                "when": "Saturday",
                "detail": "The match has moved to the small ground.",
                "source_label": "North Stand",
                "source_url": stand["url"],
            },
        ],
    }


def figure_bytes(url: str) -> bytes:
    if url == ECB_DAILY_URL:
        return ECB_XML
    if url == COINGECKO_URL:
        return COIN_JSON
    raise OSError(f"unexpected figure URL: {url}")


SAMPLE_CONFIG = """
title = "Your Morning Brief"

[mailbox]
host = "imap.example"
port = 993
user = "you@example.com"
folder = "INBOX"
hours = 24

[senders]
allow = [
  "harbor-daily.example",
  "canopy-notes.example",
  "north-stand.example",
  "field-table.example",
  "quiet-shelf.example",
]

[interests]
topics = ["city services", "climate"]

[figures]
show = ["eur-usd", "eur-gbp", "btc-usd", "eth-usd"]

[output]
path = "brief.html"

[delivery]
enabled = false
"""
