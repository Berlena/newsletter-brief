# Newsletter Brief

> A source-visible demo of the system I built to turn an overloaded newsletter
> inbox into one useful daily brief.

[Live synthetic demo](https://berlena.github.io/newsletter-brief/) ·
[Publication boundary](PUBLICATION_BOUNDARY.md)

![A production-faithful synthetic Newsletter Brief edition with indigo section rules, an editorial serif and a five-item retention card](docs/screenshot.png)

The words and sources in the screenshot are fictional. The presentation mirrors
the private email: a compact editorial column, five things to remember, one big
story, indigo section rules, and expandable headlines for skim-first reading.

I subscribed to useful newsletters faster than I could read them. The result was
an inbox full of good material and no reliable way to turn it into a view of the
day. I built a private system that separates collection, synthesis and
presentation, then gives me one brief I can actually use.

I am an operator, not a software engineer by training. I taught myself to build
with agentic coding tools because this was an operating problem where a small,
purpose-built system was more useful than another spreadsheet or process. The
private version has been in daily use since June 2026.

This repository is a deliberately limited public demo. It shows the architecture
and a runnable implementation without exposing inbox access, real subscriptions,
production prompts or future product infrastructure.

## How it works

```text
synthetic newsletter inputs
          ↓
structured AI synthesis
          ↓
strict schema + source grounding
          ↓
deterministic HTML renderer
          ↓
one static brief
```

Newsletter inputs and presentation never blur together. Synthesis produces a
validated data object; the renderer owns every layout and styling decision. That
separation makes the output testable, predictable and safe to escape.

## Run the offline demo

Python 3.12 is the only requirement. The offline path uses synthetic inputs and a
committed prepared response. It installs nothing, reads no environment variables
and makes no network request.

```bash
python -m newsletter_brief demo --offline --output dist/index.html
```

Open `dist/index.html` in a browser. The generated file should match
[`docs/index.html`](docs/index.html) byte for byte.

## Run live synthesis

Live mode sends the same synthetic fixture to the OpenAI Responses API with a
strict JSON Schema. You choose the model and supply your own credentials.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[live]"

export OPENAI_API_KEY="your-api-key"
export OPENAI_MODEL="gpt-5.6-luna"
python -m newsletter_brief demo --live --output dist/index.html
```

The example uses `gpt-5.6-luna`, a compatible non-fine-tuned model that supports
Structured Outputs. You can replace it with another compatible model available
to your project.

The API key is read from the environment and is never written to disk. The demo
also sets API response storage to false. API usage may incur charges on your
OpenAI account.

## What is automated, and why

- **Structured synthesis** turns several excerpts into one predictable object.
  A schema keeps content generation separate from layout.
- **Source grounding** rejects any output link that was not present in the
  supplied inputs.
- **Deterministic rendering** makes the page reproducible and keeps HTML,
  typography and responsive behavior under normal code review.
- **Offline generation and mocked CI** make the core path testable without
  credentials, network access or paid API calls.

The public demo does not fetch email, schedule jobs or send a brief. Those
capabilities are private because they would expose personal data and production
infrastructure rather than clarify the core idea.

## Test

```bash
python -m unittest discover -s tests -v
python scripts/audit_public_payload.py
python -m newsletter_brief demo --offline --output dist/index.html
cmp dist/index.html docs/index.html
```

The tests cover schema validation, source grounding, HTML escaping,
deterministic rendering, missing environment variables and a mocked live API
response. The publication audit also compares every tracked path with the
explicit [`PUBLIC_MANIFEST.txt`](PUBLIC_MANIFEST.txt) whitelist and scans text
files for accidental email addresses, secret-shaped values and unexpected URL
hosts.

## Privacy and the public/private line

Every publication, company, person, excerpt, number and link in the demo is
fictional. The reserved `.example` domains cannot be mistaken for real sources.
There are no mailbox credentials, labels, addresses, subscriptions or genuine
newsletter contents here.

The private system has additional collection, scheduling, ranking,
personalization and delivery behavior. None of that code or repository history
is included. See [PUBLICATION_BOUNDARY.md](PUBLICATION_BOUNDARY.md) for the
explicit whitelist and exclusions.

I am considering whether a hosted version could be useful to other newsletter
readers. This repository is an evaluation surface, not that product's
infrastructure.

## Copyright

Copyright © 2026 Lena Schaefer. This source is published for evaluation and
portfolio purposes; no license is granted at this stage.
