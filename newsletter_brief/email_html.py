"""Email-safe brief. Tables and inline CSS, with a compact markets fallback.

Apple Mail honors details/summary, so the figures line opens the full grid.
Gmail removes details and summary. The line that would have been the control
is hidden inline, and a normal one-line summary stays visible. Nothing looks
like a toggle that does not work.
"""

from __future__ import annotations

from html import escape
from urllib.parse import urlsplit

from newsletter_brief.model_mania import ARTIFICIAL_ANALYSIS_URL, LMARENA_URL
from newsletter_brief.models import Brief, Figure, ModelRelease, Story
from newsletter_brief.presentation import (
    FACTS_PILL,
    MARKETS_PILL,
    MODELS_PILL,
    STORY_PILL,
    emphasize,
    figures_line,
    pill_colors,
    section_anchor,
)
from newsletter_brief.renderer import _EXAMPLE_FIGURES

_FONT = "Inter,Helvetica,Arial,sans-serif"
_PAPER = "#fffcf6"
_INK = "#32121f"
_MUTED = "#6b5a60"
_WINE = "#4a1028"
_LIME = "#d0e79b"
_CLAY = "#8f513e"
_LINE = "#cabdb8"
_WARM = "#f4f0e6"

_HEAD_CSS = """
body, table, td, a, p, li, h1, h2, h3 { -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }
table, td { mso-table-lspace: 0pt; mso-table-rspace: 0pt; }
body { margin: 0; padding: 0; background: #fffcf6; }
a { color: #8f513e; }
details > summary { cursor: pointer; }
details.markets-details > summary .sum-label { display: inline !important; }
details.markets-details + .markets-compact { display: none !important; }
details.markets-details[open] .markets-full {
  display: block !important;
  max-height: none !important;
  overflow: visible !important;
}
@media only screen and (max-width: 620px) {
  .wrapper { width: 100% !important; }
  .pad { padding-left: 20px !important; padding-right: 20px !important; }
}
@media (prefers-color-scheme: dark) {
  body, .paper { background: #1c1016 !important; }
  .ink, .ink p, .ink td, .ink h1, .ink h2, .ink h3, .ink li { color: #f6efe8 !important; }
  .wine { color: #f3d5e0 !important; }
  .muted { color: #e7c9d2 !important; }
  .num { background: #d0e79b !important; color: #4a1028 !important; }
  .tint { background: #2a1a22 !important; }
}
"""


def _date_label(brief: Brief) -> str:
    day = brief.edition_date
    return f"{day:%A} {day.day} {day:%B %Y}"


def _pill(label: str, href: str, background: str, foreground: str) -> str:
    return (
        f'<a href="#{href}" style="display:inline-block;margin:0 6px 6px 0;padding:6px 10px;'
        f"border-radius:999px;background:{background};color:{foreground};"
        f"font-family:{_FONT};font-size:13px;font-weight:600;line-height:1.3;"
        f'text-decoration:none;">{escape(label)}</a>'
    )


def _gap(height: int) -> str:
    return (
        f'<div style="height:{height}px;line-height:{height}px;font-size:1px;">&nbsp;</div>'
    )


def _context(story: Story) -> str:
    if not story.context:
        return ""
    link = ""
    if story.context_source:
        url = escape(story.context_source, quote=True)
        host = escape(urlsplit(story.context_source).hostname or "source")
        link = f' <a href="{url}" style="color:{_CLAY};text-decoration:underline;">{host}</a>'
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        "<tr><td class=\"tint\" style=\"padding:10px 12px;background:#f4f0e6;"
        f"font-family:{_FONT};font-size:14px;line-height:1.45;color:{_INK};\">"
        f'<b style="font-weight:600;color:{_WINE};">Context.</b> '
        f"{emphasize(story.context, email=True)}{link}"
        "</td></tr></table>"
    )


def _reactions(story: Story) -> str:
    if not story.reactions:
        return ""
    return (
        f'<p style="margin:8px 0 0 0;font-family:{_FONT};font-size:16px;line-height:1.5;color:{_INK};">'
        f'<b style="font-weight:600;color:{_CLAY};">Reactions.</b> '
        f"{emphasize(story.reactions, email=True)}</p>"
    )


def _source(story: Story) -> str:
    if not story.source_url:
        return ""
    url = escape(story.source_url, quote=True)
    label = escape(story.source_label) or "Source"
    return (
        f'<p style="margin:8px 0 0 0;font-family:{_FONT};font-size:16px;line-height:1.5;">'
        f'<a href="{url}" style="color:{_CLAY};text-decoration:underline;">{label}</a></p>'
    )


def _story(story: Story, *, rule: bool) -> str:
    border = (
        f'<div style="height:8px;line-height:8px;font-size:1px;border-bottom:1px solid {_LINE};">&nbsp;</div>'
        f"{_gap(18)}"
        if rule
        else ""
    )
    return (
        f"{border}"
        f'<h3 class="wine" style="margin:0 0 10px 0;font-family:{_FONT};font-size:20px;'
        f"line-height:1.35;font-weight:600;letter-spacing:-0.02em;color:{_WINE};\">"
        f"{emphasize(story.title, email=True)}</h3>"
        f'<p style="margin:0 0 10px 0;font-family:{_FONT};font-size:17px;line-height:1.55;color:{_INK};">'
        f"{emphasize(story.summary, email=True)}</p>"
        f"{_context(story)}"
        f'<p style="margin:10px 0 8px 0;font-family:{_FONT};font-size:17px;line-height:1.55;color:{_INK};">'
        f'<b style="font-weight:600;color:{_CLAY};">Why it matters.</b> '
        f"{emphasize(story.why_it_matters, email=True)}</p>"
        f'<p style="margin:0 0 8px 0;font-family:{_FONT};font-size:17px;line-height:1.55;color:{_INK};">'
        f'<b style="font-weight:600;color:{_CLAY};">Key fact.</b> '
        f"{emphasize(story.key_fact, email=True)}</p>"
        f"{_reactions(story)}{_source(story)}"
    )


def _heading(anchor: str, label: str, background: str, foreground: str) -> str:
    return (
        f'<p id="{anchor}" style="margin:0 0 14px 0;font-family:{_FONT};font-size:13px;line-height:1.4;">'
        f'<span style="display:inline-block;padding:4px 10px;border-radius:999px;'
        f"background:{background};color:{foreground};font-weight:600;\">{escape(label)}</span></p>"
    )


def _markets(figures: tuple[Figure, ...], note: str) -> str:
    if not figures:
        return ""
    line = f"Markets · {figures_line(figures)}"
    cells = []
    for figure in figures:
        when = escape(figure.as_of) if figure.as_of else "not fetched"
        if figure.source_url:
            source = (
                f'<a href="{escape(figure.source_url, quote=True)}" '
                f'style="color:{_CLAY};text-decoration:underline;">{escape(figure.source_name)}</a>'
            )
        else:
            source = escape(figure.source_name)
        cells.append(
            "<td width=\"50%\" valign=\"top\" style=\"width:50%;padding:0 6px 8px 0;"
            f"font-family:{_FONT};\">"
            f'<p class="muted" style="margin:0;font-size:12px;font-weight:600;color:{_MUTED};">'
            f"{escape(figure.label)}</p>"
            f'<p class="wine" style="margin:2px 0;font-size:22px;line-height:1.15;font-weight:600;'
            f'color:{_WINE};">{escape(figure.value)}</p>'
            f'<p class="muted" style="margin:0;font-size:12px;line-height:1.35;color:{_MUTED};">'
            f"{source} · {when}</p></td>"
        )
    rows = []
    for index in range(0, len(cells), 2):
        pair = "".join(cells[index : index + 2])
        rows.append(f"<tr>{pair}</tr>")
    background, foreground = MARKETS_PILL
    grid = (
        f'<p class="muted" style="margin:0 0 10px 0;font-family:{_FONT};font-size:14px;'
        f'line-height:1.45;color:{_MUTED};">{escape(note)}</p>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        f"{''.join(rows)}</table>"
    )
    return (
        f"{_gap(28)}"
        f"{_heading('figures', 'Markets', background, foreground)}"
        '<details class="markets-details">'
        "<summary>"
        f'<span class="sum-label" style="display:none;font-family:{_FONT};font-size:16px;'
        f"line-height:1.5;font-weight:600;color:{_WINE};\">{line}</span>"
        "</summary>"
        f'<div class="markets-full" style="display:none;max-height:0;overflow:hidden;">{grid}</div>'
        "</details>"
        f'<p class="markets-compact" style="margin:0;font-family:{_FONT};font-size:16px;'
        f'line-height:1.5;font-weight:600;color:{_WINE};">{line}</p>'
    )


def _model_meta(release: ModelRelease) -> str:
    parts: list[str] = [release.maker]
    if release.context_length:
        parts.append(f"{release.context_length:,} tokens")
    if release.open_weights and not release.input_per_million:
        parts.append("Open weights")
    if release.input_per_million:
        parts.append(f"{release.input_per_million} in")
    if release.output_per_million:
        parts.append(f"{release.output_per_million} out")
    return " · ".join(parts)


def _models(releases: tuple[ModelRelease, ...]) -> str:
    if not releases:
        return ""
    rows = []
    for index, release in enumerate(releases, start=1):
        note = ""
        if release.note and release.note_source:
            url = escape(release.note_source, quote=True)
            host = escape(urlsplit(release.note_source).hostname or "source")
            note = (
                '<tr><td class="tint" style="padding:8px 10px;background:#f4f0e6;'
                f"font-family:{_FONT};font-size:14px;line-height:1.45;color:{_INK};\">"
                f"{emphasize(release.note, email=True)} "
                f'<a href="{url}" style="color:{_CLAY};text-decoration:underline;">{host}</a>'
                "</td></tr>"
            )
        rows.append(
            "<tr>"
            f'<td class="num" width="32" valign="top" style="width:32px;padding:0 8px 14px 0;">'
            f'<div style="width:26px;height:26px;border-radius:13px;background:{_LIME};color:{_WINE};'
            f"font-family:{_FONT};font-size:14px;font-weight:600;line-height:26px;text-align:center;\">"
            f"{index}</div></td>"
            f'<td valign="top" style="padding:0 0 14px 0;font-family:{_FONT};color:{_INK};">'
            f'<p class="wine" style="margin:0;font-size:18px;line-height:1.35;font-weight:600;color:{_WINE};">'
            f"{escape(release.name)}</p>"
            f'<p class="muted" style="margin:2px 0 0 0;font-size:14px;line-height:1.45;color:{_MUTED};">'
            f"{escape(_model_meta(release))}</p>"
            + (
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
                f"{note}</table>"
                if note
                else ""
            )
            + "</td></tr>"
        )
    background, foreground = MODELS_PILL
    return (
        f"{_gap(28)}"
        f"{_heading('models', 'Model mania', background, foreground)}"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        f"{''.join(rows)}</table>"
        f'<p class="muted" style="margin:4px 0 0 0;font-family:{_FONT};font-size:14px;line-height:1.5;color:{_MUTED};">'
        "Compare them on "
        f'<a href="{escape(LMARENA_URL, quote=True)}" style="color:{_CLAY};text-decoration:underline;">LMArena</a>'
        " and "
        f'<a href="{escape(ARTIFICIAL_ANALYSIS_URL, quote=True)}" style="color:{_CLAY};text-decoration:underline;">Artificial Analysis</a>.'
        "</p>"
    )


def render_email(brief: Brief) -> str:
    """Table layout of the same brief. Inline styles carry the design."""

    demo = brief.public_demo
    figures = _EXAMPLE_FIGURES if demo else brief.figures
    figure_note = (
        "Example figures, not a live price."
        if demo
        else "Fetched on their own. Not written by the summary."
    )
    used = {"facts", "story", "models", "figures", "events"}
    anchors = [
        section_anchor(section.name, index, used)
        for index, section in enumerate(brief.sections, start=1)
    ]
    block_count = len(brief.sections) + (1 if figures else 0) + (1 if brief.model_releases else 0)
    if not demo:
        block_count += 1
    fact_word = "fact" if len(brief.top_lines) == 1 else "facts"
    section_word = "section" if block_count == 1 else "sections"
    pills = [
        _pill("Facts", "facts", FACTS_PILL[0], FACTS_PILL[1]),
        _pill("Story", "story", STORY_PILL[0], STORY_PILL[1]),
    ]
    pills.extend(
        _pill(section.name, anchor, *pill_colors(index))
        for index, (section, anchor) in enumerate(zip(brief.sections, anchors, strict=True))
    )
    if brief.model_releases:
        pills.append(_pill("Models", "models", MODELS_PILL[0], MODELS_PILL[1]))
    if figures:
        pills.append(_pill("Markets", "figures", MARKETS_PILL[0], MARKETS_PILL[1]))
    if not demo:
        pills.append(_pill("Events", "events", *pill_colors(len(brief.sections))))

    fact_rows = []
    for index, line in enumerate(brief.top_lines, start=1):
        fact_rows.append(
            "<tr>"
            f'<td class="num" width="32" valign="top" style="width:32px;padding:0 8px 14px 0;">'
            f'<div style="width:26px;height:26px;border-radius:13px;background:{_LIME};color:{_WINE};'
            f"font-family:{_FONT};font-size:14px;font-weight:600;line-height:26px;text-align:center;\">"
            f"{index}</div></td>"
            f'<td valign="top" style="padding:0 0 14px 0;font-family:{_FONT};font-size:17px;'
            f'line-height:1.5;color:{_INK};">{emphasize(line, email=True)}</td></tr>'
        )
    sections = []
    for index, (section, anchor) in enumerate(zip(brief.sections, anchors, strict=True)):
        background, foreground = pill_colors(index)
        cards = []
        for card_index, story in enumerate(section.stories):
            cards.append(_story(story, rule=card_index > 0))
        sections.append(
            f"{_gap(28)}{_heading(anchor, section.name, background, foreground)}{''.join(cards)}"
        )
    lead = brief.lead_story
    why = ""
    if brief.why_this_matters:
        why = (
            f"{_gap(8)}"
            f'<p style="margin:0;font-family:{_FONT};font-size:17px;line-height:1.55;color:{_INK};">'
            f'<b style="font-weight:600;color:{_CLAY};">Why this matters.</b> '
            f"{emphasize(brief.why_this_matters, email=True)}</p>"
        )
    events = ""
    if not demo:
        if brief.events:
            blocks = []
            for event in brief.events:
                url = escape(event.source_url, quote=True)
                blocks.append(
                    f'<p style="margin:0 0 8px 0;font-family:{_FONT};font-size:17px;line-height:1.45;color:{_INK};">'
                    f'<b style="font-weight:600;color:{_WINE};">{escape(event.title)}</b>'
                    f' · {escape(event.when)}<br>{emphasize(event.detail, email=True)} '
                    f'<a href="{url}" style="color:{_CLAY};text-decoration:underline;">'
                    f"{escape(event.source_label)}</a></p>"
                )
            event_body = "".join(blocks)
        else:
            event_body = (
                f'<p class="muted" style="margin:0;font-family:{_FONT};font-size:16px;color:{_MUTED};">'
                "None in today’s newsletters.</p>"
            )
        background, foreground = pill_colors(len(brief.sections))
        events = f"{_gap(28)}{_heading('events', 'Events', background, foreground)}{event_body}"
    preheader = escape(brief.top_lines[0]) if brief.top_lines else escape(brief.title)
    demo_line = ""
    if demo:
        demo_line = (
            f'<p class="muted" style="margin:0 0 22px 0;font-family:{_FONT};font-size:12px;'
            f'line-height:1.5;color:{_MUTED};">Public demo · Synthetic inputs. '
            "Names and figures here are examples.</p>"
        )
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '  <meta http-equiv="X-UA-Compatible" content="IE=edge">\n'
        '  <meta name="color-scheme" content="light dark">\n'
        '  <meta name="supported-color-schemes" content="light dark">\n'
        f"  <title>{escape(brief.title)}</title>\n"
        f"  <style type=\"text/css\">{_HEAD_CSS}</style>\n"
        "</head>\n"
        f'<body class="paper" style="margin:0;padding:0;background:{_PAPER};">\n'
        '<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">'
        f"{brief.read_time_minutes} min · {preheader}</div>\n"
        f'<table role="presentation" class="paper" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{_PAPER};">\n'
        "<tr><td height=\"8\" style=\"height:8px;background:#d0e79b;font-size:1px;line-height:8px;\">&nbsp;</td></tr>\n"
        "<tr><td align=\"center\" style=\"padding:28px 16px 48px 16px;\">\n"
        f'<table role="presentation" class="wrapper" width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px;max-width:600px;">\n'
        "<tr><td class=\"pad ink\" style=\"padding:0 28px;"
        f"font-family:{_FONT};color:{_INK};\">\n"
        f"{demo_line}"
        f'<p class="muted" style="margin:0 0 6px 0;font-family:{_FONT};font-size:15px;line-height:1.5;color:{_MUTED};">'
        f"{escape(_date_label(brief))}</p>\n"
        f'<h1 class="wine" style="margin:0 0 18px 0;font-family:{_FONT};font-size:32px;line-height:1.15;'
        f"font-weight:600;letter-spacing:-0.03em;color:{_WINE};\">{escape(brief.title)}</h1>\n"
        f'<p style="margin:0 0 12px 0;font-family:{_FONT};font-size:17px;line-height:1.5;color:{_INK};">'
        f'<b style="font-weight:600;">{brief.read_time_minutes} min</b> · '
        f"{len(brief.top_lines)} {fact_word} · 1 big story · {block_count} {section_word}</p>\n"
        f'<p style="margin:0 0 28px 0;">{"".join(pills)}</p>\n'
        f"{_heading('facts', 'Start here', FACTS_PILL[0], FACTS_PILL[1])}"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        f"{''.join(fact_rows)}</table>\n"
        f"{_gap(20)}"
        f"{_heading('story', 'The big story', STORY_PILL[0], STORY_PILL[1])}"
        f"{_story(lead, rule=False)}\n"
        f'<p class="muted" style="margin:12px 0 0 0;font-family:{_FONT};font-size:15px;line-height:1.5;color:{_MUTED};">'
        f'<span style="display:block;font-size:12px;font-weight:600;letter-spacing:0.04em;'
        f'text-transform:uppercase;">Today’s through-line</span>'
        f"{emphasize(brief.opening_note, email=True)}</p>\n"
        f"{why}\n"
        f"{''.join(sections)}\n"
        f"{_models(brief.model_releases)}\n"
        f"{_markets(figures, figure_note)}\n"
        f"{events}\n"
        f"{_gap(28)}"
        f'<p class="wine" style="margin:0 0 8px 0;font-family:{_FONT};font-size:22px;line-height:1.2;'
        f"font-weight:600;color:{_WINE};\">That’s it for today.</p>\n"
        f'<p class="muted" style="margin:0;font-family:{_FONT};font-size:14px;line-height:1.5;color:{_MUTED};">'
        "The links above are the ones that were in the inputs.</p>\n"
        "</td></tr></table>\n"
        "</td></tr></table>\n"
        "</body>\n</html>\n"
    )
