# Publication boundary

This repository was built as a public project with fresh Git history.
The implementation is new and the checked-in examples are synthetic. No file
from the private Daily Brief repository was copied into this repository.

## Explicit whitelist

Approved for publication:

- the pipeline: newsletter inputs, structured synthesis, a link check,
  deterministic HTML;
- a command that reads your own mailbox, or a folder of `.eml` files, and
  writes one HTML file;
- a config example with no passwords in it;
- a model call that uses any OpenAI-compatible endpoint, chosen by settings;
- foreign-exchange and crypto figures fetched by code from public sources
  that do not need a key;
- optional email of the finished page back to you;
- schedule examples that are not switched on;
- synthetic newsletter fixtures, a prepared synthetic response, and a
  deliberately broken response with one invented link;
- a public prompt and JSON Schema;
- a dependency-free renderer for a static page;
- tests, including mocked mailbox, model, and mail-sending calls;
- a CI workflow that uses a mocked model response and no credentials;
- the generated demo page, screenshots, and the docs;
- the MIT license in `LICENSE`.

Every file in the repository must fit one of those categories.
`PUBLIC_MANIFEST.txt` enumerates the exact publishable file set, and the audit
script fails if a tracked file is added without an explicit manifest change.

## Explicit exclusions

The public repository does not contain:

- a filled-in `config.toml`, an app password, or a model key;
- real newsletter excerpts, real `.eml` files, or a generated brief from a
  real mailbox;
- OAuth client secrets or a sign-in flow;
- production ranking or personalization from the private system;
- multi-user infrastructure, analytics, billing, or a hosted product.

`config.toml`, `output/`, and `.eml` files are gitignored. A real run reads
mail when you start it and does not commit that mail.

## Guardrails in code

- The demo input and the demo output must set `synthetic` to true. The real
  run does not use that flag, and it does not write mail into the repo.
- Every link the model returns must match a link in the inputs, including
  the why-this-matters text and each event. CI feeds in a response with one
  invented link and fails if it renders.
- Figures are attached after the model returns. The schema the model fills
  has no figures field. A failed fetch is the word "unavailable".
- Passwords and API keys are rejected if they are placed in the config file.
- The renderer escapes text and link attributes.
- Offline demo generation makes no network request and needs no environment
  variables.
- CI injects a fake model client. It never uses an API key.
- CI compares the tracked files with `PUBLIC_MANIFEST.txt` and scans public
  text for real email addresses, secret-shaped values, and unexpected URL
  hosts. Reserved `.example` addresses are allowed in the docs and tests.

The demo is MIT licensed. It shows the pattern. Your mailbox contents are
not part of the repository.
