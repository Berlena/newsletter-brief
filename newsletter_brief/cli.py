"""Command-line entry point for the public newsletter brief demo."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from newsletter_brief.inputs import InputError, load_feed
from newsletter_brief.renderer import render_html
from newsletter_brief.schema import SchemaError
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
        help="Synthesize the synthetic inputs with the OpenAI Responses API.",
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
    return parser


def _live_environment() -> tuple[str, str]:
    missing = [
        name for name in ("OPENAI_API_KEY", "OPENAI_MODEL") if not os.getenv(name)
    ]
    if missing:
        joined = ", ".join(missing)
        raise SynthesisError(f"live mode requires environment variables: {joined}")
    return os.environ["OPENAI_API_KEY"], os.environ["OPENAI_MODEL"]


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        feed = load_feed(args.inputs)
        if args.offline:
            brief = prepared_synthesis(args.prepared_response, feed)
            mode_label = "offline"
        else:
            api_key, model = _live_environment()
            brief = live_synthesis(feed, api_key=api_key, model=model)
            mode_label = f"live / {model}"

        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_html(brief), encoding="utf-8")
    except (InputError, SchemaError, SynthesisError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"Wrote {mode_label} synthetic demo to {output}")
    return 0
