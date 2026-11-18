"""Command-line entry point for the public newsletter brief demo."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from newsletter_brief.config import ConfigError, load_config
from newsletter_brief.inputs import InputError, load_feed
from newsletter_brief.provider import DEFAULT_BASE_URL, ProviderError, resolve_provider
from newsletter_brief.renderer import render_html
from newsletter_brief.run import RunError, run_brief
from newsletter_brief.schema import SchemaError
from newsletter_brief.secrets import LEGACY_API_ENV, LLM_API_ENV, MAILBOX_ENV, redact
from newsletter_brief.synthesis import (
    SynthesisError,
    live_synthesis,
    prepared_synthesis,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUTS = PROJECT_ROOT / "demo" / "newsletters.json"
DEFAULT_PREPARED_RESPONSE = PROJECT_ROOT / "demo" / "prepared_response.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="newsletter_brief",
        description="Generate the synthetic public newsletter brief demo.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Generate a static synthetic brief.")
    mode = demo.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--offline",
        action="store_true",
        help="Use the committed prepared response; makes no network requests.",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="Synthesize the synthetic inputs with the configured model provider.",
    )
    demo.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path for the generated HTML file.",
    )
    demo.add_argument(
        "--inputs",
        type=Path,
        default=DEFAULT_INPUTS,
        help="Synthetic newsletter JSON (defaults to demo/newsletters.json).",
    )
    demo.add_argument(
        "--prepared-response",
        type=Path,
        default=DEFAULT_PREPARED_RESPONSE,
        help="Prepared structured response used by --offline.",
    )
    run = commands.add_parser(
        "run",
        help="Read your own inbox and write a brief.",
    )
    run.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to config.toml. Copy config.example.toml and edit it.",
    )
    run.add_argument(
        "--eml-dir",
        type=Path,
        default=None,
        help="Read this folder of .eml files instead of the mailbox.",
    )
    run.add_argument(
        "--no-send",
        action="store_true",
        help="Write the HTML file and do not send email.",
    )
    return parser


def _secret_names() -> tuple[str, ...]:
    return (LLM_API_ENV, LEGACY_API_ENV, MAILBOX_ENV)


def _demo(args: argparse.Namespace) -> int:
    try:
        feed = load_feed(args.inputs)
        if args.offline:
            brief = prepared_synthesis(args.prepared_response, feed)
            mode_label = "offline"
        else:
            provider = resolve_provider()
            brief = live_synthesis(
                feed,
                api_key=provider.api_key or "",
                model=provider.model,
                base_url=provider.base_url or DEFAULT_BASE_URL,
            )
            mode_label = f"live / {provider.model}"

        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_html(brief), encoding="utf-8")
    except (InputError, SchemaError, SynthesisError, ProviderError, OSError) as exc:
        secret_values = [
            os.environ[name] for name in _secret_names() if os.environ.get(name)
        ]
        print(f"error: {redact(str(exc), secret_values)}", file=sys.stderr)
        return 2

    print(f"Wrote {mode_label} synthetic demo to {output}")
    return 0


def _known_secrets() -> list[str]:
    return [os.environ[name] for name in _secret_names() if os.environ.get(name)]


def _personal_run(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config)
        output = run_brief(
            config,
            eml_dir=args.eml_dir,
            send=not args.no_send,
        )
    except (ConfigError, SynthesisError, ProviderError, RunError, OSError) as exc:
        print(f"error: {redact(str(exc), _known_secrets())}", file=sys.stderr)
        return 2
    print(f"Wrote brief to {output}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "run":
        return _personal_run(args)
    return _demo(args)
