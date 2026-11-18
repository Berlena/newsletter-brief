"""Build one brief from a mailbox or a folder of .eml files."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from newsletter_brief.config import AppConfig
from newsletter_brief.figures import fetch_figures
from newsletter_brief.inbox import default_head, read_eml_directory, read_imap
from newsletter_brief.mailer import send_brief
from newsletter_brief.models import Brief, NewsletterFeed, Section, Story
from newsletter_brief.provider import ProviderError, resolve_provider
from newsletter_brief.renderer import render_html
from newsletter_brief.secrets import (
    MAILBOX_ACCOUNT,
    MAILBOX_ENV,
    redact,
    require_secret,
)
from newsletter_brief.synthesis import SynthesisError, live_edition_synthesis

LOGGER = logging.getLogger("newsletter_brief")


class RunError(RuntimeError):
    """Raised for a personal-run failure whose message has already been redacted."""


def _empty_brief(config: AppConfig, moment: datetime, figures: tuple[Any, ...]) -> Brief:
    hours = config.mailbox.hours
    return Brief(
        synthetic=False,
        title=config.title,
        edition="Morning brief",
        edition_date=moment.date(),
        read_time_minutes=1,
        opening_note="Nothing from your sender list arrived in this window.",
        why_this_matters=(
            f"No newsletters from your list arrived in the last {hours} hours, "
            "so there is nothing to add context to."
        ),
        top_lines=(
            "No newsletters arrived",
            "The sender list was applied",
            "Figures below come from the data sources",
        ),
        lead_story=Story(
            title="No newsletters arrived",
            summary=f"Nothing from the sender list arrived in the last {hours} hours.",
            why_it_matters="The brief only reads the senders you listed.",
            key_fact="Sender list applied",
            source_label="",
            source_url="",
        ),
        sections=(
            Section(
                name="Inbox",
                stories=(
                    Story(
                        title="No matching mail",
                        summary="Mail from other senders was not opened.",
                        why_it_matters="Only the addresses and domains in your list are read.",
                        key_fact="Other mail was left untouched",
                        source_label="",
                        source_url="",
                    ),
                ),
            ),
        ),
        figures=tuple(figures),
        public_demo=False,
    )


def run_brief(
    config: AppConfig,
    *,
    eml_dir: Path | None = None,
    send: bool = True,
    client: Any | None = None,
    figure_get: Any | None = None,
    smtp_factory: Any | None = None,
    now: datetime | None = None,
    connector: Any | None = None,
    keychain_runner: Any | None = None,
) -> Path:
    secrets: list[str] = []
    try:
        return _run(
            config,
            secrets,
            eml_dir=eml_dir,
            send=send,
            client=client,
            figure_get=figure_get,
            smtp_factory=smtp_factory,
            now=now,
            connector=connector,
            keychain_runner=keychain_runner,
        )
    except Exception as exc:
        message = redact(str(exc), secrets)
        if type(exc) in {SynthesisError, RunError, ProviderError}:
            raise type(exc)(message) from None
        raise RunError(message) from None


def _run(
    config: AppConfig,
    secrets: list[str],
    *,
    eml_dir: Path | None,
    send: bool,
    client: Any | None,
    figure_get: Any | None,
    smtp_factory: Any | None,
    now: datetime | None,
    connector: Any | None,
    keychain_runner: Any | None,
) -> Path:
    def note(message: str) -> None:
        LOGGER.info(redact(message, secrets))

    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    edition_date = moment.date()

    if eml_dir is not None:
        collected = read_eml_directory(
            eml_dir,
            allowlist=config.senders,
            hours=config.mailbox.hours,
            max_chars=config.max_chars_per_message,
            max_total_chars=config.max_total_chars,
            now=moment,
            head=default_head,
        )
    else:
        password = require_secret(MAILBOX_ENV, MAILBOX_ACCOUNT, runner=keychain_runner)
        secrets.append(password)
        collected = read_imap(
            host=config.mailbox.host,
            port=config.mailbox.port,
            user=config.mailbox.user,
            password=password,
            folder=config.mailbox.folder,
            hours=config.mailbox.hours,
            allowlist=config.senders,
            max_messages=config.max_messages,
            max_chars=config.max_chars_per_message,
            max_total_chars=config.max_total_chars,
            now=moment,
            connector=connector,
            head=default_head,
        )
    note(
        f"messages kept: {collected.kept_messages}; "
        f"stories: {len(collected.items)}; "
        f"skipped: {collected.skipped_senders}"
    )

    figures = fetch_figures(config.figures, get=figure_get) if config.figures else ()
    input_note = ""
    if collected.trimmed:
        input_note = "Some stories were left out because the text cap was reached."

    if not collected.items:
        brief = replace(_empty_brief(config, moment, figures), input_note=input_note)
    else:
        provider = resolve_provider(
            config_base_url=config.llm_base_url,
            config_model=config.llm_model,
            runner=keychain_runner,
        )
        if provider.api_key:
            secrets.append(provider.api_key)
        feed = NewsletterFeed(
            synthetic=False,
            edition_date=edition_date,
            items=collected.items,
        )
        brief = live_edition_synthesis(
            feed,
            api_key=provider.api_key or "",
            model=provider.model,
            base_url=provider.base_url,
            title=config.title,
            interests=config.topics,
            client=client,
        )
        brief = replace(
            brief,
            title=config.title,
            figures=figures,
            public_demo=False,
            input_note=input_note,
        )

    html = render_html(brief)
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    # Write only after the link check has passed. A failed check raises above.
    config.output_path.write_text(html, encoding="utf-8")
    note(f"wrote brief to {config.output_path}")

    if send and config.delivery.enabled:
        password = require_secret(MAILBOX_ENV, MAILBOX_ACCOUNT, runner=keychain_runner)
        secrets.append(password)
        send_brief(
            host=config.delivery.smtp_host,
            port=config.delivery.smtp_port,
            user=config.mailbox.user,
            password=password,
            recipient=config.delivery.to,
            subject=config.title,
            html=html,
            client_factory=smtp_factory,
        )
        note("sent the brief")
    return config.output_path
