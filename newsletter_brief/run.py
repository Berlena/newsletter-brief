"""Build one brief from a mailbox or a folder of .eml files."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from newsletter_brief.articles import fetch_articles
from newsletter_brief.config import AppConfig
from newsletter_brief.context_lookup import lookup_summaries, names_from_items
from newsletter_brief.feeds import FeedError, FeedRequest, read_feeds
from newsletter_brief.figures import fetch_figures
from newsletter_brief.inbox import (
    FolderRead,
    default_head,
    read_eml_directory,
    read_imap,
)
from newsletter_brief.mailer import send_brief
from newsletter_brief.models import Brief, NewsletterFeed, NewsletterItem, Section, Story
from newsletter_brief.prefilter import dedupe_links, finish_prefilter
from newsletter_brief.provider import ProviderError, resolve_provider, resolve_small_model
from newsletter_brief.renderer import render_html
from newsletter_brief.secrets import (
    MAILBOX_ACCOUNT,
    MAILBOX_ENV,
    redact,
    require_secret,
)
from newsletter_brief.statefile import (
    StateError,
    drop_seen,
    load_memory,
    local_day,
    remember,
    save_memory,
)
from newsletter_brief.synthesis import (
    SynthesisError,
    Usage,
    distill_items,
    format_usage,
    live_edition_synthesis,
)

LOGGER = logging.getLogger("newsletter_brief")


class RunError(RuntimeError):
    """Raised for a personal-run failure whose message has already been redacted."""


class AlreadySent(RunError):
    """Today's brief was already emailed. The run stops before any model call."""


def _empty_brief(config: AppConfig, moment: datetime, figures: tuple[Any, ...]) -> Brief:
    hours = config.mailbox.hours
    if config.sender_mode == "folder":
        opening = "Nothing in the selected folder arrived in this window."
        why = (
            f"No messages in the selected folder arrived in the last {hours} hours, "
            "so there is nothing to add context to."
        )
        remembered = (
            "No newsletters arrived",
            "The folder was read",
            "Figures below come from the data sources",
        )
        lead_summary = f"Nothing in the selected folder arrived in the last {hours} hours."
        lead_why = "The brief reads every message in the folder you named."
        lead_fact = "Folder was read"
        section_summary = "That folder had no messages in this window."
        section_why = "Only the folder you named is read."
        section_fact = "Other folders were left untouched"
    else:
        opening = "Nothing from your sender list arrived in this window."
        why = (
            f"No newsletters from your list arrived in the last {hours} hours, "
            "so there is nothing to add context to."
        )
        remembered = (
            "No newsletters arrived",
            "The sender list was applied",
            "Figures below come from the data sources",
        )
        lead_summary = f"Nothing from the sender list arrived in the last {hours} hours."
        lead_why = "The brief only reads the senders you listed."
        lead_fact = "Sender list applied"
        section_summary = "Mail from other senders was not opened."
        section_why = "Only the addresses and domains in your list are read."
        section_fact = "Other mail was left untouched"
    return Brief(
        synthetic=False,
        title=config.title,
        edition="Morning brief",
        edition_date=moment.date(),
        read_time_minutes=1,
        opening_note=opening,
        why_this_matters=why,
        top_lines=remembered,
        lead_story=Story(
            title="No newsletters arrived",
            summary=lead_summary,
            why_it_matters=lead_why,
            key_fact=lead_fact,
            source_label="",
            source_url="",
        ),
        sections=(
            Section(
                name="Inbox",
                stories=(
                    Story(
                        title="No matching mail",
                        summary=section_summary,
                        why_it_matters=section_why,
                        key_fact=section_fact,
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
    force: bool = False,
    feed_get: Any | None = None,
    article_get: Any | None = None,
    context_get: Any | None = None,
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
            force=force,
            feed_get=feed_get,
            article_get=article_get,
            context_get=context_get,
        )
    except AlreadySent:
        raise
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
    force: bool,
    feed_get: Any | None,
    article_get: Any | None,
    context_get: Any | None,
) -> Path:
    def note(message: str) -> None:
        LOGGER.info(redact(message, secrets))

    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    edition_date = moment.date()
    today = local_day(moment)
    memory_path = config.memory.path if config.memory is not None else config.output_path.with_name("state.json")
    memory_days = config.memory.days if config.memory is not None else 2
    if send and config.delivery.enabled and not force:
        if load_memory(memory_path).already_sent(today):
            raise AlreadySent(
                f"Already sent today ({today.isoformat()}, local time). "
                "No mail was read and no model was called."
            )

    accept_all = config.sender_mode == "folder"
    folders = tuple(
        FolderRead(
            folder=section.folder,
            hours=section.hours,
            name=section.name,
            days=section.days,
            unread_only=config.mailbox.unread_only,
        )
        for section in config.sections
    )
    if eml_dir is not None:
        collected = read_eml_directory(
            eml_dir,
            allowlist=config.senders,
            hours=config.mailbox.hours,
            max_chars=config.max_chars_per_message,
            max_total_chars=config.max_total_chars,
            now=moment,
            head=default_head,
            accept_all=accept_all,
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
            accept_all=accept_all,
            unread_only=config.mailbox.unread_only,
            folders=folders or None,
        )
    feed_items: list[NewsletterItem] = []
    if config.feeds:
        try:
            feed_items = read_feeds(
                tuple(
                    FeedRequest(
                        url=source.url,
                        section=source.section,
                        hours=source.hours,
                        max_entries=source.max_entries,
                    )
                    for source in config.feeds
                ),
                max_chars=config.max_chars_per_message,
                now=moment,
                get=feed_get,
            )
        except FeedError as exc:
            raise RunError(str(exc)) from None
    raw_items = list(collected.items) + feed_items
    deduped = dedupe_links(raw_items)
    articles = config.articles
    if articles is not None and articles.enabled and deduped:
        deduped = fetch_articles(
            deduped,
            max_articles=articles.max_articles,
            timeout=articles.timeout_seconds,
            max_bytes=articles.max_bytes,
            max_chars=config.max_chars_per_message,
            get=article_get,
        )
    prepared = finish_prefilter(
        deduped,
        max_chars=config.max_chars_per_message,
        max_per_section=config.max_items_per_section,
    )
    try:
        memory = load_memory(memory_path)
    except StateError as exc:
        raise RunError(str(exc)) from None
    prepared = drop_seen(prepared, memory, today=today, days=memory_days)
    trimmed_items, trimmed = _trim_total(prepared, config.max_total_chars)
    note(
        f"messages kept: {collected.kept_messages}; "
        f"stories: {len(collected.items)}; "
        f"skipped: {collected.skipped_senders}"
    )
    note(f"items before prefilter: {len(raw_items)}; after: {len(trimmed_items)}")
    numbered = tuple(
        replace(item, item_id=f"m{index}-l1")
        for index, item in enumerate(trimmed_items, start=1)
    )

    figures = fetch_figures(config.figures, get=figure_get) if config.figures else ()
    input_note = ""
    if trimmed or collected.trimmed:
        input_note = "Some stories were left out because the text cap was reached."

    usage = Usage()
    called_model = False
    if not numbered:
        brief = replace(_empty_brief(config, moment, figures), input_note=input_note)
    else:
        provider = resolve_provider(
            config_base_url=config.llm_base_url,
            config_model=config.llm_model,
            runner=keychain_runner,
        )
        if provider.api_key:
            secrets.append(provider.api_key)
        small = resolve_small_model(config.small_model)
        model_items = numbered
        if small:
            called_model = True
            model_items = distill_items(
                numbered,
                api_key=provider.api_key or "",
                model=small,
                base_url=provider.base_url,
                interests=config.topics,
                relevance_min=config.relevance_min,
                max_chars=config.max_chars_per_message,
                client=client,
                usage=usage,
            )
            note(f"items after the small model: {len(model_items)}")
        if not model_items:
            brief = replace(_empty_brief(config, moment, figures), input_note=input_note)
        else:
            called_model = True
            feed = NewsletterFeed(
                synthetic=False,
                edition_date=edition_date,
                items=model_items,
            )
            context_sources = ()
            if config.context is not None and config.context.lookup:
                context_sources = tuple(
                    source.as_dict()
                    for source in lookup_summaries(
                        names_from_items(model_items),
                        timeout=config.context.timeout_seconds,
                        max_lookups=config.context.max_lookups,
                        get=context_get,
                    )
                )
            brief = live_edition_synthesis(
                feed,
                api_key=provider.api_key or "",
                model=provider.model,
                base_url=provider.base_url,
                title=config.title,
                interests=config.topics,
                client=client,
                fact_count=config.fact_count,
                max_cards=config.max_cards,
                usage=usage,
                context_sources=context_sources,
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
    if called_model:
        print(
            format_usage(
                usage,
                input_per_million=config.input_per_million,
                output_per_million=config.output_per_million,
            )
        )

    sent = False
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
        sent = True
        note("sent the brief")
    if send:
        titles = [brief.lead_story.title]
        titles.extend(story.title for section in brief.sections for story in section.stories)
        remember(
            memory,
            list(numbered),
            titles,
            today=today,
            days=memory_days,
            sent=sent,
        )
        save_memory(memory_path, memory)
    return config.output_path


def _trim_total(items: list[NewsletterItem], max_total_chars: int) -> tuple[list[NewsletterItem], bool]:
    kept: list[NewsletterItem] = []
    used = 0
    trimmed = False
    for item in items:
        if len(kept) >= 40 or used + len(item.excerpt) > max_total_chars:
            trimmed = True
            break
        used += len(item.excerpt)
        kept.append(item)
    return kept, trimmed
