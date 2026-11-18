"""Deterministic HTML for the brief page. The email has its own table layout."""

from __future__ import annotations

from html import escape
from urllib.parse import urlsplit

from newsletter_brief.model_mania import ARTIFICIAL_ANALYSIS_URL, LMARENA_URL
from newsletter_brief.models import Brief, Event, Figure, ModelRelease, Section, Story
from newsletter_brief.presentation import (
    DARK,
    FACTS_PILL,
    LIGHT,
    MARKETS_PILL,
    MODELS_PILL,
    STORY_PILL,
    emphasize,
    figures_line,
    pill_colors,
    section_anchor,
)

_EXAMPLE_FIGURES = (
    Figure(
        figure_id="eur-usd",
        label="EUR to USD",
        value="1.00",
        source_name="Example",
        source_url="",
        as_of="example",
        available=True,
    ),
    Figure(
        figure_id="eur-gbp",
        label="EUR to GBP",
        value="0.80",
        source_name="Example",
        source_url="",
        as_of="example",
        available=True,
    ),
    Figure(
        figure_id="btc-usd",
        label="Bitcoin",
        value="10,000",
        source_name="Example",
        source_url="",
        as_of="example",
        available=True,
    ),
    Figure(
        figure_id="eth-usd",
        label="Ether",
        value="1,000",
        source_name="Example",
        source_url="",
        as_of="example",
        available=True,
    ),
)


def _variables(colors: dict[str, str]) -> str:
    return "\n".join(f"  --{name}: {value};" for name, value in colors.items())


_CSS = f"""
:root {{
  color-scheme: light dark;
{_variables(LIGHT)}
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; }}
body {{
  background: var(--paper);
  color: var(--ink);
  font-family: Inter, Helvetica, Arial, sans-serif;
  font-size: 18px;
  font-weight: 400;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  -webkit-text-size-adjust: 100%;
}}
body::before {{
  content: "";
  display: block;
  height: 8px;
  background: var(--lime);
}}
b, strong {{ font-weight: 600; }}
a {{
  color: var(--clay);
  text-decoration-thickness: 1px;
  text-underline-offset: 0.18em;
}}
a:hover {{ color: var(--wine); }}
a:focus-visible,
summary:focus-visible {{
  outline: 3px solid #7a9850;
  outline-offset: 3px;
}}
.skip-link {{
  position: absolute;
  left: 1rem;
  top: -4rem;
  z-index: 3;
  background: var(--wine);
  color: var(--lime);
  padding: 0.65rem 0.9rem;
  font-family: Inter, Helvetica, Arial, sans-serif;
}}
.skip-link:focus {{ top: 1rem; }}
.page {{
  width: min(33rem, calc(100% - 2.4rem));
  margin: 0 auto;
  padding: 2rem 0 4.5rem;
}}
.demo-note {{
  margin: 0 0 1.6rem;
  color: var(--muted);
  font-size: 0.78rem;
  line-height: 1.5;
}}
.demo-note strong {{ color: var(--wine); font-weight: 600; }}
.kicker {{
  margin: 0 0 0.35rem;
  color: var(--muted);
  font-size: 0.95rem;
}}
.masthead h1 {{
  margin: 0;
  color: var(--wine);
  font-size: 2.2rem;
  font-weight: 600;
  letter-spacing: -0.035em;
  line-height: 1.12;
}}
.progress {{ margin: 1.2rem 0 2.4rem; }}
.progress-meta {{
  margin: 0 0 0.85rem;
  font-size: 1rem;
}}
.progress ol {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(6.2rem, 1fr));
  gap: 0.35rem;
  list-style: none;
  margin: 0;
  padding: 0;
}}
.progress a {{
  display: block;
  padding: 0.35rem 0.4rem;
  min-height: 36px;
  text-align: center;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--ink);
  font-size: 0.75rem;
  font-weight: 600;
  text-decoration: none;
  line-height: 1.35;
}}
.progress a:hover {{ background: var(--warm); }}
.section {{ margin: 0 0 2.6rem; }}
.section-head {{
  display: flex;
  align-items: center;
  gap: 0.65rem;
  margin: 0 0 1rem;
}}
.sr-only {{
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}}
.tag {{
  display: inline-flex;
  align-items: center;
  padding: 0.28rem 0.65rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1.2;
}}
.fact-list {{
  list-style: none;
  margin: 0;
  padding: 0;
}}
.fact-list li {{
  display: grid;
  grid-template-columns: 1.8rem 1fr;
  gap: 0.75rem;
  margin: 0 0 1.05rem;
  align-items: start;
}}
.num {{
  width: 1.65rem;
  height: 1.65rem;
  border-radius: 50%;
  background: #d0e79b;
  color: #4a1028;
  font-weight: 600;
  font-size: 0.85rem;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  margin-top: 0.15rem;
  font-variant-numeric: tabular-nums;
}}
.fact-list p {{
  margin: 0;
  font-size: 1.05rem;
  line-height: 1.5;
}}
.card h3, .lead h3, .model-name {{
  margin: 0 0 0.65rem;
  color: var(--wine);
  font-size: 1.16rem;
  font-weight: 600;
  letter-spacing: -0.02em;
  line-height: 1.35;
}}
.summary, .why, .key-fact {{
  margin: 0 0 0.75rem;
  font-size: 1rem;
  line-height: 1.55;
}}
.why-label, .key-label, .who-label {{
  font-weight: 600;
  color: var(--clay);
}}
.who-label {{ color: var(--wine); }}
.why-brief {{
  margin: 0 0 1.6rem;
  font-size: 1rem;
  line-height: 1.55;
}}
.context {{
  margin: 0 0 0.85rem;
  padding: 0.55rem 0.8rem 0.6rem;
  background: var(--remember-bg);
  border-radius: 12px;
  font-size: 0.92rem;
  line-height: 1.45;
}}
.context a {{ color: var(--clay); }}
.source {{ margin: 0 0 0.2rem; font-size: 0.95rem; }}
.thread {{
  margin: 0.2rem 0 0;
  color: var(--muted);
  font-size: 0.95rem;
  line-height: 1.5;
}}
.thread span {{
  display: block;
  margin-bottom: 0.12rem;
  color: var(--muted);
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}}
.card + .card {{
  margin-top: 1.4rem;
  padding-top: 1.4rem;
  border-top: 1px solid var(--line);
}}
.more {{ margin: 0.2rem 0 0.6rem; }}
.more > summary {{
  cursor: pointer;
  color: var(--clay);
  font-weight: 600;
}}
.markets-toggle > summary {{
  cursor: pointer;
  list-style: none;
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
  align-items: baseline;
  color: var(--ink);
  font-size: 1rem;
}}
.markets-toggle > summary::-webkit-details-marker {{ display: none; }}
.markets-line {{ font-variant-numeric: tabular-nums; }}
.when-open {{ display: none; color: var(--clay); font-weight: 600; }}
.when-closed {{ color: var(--clay); font-weight: 600; }}
.markets-toggle[open] .when-closed {{ display: none; }}
.markets-toggle[open] .when-open {{ display: inline; }}
.markets-panel {{ margin-top: 0.9rem; }}
.figure-note, .markets-asof {{
  margin: 0 0 0.8rem;
  color: var(--muted);
  font-size: 0.88rem;
}}
.figure-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.7rem;
}}
.figure {{
  margin: 0;
  padding: 0.9rem 1rem;
  background: var(--warm);
  border-radius: 16px;
}}
.figure-label {{
  margin: 0;
  color: var(--muted);
  font-size: 0.75rem;
  font-weight: 600;
}}
.figure-value {{
  margin: 0.12rem 0;
  color: var(--wine);
  font-size: 1.35rem;
  font-weight: 600;
  letter-spacing: -0.03em;
  font-variant-numeric: tabular-nums;
  line-height: 1.15;
}}
.figure-meta {{
  margin: 0;
  color: var(--muted);
  font-size: 0.75rem;
  line-height: 1.35;
}}
.model-list {{
  list-style: none;
  margin: 0;
  padding: 0;
}}
.model-list li {{
  display: grid;
  grid-template-columns: 1.8rem 1fr;
  gap: 0.75rem;
  margin: 0 0 1.15rem;
}}
.model-meta {{
  margin: -0.35rem 0 0.45rem;
  color: var(--muted);
  font-size: 0.92rem;
}}
.model-boards {{
  margin: 0.2rem 0 0;
  color: var(--muted);
  font-size: 0.92rem;
}}
.story-card {{
  margin: 0 0 0.8rem;
}}
.story-card summary {{
  cursor: pointer;
  color: var(--wine);
  font-weight: 600;
}}
.story-card summary:hover {{ color: var(--accent-dark); }}
.story-body {{ padding: 0.4rem 0 0.2rem; }}
.issue-meta {{ margin: 0 0 0.3rem; color: var(--muted); font-size: 0.88rem; }}
.quiet {{ margin: 0; color: var(--muted); }}
.ending {{ margin-top: 0.4rem; padding-top: 0.4rem; }}
.ending::before {{
  content: "";
  display: block;
  width: 2.2rem;
  height: 8px;
  background: var(--lime);
  border-radius: 99px;
  margin-bottom: 1.1rem;
}}
.thats-it {{
  margin: 0 0 0.45rem;
  color: var(--wine);
  font-size: 1.45rem;
  font-weight: 600;
  letter-spacing: -0.03em;
}}
.ending p {{ margin: 0 0 0.45rem; }}
.fine, .footer-note {{
  color: var(--muted);
  font-size: 0.82rem;
  line-height: 1.5;
}}
.pipeline {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin: 0.7rem 0;
}}
.pipeline span {{
  padding: 0.2rem 0.5rem;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--muted);
  font-size: 0.72rem;
}}
.source-check {{
  margin: 0 0 0.7rem;
  padding: 0.55rem 0.7rem;
  background: var(--warm);
  border-radius: 12px;
  font-size: 0.82rem;
}}
@media (max-width: 680px) {{
  body {{ font-size: 17px; }}
  .masthead h1 {{ font-size: 1.9rem; }}
  .page {{ width: calc(100% - 2rem); padding-top: 1.4rem; }}
}}
@media (prefers-color-scheme: dark) {{
  :root {{
{_variables(DARK)}
  }}
  .num {{ background: #d0e79b; color: #4a1028; }}
  .figure {{ background: var(--warm); }}
}}
"""


def _all_stories(brief: Brief) -> tuple[Story, ...]:
    return (brief.lead_story,) + tuple(
        story for section in brief.sections for story in section.stories
    )


def _edition_urls(brief: Brief) -> set[str]:
    urls = {story.source_url for story in _all_stories(brief) if story.source_url}
    urls.update(event.source_url for event in brief.events if event.source_url)
    return urls


def _date_label(brief: Brief) -> str:
    day = brief.edition_date
    return f"{day:%A} {day.day} {day:%B %Y}"


def _source(story: Story) -> str:
    if not story.source_url:
        return ""
    url = escape(story.source_url, quote=True)
    label = escape(story.source_label) or "Source"
    return f'<p class="source"><a href="{url}" rel="noopener noreferrer">{label}</a></p>'


def _context(story: Story) -> str:
    if not story.context:
        return ""
    link = ""
    if story.context_source:
        url = escape(story.context_source, quote=True)
        host = escape(urlsplit(story.context_source).hostname or "source")
        link = f' <a href="{url}" rel="noopener noreferrer">{host}</a>'
    return (
        '<p class="context"><span class="who-label">Context.</span> '
        f"{emphasize(story.context)}{link}</p>"
    )


def _reactions(story: Story) -> str:
    if not story.reactions:
        return ""
    return (
        '<details class="more"><summary>Reactions</summary>'
        f"<p>{emphasize(story.reactions)}</p></details>"
    )


def _story(story: Story) -> str:
    return (
        '<article class="card">'
        f"<h3>{emphasize(story.title)}</h3>"
        f'<p class="summary">{emphasize(story.summary)}</p>'
        f'<p class="why"><span class="why-label">Why it matters.</span> {emphasize(story.why_it_matters)}</p>'
        f'<p class="key-fact"><span class="key-label">Key fact.</span> {emphasize(story.key_fact)}</p>'
        f"{_context(story)}{_reactions(story)}{_source(story)}"
        "</article>"
    )


def _section(section: Section, index: int, anchor: str) -> str:
    background, foreground = pill_colors(index)
    cards = "".join(_story(story) for story in section.stories)
    return (
        f'<section class="section" id="{anchor}" aria-labelledby="h-{anchor}">'
        '<header class="section-head">'
        f'<span class="tag" style="background:{background};color:{foreground}">'
        f"{escape(section.name)}</span>"
        f'<h2 id="h-{anchor}" class="sr-only">{escape(section.name)}</h2>'
        "</header>"
        f"{cards}</section>"
    )


def _figure_card(figure: Figure) -> str:
    when = escape(figure.as_of) if figure.as_of else "not fetched"
    if figure.source_url:
        source = (
            f'<a href="{escape(figure.source_url, quote=True)}" rel="noopener noreferrer">'
            f"{escape(figure.source_name)}</a>"
        )
    else:
        source = escape(figure.source_name)
    return (
        '<div class="figure">'
        f'<p class="figure-label">{escape(figure.label)}</p>'
        f'<p class="figure-value">{escape(figure.value)}</p>'
        f'<p class="figure-meta">{source} · {when}</p>'
        "</div>"
    )


def _markets(figures: tuple[Figure, ...], note: str) -> str:
    if not figures:
        return ""
    line = figures_line(figures)
    cards = "".join(_figure_card(figure) for figure in figures)
    background, foreground = MARKETS_PILL
    return (
        '<aside class="section markets" id="figures" aria-labelledby="figures-title">'
        '<header class="section-head">'
        f'<span class="tag" style="background:{background};color:{foreground}">Markets</span>'
        '<h2 id="figures-title" class="sr-only">Markets</h2>'
        "</header>"
        '<details class="markets-toggle">'
        "<summary>"
        f'<span class="markets-line">{line}</span>'
        '<span class="when-closed">Show</span>'
        '<span class="when-open">Hide</span>'
        "</summary>"
        '<div class="markets-panel">'
        f'<p class="figure-note">{escape(note)}</p>'
        f'<div class="figure-grid">{cards}</div>'
        "</div>"
        "</details>"
        "</aside>"
    )


def _model_meta(release: ModelRelease) -> str:
    parts: list[str] = []
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
    rows: list[str] = []
    for index, release in enumerate(releases, start=1):
        meta = _model_meta(release)
        detail = escape(release.maker) if not meta else f"{escape(release.maker)} · {escape(meta)}"
        note = ""
        if release.note and release.note_source:
            url = escape(release.note_source, quote=True)
            host = escape(urlsplit(release.note_source).hostname or "source")
            note = (
                '<p class="context"><span class="who-label">Note.</span> '
                f'{emphasize(release.note)} '
                f'<a href="{url}" rel="noopener noreferrer">{host}</a></p>'
            )
        rows.append(
            "<li>"
            f'<span class="num">{index}</span>'
            "<div>"
            f'<p class="model-name">{escape(release.name)}</p>'
            f'<p class="model-meta">{detail}</p>'
            f"{note}"
            "</div></li>"
        )
    background, foreground = MODELS_PILL
    return (
        '<section class="section" id="models" aria-labelledby="h-models">'
        '<header class="section-head">'
        f'<span class="tag" style="background:{background};color:{foreground}">Model mania</span>'
        '<h2 id="h-models" class="sr-only">Model mania</h2>'
        "</header>"
        f'<ol class="model-list">{"".join(rows)}</ol>'
        '<p class="model-boards">Compare them on '
        f'<a href="{escape(LMARENA_URL, quote=True)}">LMArena</a>'
        " and "
        f'<a href="{escape(ARTIFICIAL_ANALYSIS_URL, quote=True)}">Artificial Analysis</a>.'
        "</p></section>"
    )


def _event_card(event: Event) -> str:
    url = escape(event.source_url, quote=True)
    label = escape(event.source_label)
    return (
        '<details class="story-card">'
        f"<summary>{escape(event.title)}</summary>"
        '<div class="story-body">'
        f'<p class="issue-meta">{escape(event.when)}</p>'
        f"<p>{emphasize(event.detail)}</p>"
        f'<p class="source"><a href="{url}" rel="noopener noreferrer">{label}</a></p>'
        "</div></details>"
    )


def _events(brief: Brief) -> str:
    if brief.events:
        body = "".join(_event_card(event) for event in brief.events)
    else:
        body = '<p class="quiet">None in today’s newsletters.</p>'
    background, foreground = pill_colors(len(brief.sections))
    return (
        '<section class="section" id="events" aria-labelledby="h-events">'
        '<header class="section-head">'
        f'<span class="tag" style="background:{background};color:{foreground}">Events</span>'
        '<h2 id="h-events" class="sr-only">Events</h2>'
        "</header>"
        f"{body}</section>"
    )


def _nav_link(href: str, label: str) -> str:
    return f'<li><a href="#{href}">{escape(label)}</a></li>'


def _render(
    brief: Brief,
    *,
    demo: bool,
    figures: tuple[Figure, ...],
    figure_note: str,
) -> str:
    used = {"facts", "story", "models", "figures", "events"}
    anchors = [
        section_anchor(section.name, index, used)
        for index, section in enumerate(brief.sections, start=1)
    ]
    sections_html = "".join(
        _section(section, index, anchor)
        for index, (section, anchor) in enumerate(zip(brief.sections, anchors, strict=True))
    )
    links = [_nav_link("facts", "Facts"), _nav_link("story", "Story")]
    links.extend(
        _nav_link(anchor, section.name)
        for section, anchor in zip(brief.sections, anchors, strict=True)
    )
    if brief.model_releases:
        links.append(_nav_link("models", "Models"))
    if figures:
        links.append(_nav_link("figures", "Markets"))
    if not demo:
        links.append(_nav_link("events", "Events"))
    block_count = len(brief.sections)
    if brief.model_releases:
        block_count += 1
    if figures:
        block_count += 1
    if not demo:
        block_count += 1
    fact_word = "fact" if len(brief.top_lines) == 1 else "facts"
    section_word = "section" if block_count == 1 else "sections"
    facts = "".join(
        f'<li><span class="num">{index}</span><p>{emphasize(line)}</p></li>'
        for index, line in enumerate(brief.top_lines, start=1)
    )
    lead = brief.lead_story
    why = (
        f'<p class="why-brief"><span class="why-label">Why this matters.</span> '
        f"{emphasize(brief.why_this_matters)}</p>"
        if brief.why_this_matters
        else ""
    )
    if demo:
        source_count = len({story.source_url for story in _all_stories(brief)})
    else:
        source_count = len(_edition_urls(brief))
    link_word = "link" if source_count == 1 else "links"
    if demo:
        check = (
            f"<strong>Source check</strong> · {source_count} {link_word} in this edition, "
            "each one matched to an item in the inputs. A link that isn’t in the inputs stops the build."
        )
        pipeline = (
            '<div class="pipeline" aria-label="Demo architecture">'
            "<span>synthetic inputs</span><span>structured synthesis</span>"
            "<span>schema validation</span><span>deterministic HTML</span></div>"
        )
        closing = (
            '<p class="footer-note">Every name, publication, excerpt and claim in this edition is fictional. '
            "The public repository contains no inbox connection or production personalization logic.</p>"
        )
        demo_note = (
            '<p class="demo-note"><strong>Public demo</strong> · Synthetic inputs and fictional sources; '
            "no inbox data or real newsletter content.</p>"
        )
        title = f"{escape(brief.title)} · Synthetic demo"
        description = "A synthetic, source-visible newsletter brief demo."
        edition_line = f"<p><strong>{escape(brief.edition)}</strong> · How this public demo was made</p>"
    else:
        check = (
            f"<strong>Source check</strong> · {source_count} {link_word} in this edition, "
            "each one matched to an item in the inputs. Figure links point at the data source. "
            "A link that isn’t in the inputs stops the build."
        )
        pipeline = (
            '<div class="pipeline" aria-label="How this page was made">'
            "<span>your inbox</span><span>structured synthesis</span>"
            "<span>link check</span><span>this page</span></div>"
        )
        note = (
            f'<p class="footer-note">{escape(brief.input_note)}</p>' if brief.input_note else ""
        )
        closing = (
            f"{note}"
            '<p class="footer-note">Newsletter text was sent to the model provider configured for this run. '
            "Figures were fetched separately. Nothing else was sent.</p>"
        )
        demo_note = ""
        title = escape(brief.title)
        description = "A morning brief made from your newsletters."
        edition_line = f"<p><strong>{escape(brief.edition)}</strong> · How this page was made</p>"
    events = "" if demo else _events(brief)
    facts_bg, facts_fg = FACTS_PILL
    story_bg, story_fg = STORY_PILL
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '  <meta name="color-scheme" content="light dark">\n'
        '  <meta name="supported-color-schemes" content="light dark">\n'
        f"  <title>{title}</title>\n"
        f'  <meta name="description" content="{description}">\n'
        f"  <style>{_CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        '  <a class="skip-link" href="#facts">Skip to facts</a>\n'
        '  <main class="page" id="brief">\n'
        f"    {demo_note}"
        '    <header class="masthead">\n'
        f'      <p class="kicker">{escape(_date_label(brief))}</p>\n'
        f"      <h1>{escape(brief.title)}</h1>\n"
        "    </header>\n"
        '    <nav class="progress" aria-label="In this brief">\n'
        f'      <p class="progress-meta"><b>{brief.read_time_minutes} min</b> · '
        f"{len(brief.top_lines)} {fact_word} · 1 big story · {block_count} {section_word}</p>\n"
        f"      <ol>{''.join(links)}</ol>\n"
        "    </nav>\n"
        '    <section class="section" id="facts" aria-labelledby="glance-title">\n'
        '      <header class="section-head">\n'
        f'        <span class="tag" style="background:{facts_bg};color:{facts_fg}">Start here</span>\n'
        f'        <h2 id="glance-title" class="sr-only">{len(brief.top_lines)} things to remember today</h2>\n'
        "      </header>\n"
        f'      <ol class="fact-list">{facts}</ol>\n'
        "    </section>\n"
        '    <section class="section" id="story" aria-labelledby="lead-section">\n'
        '      <header class="section-head">\n'
        f'        <span class="tag" style="background:{story_bg};color:{story_fg}">The big story</span>\n'
        '        <h2 id="lead-section" class="sr-only">The big story</h2>\n'
        "      </header>\n"
        '      <article class="card lead">\n'
        f"        <h3>{emphasize(lead.title)}</h3>\n"
        f'        <p class="summary">{emphasize(lead.summary)}</p>\n'
        f'        <p class="why"><span class="why-label">Why it matters.</span> {emphasize(lead.why_it_matters)}</p>\n'
        f'        <p class="key-fact"><span class="key-label">Key fact.</span> {emphasize(lead.key_fact)}</p>\n'
        f"        {_context(lead)}\n"
        f"        {_reactions(lead)}\n"
        f'        <p class="thread"><span>Today’s through-line</span>{emphasize(brief.opening_note)}</p>\n'
        f"        {_source(lead)}\n"
        "      </article>\n"
        "    </section>\n"
        f"    {why}\n"
        f"{sections_html}\n"
        f"    {_models(brief.model_releases)}\n"
        f"    {_markets(figures, figure_note)}\n"
        f"    {events}\n"
        '    <footer class="ending">\n'
        '      <p class="thats-it">That’s it for today.</p>\n'
        f"      {edition_line}\n"
        f"      {pipeline}\n"
        f'      <p class="source-check">{check}</p>\n'
        f"      {closing}\n"
        "    </footer>\n"
        "  </main>\n"
        "</body>\n"
        "</html>\n"
    )


def render_html(brief: Brief) -> str:
    """Render the public demo or a personal brief page."""

    if brief.public_demo:
        return _render(
            brief,
            demo=True,
            figures=_EXAMPLE_FIGURES,
            figure_note="Example figures, not a live price.",
        )
    return _render(
        brief,
        demo=False,
        figures=brief.figures,
        figure_note="Fetched on their own. Not written by the summary.",
    )
