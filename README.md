# Newsletter Brief

**One rule if you let AI summarize your newsletters: a link only makes it into
the summary if it was actually in the source. Anything else gets rejected.**

I'd rather miss a story than read one the model made up. This repo is a small,
runnable version of the morning brief I built for myself in June 2026, with
fictional newsletters, so you can see how that rule works in code.

[Live synthetic demo](https://berlena.github.io/newsletter-brief/) ·
[Publication boundary](PUBLICATION_BOUNDARY.md) · MIT licensed

![A synthetic Newsletter Brief edition: five things to remember, one big story and expandable headlines](docs/screenshot.png)

Every publication, person, excerpt and link in the screenshot is fictional.

## Why the rule

I subscribe to more newsletters than I have time to read. Summarizing them with
a model is the easy part. The part I didn't trust was the links: a summary can
sound right and point to a story that was never in my inbox.

So the model doesn't get the last word. After it writes the brief, plain code
compares every link in the output with the links in the inputs. If one doesn't
match, the build stops and nothing gets rendered. The model can still get a
summary wrong, so I still click through on anything I'm going to repeat. But it
can't invent a source.

You can watch it fail on purpose. `demo/ungrounded_response.json` is the same
brief with one invented link:

```bash
python -m newsletter_brief demo --offline \
  --prepared-response demo/ungrounded_response.json \
  --output dist/ungrounded.html
```

```text
error: structured output contains source URLs absent from the input feed: https://invented-source.example/a-story-nobody-sent-you
```

No HTML file is written. CI runs this on every push and fails if that brief
ever renders.

## How it works

```text
synthetic newsletter inputs
          ↓
structured AI synthesis (strict JSON Schema)
          ↓
validation + link check against the inputs
          ↓
deterministic HTML renderer
          ↓
one static brief
```

The model only fills in a data object. Code checks it, and the renderer owns
every layout decision. That keeps the output testable and the HTML escaped.

## Run the offline demo

Needs Python 3.12 or newer and nothing else. The offline path uses the
synthetic inputs and a committed prepared response. It installs nothing, reads
no environment variables and makes no network requests.

```bash
python -m newsletter_brief demo --offline --output dist/index.html
```

Open `dist/index.html` in a browser. It should match
[`docs/index.html`](docs/index.html) byte for byte.

## Run live synthesis

Live mode sends the same synthetic inputs to the OpenAI Responses API with a
strict JSON Schema. You bring your own key and pick the model.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[live]"

export OPENAI_API_KEY="your-api-key"
export OPENAI_MODEL="a-model-that-supports-structured-outputs"
python -m newsletter_brief demo --live --output dist/index.html
```

Any model on your project that supports Structured Outputs should work. The key
is read from the environment and never written to disk, and the request sets
response storage to false. API calls cost money on your OpenAI account.

## What's public and what isn't

The public demo doesn't read email, run on a schedule or send anything. My
private version does, and that part stays private because it would expose my
inbox and setup without making the idea any clearer.

There are no mailbox credentials, subscriptions or real newsletter content
here. Every file in the repo is listed in
[`PUBLIC_MANIFEST.txt`](PUBLIC_MANIFEST.txt), and an audit script fails if
anything else gets added or if it finds an email address, a secret-shaped
string or an unexpected URL. See [PUBLICATION_BOUNDARY.md](PUBLICATION_BOUNDARY.md).

## Test

```bash
python -m unittest discover -s tests -v
python scripts/audit_public_payload.py
python -m newsletter_brief demo --offline --output dist/index.html
cmp dist/index.html docs/index.html
```

The tests cover schema validation, the link check, HTML escaping, deterministic
rendering, missing environment variables and a mocked live API response.

## License

MIT. See [LICENSE](LICENSE). Copyright (c) 2026 Lena Schaefer.
