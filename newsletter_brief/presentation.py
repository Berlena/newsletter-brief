"""Shared type and color choices for the page and the email."""

from __future__ import annotations

import re
from html import escape

from newsletter_brief.models import Figure

# Light palette. Wine and lime are the two accents. Pills stay soft and sunset-colored.
# Text on each pair clears WCAG AA.
LIGHT = {
    "paper": "#fffcf6",
    "ink": "#32121f",
    "muted": "#6b5a60",
    "accent": "#4a1028",
    "accent-dark": "#2e0a18",
    "remember-bg": "#f4f0e6",
    "line": "#cabdb8",
    "wine": "#4a1028",
    "lime": "#d0e79b",
    "clay": "#8f513e",
    "warm": "#f4f0e6",
}

# Dark palette. Headings flip to a light rose so they stay readable on a dark ground.
# Lime number chips keep dark wine text in both themes.
DARK = {
    "paper": "#1c1016",
    "ink": "#f6efe8",
    "muted": "#e7c9d2",
    "accent": "#f3d5e0",
    "accent-dark": "#f6efe8",
    "remember-bg": "#2a1a22",
    "line": "#4a3040",
    "wine": "#f3d5e0",
    "lime": "#d0e79b",
    "clay": "#f0c2b4",
    "warm": "#2a1a22",
}

# Sunset pills. The same list repeats when there are more sections than colors.
PILL_COLORS = (
    ("#ecb7aa", "#32121f"),
    ("#dce5ee", "#1e2a44"),
    ("#d8d3e8", "#4a1028"),
    ("#f5d4aa", "#4a1028"),
    ("#dde4d9", "#32121f"),
    ("#f3c7c0", "#4a1028"),
)

FACTS_PILL = ("#d0e79b", "#32121f")
STORY_PILL = ("#4a1028", "#fffcf6")
MARKETS_PILL = ("#dde4d9", "#32121f")
MODELS_PILL = ("#d8d3e8", "#4a1028")

_NUMBER = re.compile(r"^(?:[$€£])?\d[\d,]*(?:\.\d+)?%?$")
_UNIT = {"billion", "million", "trillion"}
_ACRONYM = re.compile(r"^[A-Z]{2,}[A-Z0-9-]*$")


def pill_colors(index: int) -> tuple[str, str]:
    """Background and text for the section at this position. The palette cycles."""

    return PILL_COLORS[index % len(PILL_COLORS)]


def section_anchor(name: str, index: int, used: set[str]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or f"section-{index}"
    base = slug
    extra = 2
    while slug in used:
        slug = f"{base}-{extra}"
        extra += 1
    used.add(slug)
    return slug


def _core(token: str) -> str:
    return token.strip(".,;:!?“”\"'()[]")


def _is_number(token: str) -> bool:
    return _NUMBER.fullmatch(_core(token)) is not None


def _is_unit(token: str) -> bool:
    return _core(token).casefold() in _UNIT


def _is_name(token: str) -> bool:
    """All-caps tokens such as ECB or USDC. Ordinary capitalized words stay plain."""

    core = _core(token)
    return _ACRONYM.fullmatch(core) is not None


def _bold(text: str, *, email: bool) -> str:
    if email:
        return f'<b style="font-weight:600">{text}</b>'
    return f"<b>{text}</b>"


def emphasize(text: str, *, email: bool = False) -> str:
    """Escape text, then bold numbers and names only.

    A number and a following unit such as "1.8 million" stay one phrase so the
    words are still readable as a unit.
    """

    escaped = escape(text)
    tokens = re.split(r"(\s+)", escaped)
    out: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token or token.isspace():
            out.append(token)
            index += 1
            continue
        if (
            _is_number(token)
            and index + 2 < len(tokens)
            and tokens[index + 1].isspace()
            and _is_unit(tokens[index + 2])
        ):
            phrase = token + tokens[index + 1] + tokens[index + 2]
            out.append(_bold(phrase, email=email))
            index += 3
            continue
        if _is_number(token) or _is_name(token):
            out.append(_bold(token, email=email))
        else:
            out.append(token)
        index += 1
    return "".join(out)


def short_figure_label(figure: Figure) -> str:
    if figure.figure_id.startswith("eur-") and "-" in figure.figure_id:
        return "EUR/" + figure.figure_id.split("-", 1)[1].upper()
    return figure.label


def figures_line(figures: tuple[Figure, ...] | list[Figure]) -> str:
    parts = [f"{escape(short_figure_label(figure))} {escape(figure.value)}" for figure in figures]
    return " · ".join(parts)
