# Publication boundary

This repository was built as a public evaluation surface with fresh Git history.
The implementation is new and the examples are synthetic. No file from the
private Daily Brief repository was copied into this repository.

## Explicit whitelist

Only these concepts and components are approved for publication:

- the four-stage architecture: newsletter inputs → structured synthesis →
  validation → deterministic HTML;
- a small Python CLI with separate offline and live demo paths;
- synthetic newsletter fixtures and a prepared synthetic response;
- a deliberately limited public prompt and JSON Schema;
- a dependency-free renderer for a static, responsive demo;
- tests for validation, escaping, grounding, missing variables and rendering;
- a CI workflow that uses a mocked AI response and no credentials;
- the generated static page, screenshot and public-facing documentation.

Every file in the repository must fit one of those categories.
`PUBLIC_MANIFEST.txt` enumerates the exact publishable file set, and the audit
script fails if a tracked file is added without an explicit manifest change.

## Explicit exclusions

The public repository does not contain:

- Gmail, IMAP, OAuth, mailbox labels, email addresses or connection code;
- real subscriptions, newsletter excerpts or source metadata;
- production prompts, ranking, de-duplication or personalization logic;
- private schedules, repository history, internal URLs or secrets;
- sending, inbox mutation or subscription-management code;
- multi-user infrastructure, analytics, billing or hosted-product code.

## Guardrails in code

- Input JSON must set `synthetic` to `true`.
- Structured output must also set `synthetic` to `true`.
- Every rendered source URL must match one supplied in the input fixture.
- The renderer accepts a validated model and escapes text and link attributes.
- Offline generation makes no network request and needs no environment variables.
- CI injects a fake Responses API client; it never uses an API key.
- CI compares the exact tracked file set with `PUBLIC_MANIFEST.txt` and scans
  public text for email addresses, secret-shaped values and unexpected URL hosts.

The source-visible demo is intentionally not a distributable version of the
private system or of any future hosted service.
