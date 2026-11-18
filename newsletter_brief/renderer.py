"""Deterministic, dependency-free HTML rendering for a validated Brief."""

from __future__ import annotations

from html import escape

from newsletter_brief.models import Brief, Event, Figure, Section, Story

_CSS = """
:root {
  color-scheme: light;
  --canvas: #f3f4f6;
  --paper: #ffffff;
  --ink: #1a1a1a;
  --muted: #6b7280;
  --line: #e5e7eb;
  --card: #f9fafb;
  --accent: #4f46e5;
  --accent-dark: #3730a3;
  --remember-bg: #eef2ff;
  --quote-line: #c7d2fe;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--canvas);
  color: var(--ink);
  font-family: Charter, "Charter BT", "Iowan Old Style", Georgia, "Times New Roman", serif;
  line-height: 1.5;
  -webkit-text-size-adjust: 100%;
}
a {
  color: var(--accent);
  text-decoration-thickness: 1px;
  text-underline-offset: 0.16em;
}
a:hover { color: var(--accent-dark); }
a:focus-visible,
summary:focus-visible {
  outline: 3px solid var(--quote-line);
  outline-offset: 3px;
}
.skip-link {
  position: fixed;
  left: 1rem;
  top: -4rem;
  z-index: 3;
  background: var(--ink);
  color: var(--paper);
  padding: 0.65rem 0.9rem;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.skip-link:focus { top: 1rem; }
.page {
  width: min(640px, calc(100% - 2rem));
  min-height: 100vh;
  margin: 1.5rem auto 3rem;
  padding: 2rem 1.5rem 2.5rem;
  background: var(--paper);
  box-shadow: 0 18px 50px rgba(17, 24, 39, 0.08);
}
.demo-note {
  margin: 0 0 1.6rem;
  padding: 0 0 0.7rem;
  border-bottom: 1px solid var(--line);
  color: var(--muted);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 0.72rem;
  line-height: 1.45;
}
.demo-note strong {
  color: var(--accent-dark);
  font-weight: 700;
}
.masthead {
  margin-bottom: 1.2rem;
}
.masthead h1 {
  margin: 0 0 0.15rem;
  font-size: clamp(1.8rem, 7vw, 2.15rem);
  font-weight: 800;
  letter-spacing: -0.025em;
  line-height: 1.1;
}
.issue-meta {
  margin: 0;
  color: var(--muted);
  font-size: 0.86rem;
}
.at-a-glance {
  margin: 0 0 1.7rem;
  padding: 1rem 1.1rem 0.8rem;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 12px;
}
.at-a-glance h2 {
  margin: 0 0 0.75rem;
  color: var(--muted);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.at-a-glance ol {
  margin: 0;
  padding: 0;
  list-style: none;
  counter-reset: item;
}
.at-a-glance li {
  display: grid;
  grid-template-columns: 1.4rem 1fr;
  gap: 0.2rem;
  margin: 0 0 0.48rem;
  font-size: 0.94rem;
  line-height: 1.45;
}
.at-a-glance li::before {
  counter-increment: item;
  content: counter(item) ".";
  color: var(--accent);
  font-weight: 700;
}
.section-heading {
  margin: 0;
  padding: 0 0 0.35rem;
  border-bottom: 2px solid var(--accent);
  color: var(--accent);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 0.82rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.lead {
  padding: 0.9rem 0 0.2rem;
}
.lead h3 {
  margin: 0 0 0.5rem;
  font-size: clamp(1.45rem, 5.7vw, 1.85rem);
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.22;
}
.lead-summary {
  margin: 0 0 0.35rem;
  font-size: 1rem;
}
.why {
  margin: 0 0 0.7rem;
  color: var(--muted);
  font-size: 0.93rem;
}
.why strong {
  color: var(--accent);
  font-weight: 600;
}
.key-fact {
  display: inline-block;
  margin: 0.05rem 0 0.75rem;
  padding: 0.42rem 0.7rem;
  border-radius: 8px;
  background: var(--remember-bg);
  color: var(--accent-dark);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 0.8rem;
  font-weight: 600;
}
.thread {
  margin: 0.15rem 0 0.75rem;
  padding: 0.35rem 0 0.35rem 0.85rem;
  /* Intentional: this matches the private email's quoted talk-track treatment. */
  border-left: 3px solid var(--quote-line);
  font-size: 0.9rem;
  font-style: italic;
  line-height: 1.5;
}
.thread span {
  display: block;
  margin-bottom: 0.12rem;
  color: var(--muted);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 0.7rem;
  font-style: normal;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.source {
  margin: 0.1rem 0 0;
  color: var(--muted);
  font-size: 0.76rem;
}
.sections {
  margin-top: 0.3rem;
}
.section {
  margin-top: 1.6rem;
}
.section-header {
  border-bottom: 2px solid var(--accent);
}
.section-header h2 {
  margin: 0;
  padding-bottom: 0.35rem;
  color: var(--accent);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 0.82rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.story-card {
  padding: 0.85rem 0;
  border-bottom: 1px solid var(--line);
}
.story-card summary {
  color: var(--ink);
  cursor: pointer;
  font-size: 1.03rem;
  font-weight: 700;
  line-height: 1.35;
}
.story-card summary:hover { color: var(--accent-dark); }
.story-body {
  padding: 0.55rem 0 0 1.05rem;
}
.story-body > p:first-child {
  margin: 0 0 0.35rem;
  font-size: 0.94rem;
}
.footer {
  margin-top: 1.8rem;
  padding-top: 0.9rem;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 0.7rem;
}
.footer p { margin: 0; }
.pipeline {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  margin: 0.65rem 0;
}
.pipeline span {
  padding: 0.25rem 0.48rem;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--muted);
  font-size: 0.65rem;
}
.footer-note {
  line-height: 1.5;
}
.source-check {
  margin: 0 0 0.65rem;
  padding: 0.45rem 0.6rem;
  border-left: 3px solid var(--accent);
  background: var(--card);
  color: var(--ink);
  font-size: 0.72rem;
}
@media (max-width: 680px) {
  body { background: var(--paper); }
  .page {
    width: 100%;
    margin: 0;
    padding: 1.35rem 1.1rem 2rem;
    box-shadow: none;
  }
  .demo-note { margin-bottom: 1.3rem; }
  .at-a-glance { padding-inline: 1rem; }
}
"""


def _all_stories(brief: Brief) -> tuple[Story, ...]:
    return (brief.lead_story,) + tuple(
        story for section in brief.sections for story in section.stories
    )


def _source(story: Story) -> str:
    if not story.source_url:
        return ""
    url = escape(story.source_url, quote=True)
    label = escape(story.source_label)
    return (
        f'<p class="source">→ <a href="{url}" rel="noopener noreferrer">{label}</a></p>'
    )


def _story_card(story: Story) -> str:
    return (
        '<details class="story-card">'
        f"<summary>{escape(story.title)}</summary>"
        '<div class="story-body">'
        f"<p>{escape(story.summary)}</p>"
        f'<p class="why"><strong>Why·</strong> {escape(story.why_it_matters)}</p>'
        f'<p class="key-fact">Remember · {escape(story.key_fact)}</p>'
        f"{_source(story)}"
        "</div>"
        "</details>"
    )


def _section(section: Section, index: int) -> str:
    cards = "".join(_story_card(story) for story in section.stories)
    return (
        f'<section class="section" aria-labelledby="section-{index}">'
        '<div class="section-header">'
        f'<h2 id="section-{index}">{escape(section.name)}</h2>'
        "</div>"
        f"{cards}"
        "</section>"
    )


def _render_public_demo(brief: Brief) -> str:
    """Return byte-for-byte stable HTML for the same validated demo brief."""

    date_label = (
        f"{brief.edition_date:%a, %b} {brief.edition_date.day}, {brief.edition_date:%Y}"
    )
    top_lines = "".join(f"<li>{escape(line)}</li>" for line in brief.top_lines)
    sections = "".join(
        _section(section, index)
        for index, section in enumerate(brief.sections, start=1)
    )
    lead = brief.lead_story
    source_count = len({story.source_url for story in _all_stories(brief)})
    link_word = "link" if source_count == 1 else "links"

    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"  <title>{escape(brief.title)} · Synthetic demo</title>\n"
        '  <meta name="description" content="A synthetic, source-visible newsletter brief demo.">\n'
        f"  <style>{_CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        '  <a class="skip-link" href="#brief">Skip to brief</a>\n'
        '  <main class="page" id="brief">\n'
        '    <p class="demo-note"><strong>Public demo</strong> · Synthetic inputs and fictional sources; '
        "no inbox data or real newsletter content.</p>\n"
        '    <header class="masthead">\n'
        f"      <h1>{escape(brief.title)}</h1>\n"
        '      <p class="issue-meta">'
        f"{escape(date_label)} &nbsp;·&nbsp; "
        f"{brief.read_time_minutes} min essentials</p>\n"
        "    </header>\n"
        '    <aside class="at-a-glance" aria-labelledby="glance-title">\n'
        f'      <h2 id="glance-title">{len(brief.top_lines)} things to remember today</h2>\n'
        f"      <ol>{top_lines}</ol>\n"
        "    </aside>\n"
        '    <section aria-labelledby="lead-section">\n'
        '      <h2 class="section-heading" id="lead-section">The Big Story</h2>\n'
        '      <article class="lead">\n'
        f"        <h3>{escape(lead.title)}</h3>\n"
        f'        <p class="lead-summary">{escape(lead.summary)}</p>\n'
        f'        <p class="why"><strong>Why·</strong> {escape(lead.why_it_matters)}</p>\n'
        f'        <p class="key-fact">Remember · {escape(lead.key_fact)}</p>\n'
        '        <blockquote class="thread"><span>Today’s through-line</span>'
        f"“{escape(brief.opening_note)}”</blockquote>\n"
        f"        {_source(lead)}\n"
        "      </article>\n"
        "    </section>\n"
        f'    <div class="sections">{sections}</div>\n'
        '    <footer class="footer">\n'
        f"      <p><strong>{escape(brief.edition)}</strong> · How this public demo was made</p>\n"
        '        <div class="pipeline" aria-label="Demo architecture">\n'
        "          <span>synthetic inputs</span><span>structured synthesis</span>"
        "<span>schema validation</span><span>deterministic HTML</span>\n"
        "        </div>\n"
        f'      <p class="source-check"><strong>Source check</strong> · {source_count} {link_word} in this edition, '
        "each one matched to an item in the inputs. A link that isn’t in the inputs stops the build.</p>\n"
        '      <p class="footer-note">Every name, publication, excerpt and claim in this edition is fictional. '
        "The public repository contains no inbox connection or production personalization logic.</p>\n"
        "    </footer>\n"
        "  </main>\n"
        "</body>\n"
        "</html>\n"
    )


_EDITION_CSS = """
.why-box {
  margin: 0 0 1.7rem;
  padding: 1rem 1.1rem 0.95rem;
  background: var(--remember-bg);
  border-radius: 12px;
}
.why-box h2 {
  margin: 0 0 0.45rem;
  color: var(--accent-dark);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.why-box p { margin: 0; font-size: 0.98rem; }
.figure-note {
  margin: -0.35rem 0 0.75rem;
  color: var(--muted);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 0.72rem;
}
.figure-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.55rem;
}
.figure {
  margin: 0;
  padding: 0.55rem 0.7rem 0.5rem;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 8px;
}
.figure-label {
  margin: 0;
  color: var(--muted);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.figure-value {
  margin: 0.12rem 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 1.15rem;
  font-weight: 700;
}
.figure-meta {
  margin: 0;
  color: var(--muted);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 0.68rem;
  line-height: 1.35;
}
.quiet {
  margin: 0.7rem 0 0.2rem;
  color: var(--muted);
  font-size: 0.9rem;
}
@media (max-width: 680px) {
  .figure-grid { grid-template-columns: 1fr; }
}
"""


def _edition_urls(brief: Brief) -> set[str]:
    urls = {story.source_url for story in _all_stories(brief) if story.source_url}
    urls.update(event.source_url for event in brief.events if event.source_url)
    return urls


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


def _event_card(event: Event) -> str:
    url = escape(event.source_url, quote=True)
    label = escape(event.source_label)
    return (
        '<details class="story-card">'
        f"<summary>{escape(event.title)}</summary>"
        '<div class="story-body">'
        f'<p class="issue-meta">{escape(event.when)}</p>'
        f"<p>{escape(event.detail)}</p>"
        f'<p class="source">→ <a href="{url}" rel="noopener noreferrer">{label}</a></p>'
        "</div>"
        "</details>"
    )


def _render_edition(brief: Brief) -> str:
    """Personal brief. Same column, type and rules as the demo, with the extra boxes."""

    date_label = (
        f"{brief.edition_date:%a, %b} {brief.edition_date.day}, {brief.edition_date:%Y}"
    )
    top_lines = "".join(f"<li>{escape(line)}</li>" for line in brief.top_lines)
    sections = "".join(
        _section(section, index)
        for index, section in enumerate(brief.sections, start=1)
    )
    lead = brief.lead_story
    source_count = len(_edition_urls(brief))
    link_word = "link" if source_count == 1 else "links"
    why = (
        '<aside class="why-box" aria-labelledby="why-title">\n'
        '      <h2 id="why-title">Why this matters</h2>\n'
        f"      <p>{escape(brief.why_this_matters)}</p>\n"
        "    </aside>\n"
        if brief.why_this_matters
        else ""
    )
    if brief.figures:
        cards = "".join(_figure_card(figure) for figure in brief.figures)
        figures = (
            '<aside class="at-a-glance" id="figures" aria-labelledby="figures-title">\n'
            '      <h2 id="figures-title">Figures</h2>\n'
            '      <p class="figure-note">Fetched on their own. Not written by the summary.</p>\n'
            f'      <div class="figure-grid">{cards}</div>\n'
            "    </aside>\n"
        )
    else:
        figures = ""
    if brief.events:
        event_cards = "".join(_event_card(event) for event in brief.events)
        event_body = event_cards
    else:
        event_body = '<p class="quiet">None in today’s newsletters.</p>'
    events = (
        '<section class="section" aria-labelledby="events-title">\n'
        '      <div class="section-header">'
        '<h2 id="events-title">Events</h2></div>\n'
        f"      {event_body}\n"
        "    </section>\n"
    )
    note = (
        f'      <p class="footer-note">{escape(brief.input_note)}</p>\n'
        if brief.input_note
        else ""
    )
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"  <title>{escape(brief.title)}</title>\n"
        '  <meta name="description" content="A morning brief made from your newsletters.">\n'
        f"  <style>{_CSS}{_EDITION_CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        '  <a class="skip-link" href="#brief">Skip to brief</a>\n'
        '  <main class="page" id="brief">\n'
        '    <header class="masthead">\n'
        f"      <h1>{escape(brief.title)}</h1>\n"
        '      <p class="issue-meta">'
        f"{escape(date_label)} &nbsp;·&nbsp; "
        f"{brief.read_time_minutes} min essentials</p>\n"
        "    </header>\n"
        '    <aside class="at-a-glance" aria-labelledby="glance-title">\n'
        f'      <h2 id="glance-title">{len(brief.top_lines)} things to remember today</h2>\n'
        f"      <ol>{top_lines}</ol>\n"
        "    </aside>\n"
        f"    {why}"
        f"    {figures}"
        '    <section aria-labelledby="lead-section">\n'
        '      <h2 class="section-heading" id="lead-section">The Big Story</h2>\n'
        '      <article class="lead">\n'
        f"        <h3>{escape(lead.title)}</h3>\n"
        f'        <p class="lead-summary">{escape(lead.summary)}</p>\n'
        f'        <p class="why"><strong>Why·</strong> {escape(lead.why_it_matters)}</p>\n'
        f'        <p class="key-fact">Remember · {escape(lead.key_fact)}</p>\n'
        '        <blockquote class="thread"><span>Today’s through-line</span>'
        f"“{escape(brief.opening_note)}”</blockquote>\n"
        f"        {_source(lead)}\n"
        "      </article>\n"
        "    </section>\n"
        f'    <div class="sections">{sections}</div>\n'
        f"    {events}"
        '    <footer class="footer">\n'
        f"      <p><strong>{escape(brief.edition)}</strong> · How this page was made</p>\n"
        '      <div class="pipeline" aria-label="How this page was made">\n'
        "        <span>your inbox</span><span>structured synthesis</span>"
        "<span>link check</span><span>this page</span>\n"
        "      </div>\n"
        f'      <p class="source-check"><strong>Source check</strong> · {source_count} {link_word} in this edition, '
        "each one matched to an item in the inputs. Figure links point at the data source. "
        "A link that isn’t in the inputs stops the build.</p>\n"
        f"{note}"
        '      <p class="footer-note">Newsletter text was sent to the model provider configured for this run. '
        "Figures were fetched separately. Nothing else was sent.</p>\n"
        "    </footer>\n"
        "  </main>\n"
        "</body>\n"
        "</html>\n"
    )


def render_html(brief: Brief) -> str:
    """Render the public demo or a personal brief. The demo path stays byte-stable."""

    if brief.public_demo:
        return _render_public_demo(brief)
    return _render_edition(brief)
