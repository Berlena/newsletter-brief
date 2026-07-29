"""Deterministic, dependency-free HTML rendering for a validated Brief."""

from __future__ import annotations

from html import escape

from newsletter_brief.models import Brief, Section, Story

_CSS = """
:root {
  color-scheme: light;
  --paper: #f4f0e7;
  --sheet: #fffdf8;
  --ink: #20201d;
  --muted: #6b6860;
  --line: #d8d1c3;
  --signal: #d9653b;
  --signal-dark: #8d3821;
  --lead-bg: #d9653b;
  --lead-ink: #18110e;
  --lead-secondary: #2a1a14;
  --lead-hover: #000000;
  --wash: #ede5d8;
  --sage: #dfe5d7;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.55;
}
a { color: inherit; text-underline-offset: 0.18em; }
a:hover { color: var(--signal-dark); }
.skip-link {
  position: absolute;
  left: 1rem;
  top: -4rem;
  z-index: 2;
  background: var(--ink);
  color: white;
  padding: 0.65rem 0.9rem;
}
.skip-link:focus { top: 1rem; }
.demo-bar {
  background: var(--ink);
  color: #fff;
  font-size: 0.72rem;
  font-weight: 750;
  letter-spacing: 0.13em;
  padding: 0.7rem 1rem;
  text-align: center;
  text-transform: uppercase;
}
.page {
  width: min(1120px, calc(100% - 2rem));
  margin: 1.4rem auto 3rem;
  background: var(--sheet);
  border: 1px solid var(--line);
  box-shadow: 0 24px 70px rgba(53, 45, 31, 0.09);
}
.masthead {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 1.5rem;
  align-items: end;
  padding: 2rem clamp(1.25rem, 4vw, 3.5rem) 1.5rem;
  border-bottom: 1px solid var(--line);
}
.eyebrow, .section-label, .story-label {
  margin: 0 0 0.45rem;
  color: var(--signal-dark);
  font-size: 0.7rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}
.masthead h1 {
  margin: 0;
  font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
  font-size: clamp(2.7rem, 7vw, 5.8rem);
  font-weight: 500;
  letter-spacing: -0.055em;
  line-height: 0.9;
}
.issue-meta {
  margin: 0;
  color: var(--muted);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 0.73rem;
  line-height: 1.7;
  text-align: right;
  text-transform: uppercase;
}
.opening {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(250px, 0.75fr);
  gap: clamp(1.5rem, 5vw, 4rem);
  padding: clamp(2rem, 5vw, 4.2rem) clamp(1.25rem, 4vw, 3.5rem);
}
.opening-note {
  margin: 0;
  font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
  font-size: clamp(1.65rem, 3.5vw, 2.8rem);
  letter-spacing: -0.025em;
  line-height: 1.16;
}
.at-a-glance {
  align-self: start;
  padding: 1.2rem 1.25rem;
  background: var(--wash);
}
.at-a-glance h2 {
  margin: 0 0 0.8rem;
  font-size: 0.75rem;
  letter-spacing: 0.13em;
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
  grid-template-columns: 1.8rem 1fr;
  gap: 0.35rem;
  padding: 0.65rem 0;
  border-top: 1px solid rgba(32, 32, 29, 0.16);
  font-size: 0.88rem;
}
.at-a-glance li::before {
  counter-increment: item;
  content: "0" counter(item);
  color: var(--signal-dark);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 0.68rem;
  padding-top: 0.15rem;
}
.lead-wrap {
  padding: 0 clamp(1.25rem, 4vw, 3.5rem) clamp(2rem, 5vw, 4rem);
}
.lead {
  display: grid;
  grid-template-columns: minmax(280px, 0.85fr) minmax(0, 1.15fr);
  gap: clamp(2rem, 4vw, 3.5rem);
  padding: clamp(1.5rem, 4vw, 3rem);
  background: var(--lead-bg);
  color: var(--lead-ink);
}
.lead .story-label { color: var(--lead-ink); }
.lead h2 {
  max-width: 13ch;
  margin: 0;
  font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
  font-size: clamp(2.25rem, 3.7vw, 3.45rem);
  font-weight: 500;
  letter-spacing: -0.035em;
  line-height: 1;
  text-wrap: balance;
}
.lead-copy p { margin: 0 0 1rem; }
.why {
  padding-top: 1rem;
  border-top: 1px solid rgba(32, 32, 29, 0.28);
}
.why strong, .key-fact strong { font-size: 0.78rem; text-transform: uppercase; }
.key-fact {
  display: inline-block;
  margin: 0.25rem 0 1.1rem;
  padding: 0.55rem 0.7rem;
  background: rgba(255, 253, 248, 0.52);
}
.source {
  margin: 0;
  color: var(--muted);
  font-size: 0.76rem;
}
.lead .source,
.lead .source a { color: var(--lead-secondary); }
.lead a:hover,
.lead a:focus-visible { color: var(--lead-hover); }
.lead a:focus-visible {
  outline: 3px solid var(--lead-hover);
  outline-offset: 3px;
}
.sections {
  padding: 0 clamp(1.25rem, 4vw, 3.5rem) 3rem;
}
.section {
  padding: 2.2rem 0 2.5rem;
  border-top: 1px solid var(--ink);
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 1rem;
  margin-bottom: 1.5rem;
}
.section-header h2 {
  margin: 0;
  font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
  font-size: clamp(1.7rem, 3vw, 2.5rem);
  font-weight: 500;
  letter-spacing: -0.025em;
}
.section-count {
  color: var(--muted);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 0.7rem;
  text-transform: uppercase;
}
.story-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
}
.story-card {
  min-width: 0;
  padding: clamp(1.25rem, 3vw, 2rem);
  background: var(--sheet);
}
.story-card:nth-child(3n) { background: var(--sage); }
.story-card h3 {
  margin: 0 0 0.85rem;
  font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
  font-size: clamp(1.35rem, 2.2vw, 1.85rem);
  font-weight: 600;
  letter-spacing: -0.02em;
  line-height: 1.15;
}
.story-card p { margin: 0 0 0.85rem; }
.story-card .why {
  margin-top: 1rem;
  color: #4b4943;
}
.story-card .key-fact { background: var(--wash); }
.footer {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 2rem;
  padding: 2rem clamp(1.25rem, 4vw, 3.5rem);
  background: var(--ink);
  color: #f9f5ec;
}
.footer p { margin: 0; }
.pipeline {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  margin-top: 0.8rem;
}
.pipeline span {
  padding: 0.35rem 0.55rem;
  border: 1px solid #77736b;
  border-radius: 999px;
  color: #d9d3c8;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 0.65rem;
}
.footer-note {
  max-width: 25rem;
  color: #c4beb3;
  font-size: 0.76rem;
  text-align: right;
}
@media (max-width: 900px) {
  .lead {
    grid-template-columns: 1fr;
    gap: 1.5rem;
  }
  .lead h2 { max-width: 18ch; }
}
@media (max-width: 760px) {
  .page { width: min(100% - 1rem, 1120px); margin-top: 0.5rem; }
  .masthead, .opening, .footer { grid-template-columns: 1fr; }
  .issue-meta, .footer-note { text-align: left; }
  .opening { gap: 1.5rem; }
  .story-grid { grid-template-columns: 1fr; }
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
}
"""


def _source(story: Story) -> str:
    url = escape(story.source_url, quote=True)
    label = escape(story.source_label)
    return (
        f'<p class="source">Source · <a href="{url}" rel="noopener noreferrer">'
        f"{label}</a></p>"
    )


def _story_card(story: Story) -> str:
    return (
        '<article class="story-card">'
        '<p class="story-label">Briefed</p>'
        f"<h3>{escape(story.title)}</h3>"
        f"<p>{escape(story.summary)}</p>"
        f'<p class="why"><strong>Why it matters</strong><br>{escape(story.why_it_matters)}</p>'
        f'<p class="key-fact"><strong>Keep</strong> · {escape(story.key_fact)}</p>'
        f"{_source(story)}"
        "</article>"
    )


def _section(section: Section, index: int) -> str:
    count = len(section.stories)
    label = "story" if count == 1 else "stories"
    cards = "".join(_story_card(story) for story in section.stories)
    return (
        f'<section class="section" aria-labelledby="section-{index}">'
        '<div class="section-header">'
        f'<h2 id="section-{index}">{escape(section.name)}</h2>'
        f'<span class="section-count">{count:02d} {label}</span>'
        "</div>"
        f'<div class="story-grid">{cards}</div>'
        "</section>"
    )


def render_html(brief: Brief) -> str:
    """Return byte-for-byte stable HTML for the same validated brief."""

    date_label = (
        f"{brief.edition_date:%A}, {brief.edition_date.day} {brief.edition_date:%B %Y}"
    )
    top_lines = "".join(f"<li>{escape(line)}</li>" for line in brief.top_lines)
    sections = "".join(
        _section(section, index)
        for index, section in enumerate(brief.sections, start=1)
    )
    lead = brief.lead_story

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
        '  <div class="demo-bar">Synthetic demo · no real newsletters or personal data</div>\n'
        '  <main class="page" id="brief">\n'
        '    <header class="masthead">\n'
        "      <div>\n"
        '        <p class="eyebrow">Newsletter brief / public demo</p>\n'
        f"        <h1>{escape(brief.title)}</h1>\n"
        "      </div>\n"
        '      <p class="issue-meta">'
        f"{escape(brief.edition)}<br>{escape(date_label)}<br>"
        f"{brief.read_time_minutes} minute read</p>\n"
        "    </header>\n"
        '    <section class="opening" aria-labelledby="opening-title">\n'
        "      <div>\n"
        '        <p class="section-label" id="opening-title">The through-line</p>\n'
        f'        <p class="opening-note">{escape(brief.opening_note)}</p>\n'
        "      </div>\n"
        '      <aside class="at-a-glance" aria-labelledby="glance-title">\n'
        '        <h2 id="glance-title">At a glance</h2>\n'
        f"        <ol>{top_lines}</ol>\n"
        "      </aside>\n"
        "    </section>\n"
        '    <div class="lead-wrap">\n'
        '      <article class="lead">\n'
        "        <div>\n"
        '          <p class="story-label">Lead story</p>\n'
        f"          <h2>{escape(lead.title)}</h2>\n"
        "        </div>\n"
        '        <div class="lead-copy">\n'
        f"          <p>{escape(lead.summary)}</p>\n"
        f'          <p class="why"><strong>Why it matters</strong><br>{escape(lead.why_it_matters)}</p>\n'
        f'          <p class="key-fact"><strong>Keep</strong> · {escape(lead.key_fact)}</p>\n'
        f"          {_source(lead)}\n"
        "        </div>\n"
        "      </article>\n"
        "    </div>\n"
        f'    <div class="sections">{sections}</div>\n'
        '    <footer class="footer">\n'
        "      <div>\n"
        "        <p><strong>How this page was made</strong></p>\n"
        '        <div class="pipeline" aria-label="Demo architecture">\n'
        "          <span>synthetic inputs</span><span>structured synthesis</span>"
        "<span>schema validation</span><span>deterministic HTML</span>\n"
        "        </div>\n"
        "      </div>\n"
        '      <p class="footer-note">Every name, publication, excerpt and claim in this edition is fictional. '
        "The public repository contains no inbox connection or production personalization logic.</p>\n"
        "    </footer>\n"
        "  </main>\n"
        "</body>\n"
        "</html>\n"
    )
