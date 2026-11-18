"""Load the personal-run config. Secrets are rejected if they appear in the file."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from newsletter_brief.figures import SUPPORTED_FIGURE_RE
from newsletter_brief.inbox import _blocked_host

_FORBIDDEN_KEYS = {
    "password",
    "passwd",
    "app_password",
    "api_key",
    "apikey",
    "secret",
    "token",
    "openai_api_key",
    "llm_api_key",
    "mailbox_password",
}
_SECRET_VALUE = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")
_DEFAULT_FIGURES = ("eur-usd", "eur-gbp", "btc-usd", "eth-usd")
_KNOWN_SECTIONS = {
    "mailbox",
    "senders",
    "interests",
    "figures",
    "output",
    "delivery",
    "limits",
    "llm",
    "sections",
    "feeds",
    "articles",
    "memory",
    "edition",
}
_DAY_WORDS = {"weekday", "sat", "sun", "weekend"}


class ConfigError(ValueError):
    """Raised when config.toml is missing a field or contains a secret."""


@dataclass(frozen=True, slots=True)
class MailboxConfig:
    host: str
    port: int
    user: str
    folder: str
    hours: int
    unread_only: bool = True


@dataclass(frozen=True, slots=True)
class SectionConfig:
    name: str
    folder: str
    hours: int
    days: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FeedSource:
    url: str
    section: str
    hours: int
    max_entries: int


@dataclass(frozen=True, slots=True)
class ArticleConfig:
    enabled: bool
    max_articles: int
    timeout_seconds: int
    max_bytes: int


@dataclass(frozen=True, slots=True)
class MemoryConfig:
    path: Path
    days: int


@dataclass(frozen=True, slots=True)
class DeliveryConfig:
    enabled: bool
    smtp_host: str
    smtp_port: int
    to: str


@dataclass(frozen=True, slots=True)
class AppConfig:
    mailbox: MailboxConfig
    senders: tuple[str, ...]
    topics: tuple[str, ...]
    figures: tuple[str, ...]
    output_path: Path
    title: str
    delivery: DeliveryConfig
    max_messages: int
    max_chars_per_message: int
    max_total_chars: int
    llm_base_url: str | None = None
    llm_model: str | None = None
    sender_mode: str = "allow"
    sections: tuple[SectionConfig, ...] = ()
    feeds: tuple[FeedSource, ...] = ()
    articles: ArticleConfig | None = None
    memory: MemoryConfig | None = None
    fact_count: int = 5
    max_cards: int = 3
    max_items_per_section: int = 8
    input_per_million: float | None = None
    output_per_million: float | None = None
    small_model: str | None = None
    relevance_min: int = 40


def _text(value: Any, path: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{path} must be text")
    cleaned = value.strip()
    if not cleaned:
        raise ConfigError(f"{path} must not be empty")
    if len(cleaned) > maximum:
        raise ConfigError(f"{path} must be at most {maximum} characters")
    if _SECRET_VALUE.search(cleaned):
        raise ConfigError(f"{path} looks like a secret. Put secrets in the environment or the keychain.")
    return cleaned


def _whole(value: Any, path: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{path} must be a whole number")
    if not minimum <= value <= maximum:
        raise ConfigError(f"{path} must be between {minimum} and {maximum}")
    return value


def _reject_forbidden(value: Any, path: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).casefold() in _FORBIDDEN_KEYS:
                raise ConfigError(
                    f"{path}.{key} is not allowed in the config file. "
                    "Put the mailbox app password in NEWSLETTER_BRIEF_MAILBOX_PASSWORD "
                    "or the keychain, and the model key in LLM_API_KEY or the keychain."
                )
            _reject_forbidden(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_forbidden(item, f"{path}[{index}]")
    elif isinstance(value, str) and _SECRET_VALUE.search(value):
        raise ConfigError(
            f"{path} looks like a secret. Put secrets in the environment or the keychain."
        )


def _sender(value: str, path: str) -> str:
    item = _text(value, path, maximum=200).casefold()
    if any(char.isspace() for char in item):
        raise ConfigError(f"{path} must be one address or one domain")
    if item.startswith("@") or item.endswith("@"):
        raise ConfigError(f"{path} is not a usable address or domain")
    if "@" in item:
        local, _, domain = item.partition("@")
        if not local or "." not in domain:
            raise ConfigError(f"{path} must be a full address")
        return item
    if "." not in item:
        raise ConfigError(f"{path} must be a domain such as news.example")
    return item


def load_config(path: Path) -> AppConfig:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"could not read {path}") from exc
    try:
        raw = tomllib.loads(raw_text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("config must be a table")
    _reject_forbidden(raw, "config")

    unknown = sorted(set(raw) - _KNOWN_SECTIONS - {"title"})
    if unknown:
        raise ConfigError("unknown config fields: " + ", ".join(unknown))

    title = _text(raw.get("title", "Your Morning Brief"), "title", maximum=80)
    mailbox_raw = raw.get("mailbox")
    if not isinstance(mailbox_raw, dict):
        raise ConfigError("mailbox must be a table")
    hours = mailbox_raw.get("hours", 24)
    unread_only = mailbox_raw.get("unread_only", True)
    if not isinstance(unread_only, bool):
        raise ConfigError("mailbox.unread_only must be true or false")
    extra_mailbox = set(mailbox_raw) - {"host", "port", "user", "folder", "hours", "unread_only"}
    if extra_mailbox:
        raise ConfigError("unknown fields in mailbox: " + ", ".join(sorted(extra_mailbox)))
    mailbox = MailboxConfig(
        host=_text(mailbox_raw.get("host"), "mailbox.host", maximum=200),
        port=_whole(mailbox_raw.get("port", 993), "mailbox.port", minimum=1, maximum=65535),
        user=_text(mailbox_raw.get("user"), "mailbox.user", maximum=200),
        folder=_text(mailbox_raw.get("folder", "INBOX"), "mailbox.folder", maximum=200),
        hours=_whole(hours, "mailbox.hours", minimum=1, maximum=168),
        unread_only=unread_only,
    )
    if "://" in mailbox.host or " " in mailbox.host:
        raise ConfigError("mailbox.host must be a hostname, without https://")

    sections = _sections(raw.get("sections"), default_hours=mailbox.hours)
    sender_mode, senders = _senders(raw.get("senders"), mailbox, sections)

    topics: tuple[str, ...] = ()
    if "interests" in raw:
        interests = raw["interests"]
        if not isinstance(interests, dict):
            raise ConfigError("interests must be a table")
        topic_list = interests.get("topics", [])
        if not isinstance(topic_list, list):
            raise ConfigError("interests.topics must be a list")
        if len(topic_list) > 12:
            raise ConfigError("interests.topics must contain at most 12 items")
        topics = tuple(
            _text(item, f"interests.topics[{index}]", maximum=80)
            for index, item in enumerate(topic_list)
        )

    figures = _DEFAULT_FIGURES
    if "figures" in raw:
        figures_raw = raw["figures"]
        if not isinstance(figures_raw, dict) or "show" not in figures_raw:
            raise ConfigError("figures.show must be a list of figure ids")
        show = figures_raw["show"]
        if not isinstance(show, list):
            raise ConfigError("figures.show must be a list")
        if len(show) > 12:
            raise ConfigError("figures.show must contain at most 12 figures")
        parsed: list[str] = []
        for index, item in enumerate(show):
            figure_id = _text(item, f"figures.show[{index}]", maximum=20).casefold()
            if SUPPORTED_FIGURE_RE.fullmatch(figure_id) is None:
                raise ConfigError(
                    f"figures.show[{index}] must be eur-xxx, btc-usd or eth-usd"
                )
            parsed.append(figure_id)
        figures = tuple(parsed)

    output_raw = raw.get("output")
    if not isinstance(output_raw, dict):
        raise ConfigError("output.path is required")
    output_text = _text(output_raw.get("path"), "output.path", maximum=300)
    output_path = Path(output_text)
    if not output_path.is_absolute():
        output_path = (path.parent / output_path).resolve()

    delivery = _delivery(raw.get("delivery"), mailbox.user)
    llm_base_url, llm_model, small_model, price_in, price_out, relevance_min = _llm(raw.get("llm"))
    limits = raw.get("limits", {})
    if not isinstance(limits, dict):
        raise ConfigError("limits must be a table")
    extra_limits = set(limits) - {
        "max_messages",
        "max_chars_per_message",
        "max_total_chars",
        "max_items_per_section",
    }
    if extra_limits:
        raise ConfigError("unknown fields in limits: " + ", ".join(sorted(extra_limits)))
    fact_count, max_cards = _edition(raw.get("edition"))
    feeds = _feeds(raw.get("feeds"), default_hours=mailbox.hours)
    articles = _articles(raw.get("articles"))
    memory = _memory(raw.get("memory"), config_path=path)
    return AppConfig(
        mailbox=mailbox,
        senders=senders,
        topics=topics,
        figures=figures,
        output_path=output_path,
        title=title,
        delivery=delivery,
        max_messages=_whole(
            limits.get("max_messages", 30), "limits.max_messages", minimum=1, maximum=100
        ),
        max_chars_per_message=_whole(
            limits.get("max_chars_per_message", 20_000),
            "limits.max_chars_per_message",
            minimum=500,
            maximum=100_000,
        ),
        max_total_chars=_whole(
            limits.get("max_total_chars", 60_000),
            "limits.max_total_chars",
            minimum=1_000,
            maximum=200_000,
        ),
        llm_base_url=llm_base_url,
        llm_model=llm_model,
        sender_mode=sender_mode,
        sections=sections,
        feeds=feeds,
        articles=articles,
        memory=memory,
        fact_count=fact_count,
        max_cards=max_cards,
        max_items_per_section=_whole(
            limits.get("max_items_per_section", 8),
            "limits.max_items_per_section",
            minimum=1,
            maximum=40,
        ),
        input_per_million=price_in,
        output_per_million=price_out,
        small_model=small_model,
        relevance_min=relevance_min,
    )


def _price(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{path} must be a number")
    if value < 0 or value > 1000:
        raise ConfigError(f"{path} must be between 0 and 1000")
    return float(value)


def _llm(
    value: Any,
) -> tuple[str | None, str | None, str | None, float | None, float | None, int]:
    if value is None:
        return None, None, None, None, None, 40
    if not isinstance(value, dict):
        raise ConfigError("llm must be a table")
    extra = set(value) - {
        "base_url",
        "model",
        "small_model",
        "input_per_million",
        "output_per_million",
        "relevance_min",
    }
    if extra:
        raise ConfigError("unknown fields in llm: " + ", ".join(sorted(extra)))
    base_url = None
    model = None
    small_model = None
    if "base_url" in value and str(value.get("base_url") or "").strip():
        base_url = _text(value.get("base_url"), "llm.base_url", maximum=300)
        if not base_url.startswith(("http://", "https://")):
            raise ConfigError("llm.base_url must start with http:// or https://")
    if "model" in value and str(value.get("model") or "").strip():
        model = _text(value.get("model"), "llm.model", maximum=120)
    if "small_model" in value and str(value.get("small_model") or "").strip():
        small_model = _text(value.get("small_model"), "llm.small_model", maximum=120)
    price_in = None
    price_out = None
    if "input_per_million" in value or "output_per_million" in value:
        if "input_per_million" not in value or "output_per_million" not in value:
            raise ConfigError("llm.input_per_million and llm.output_per_million must be set together")
        price_in = _price(value.get("input_per_million"), "llm.input_per_million")
        price_out = _price(value.get("output_per_million"), "llm.output_per_million")
    relevance = _whole(
        value.get("relevance_min", 40), "llm.relevance_min", minimum=0, maximum=100
    )
    return base_url, model, small_model, price_in, price_out, relevance


def _is_inbox(folder: str) -> bool:
    return folder.casefold() == "inbox"


def _day_filter(value: Any, path: str) -> tuple[str, ...]:
    if value is None:
        return ()
    raw_items = [value] if isinstance(value, str) else value
    if not isinstance(raw_items, list):
        raise ConfigError(f'{path} must be "weekday", "sat", "sun", or "weekend"')
    parsed: list[str] = []
    for index, item in enumerate(raw_items):
        token = _text(item, f"{path}[{index}]", maximum=20).casefold()
        if token not in _DAY_WORDS:
            raise ConfigError(f'{path} must be "weekday", "sat", "sun", or "weekend"')
        if token == "weekend":
            parsed.extend(["sat", "sun"])
        else:
            parsed.append(token)
    return tuple(dict.fromkeys(parsed))


def _sections(value: Any, *, default_hours: int) -> tuple[SectionConfig, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ConfigError("sections must be a list of tables")
    if len(value) > 12:
        raise ConfigError("sections must contain at most 12 folders")
    sections: list[SectionConfig] = []
    names: set[str] = set()
    for index, item in enumerate(value):
        path = f"sections[{index}]"
        if not isinstance(item, dict):
            raise ConfigError(f"{path} must be a table")
        extra = set(item) - {"name", "folder", "hours", "days"}
        if extra:
            raise ConfigError(f"unknown fields in {path}: " + ", ".join(sorted(extra)))
        name = _text(item.get("name"), f"{path}.name", maximum=70)
        if name.casefold() in names:
            raise ConfigError(f"{path}.name must be unique")
        names.add(name.casefold())
        sections.append(
            SectionConfig(
                name=name,
                folder=_text(item.get("folder"), f"{path}.folder", maximum=200),
                hours=_whole(
                    item.get("hours", default_hours), f"{path}.hours", minimum=1, maximum=336
                ),
                days=_day_filter(item.get("days"), f"{path}.days"),
            )
        )
    return tuple(sections)


def _senders(
    value: Any,
    mailbox: MailboxConfig,
    sections: tuple[SectionConfig, ...],
) -> tuple[str, tuple[str, ...]]:
    if not isinstance(value, dict):
        raise ConfigError("senders.allow must list at least one address or domain")
    extra = set(value) - {"allow", "mode"}
    if extra:
        raise ConfigError("unknown fields in senders: " + ", ".join(sorted(extra)))
    mode = "allow"
    if "mode" in value:
        mode = _text(value.get("mode"), "senders.mode", maximum=20).casefold()
    if mode not in {"allow", "folder"}:
        raise ConfigError('senders.mode must be "allow" or "folder"')
    active = [section.folder for section in sections] or [mailbox.folder]
    if mode == "folder":
        if "allow" in value:
            raise ConfigError(
                'senders.allow is not used when mode is "folder". '
                'Remove allow, or set mode to "allow".'
            )
        if any(_is_inbox(folder) for folder in active):
            raise ConfigError(
                'senders.mode "folder" cannot be used when a folder is INBOX. '
                "Choose a label or folder that contains only newsletters. "
                "Folder mode reads every message in that folder."
            )
        return "folder", ()
    if "allow" not in value:
        raise ConfigError("senders.allow must list at least one address or domain")
    allow = value["allow"]
    if not isinstance(allow, list) or not allow:
        raise ConfigError("senders.allow must list at least one address or domain")
    senders = tuple(_sender(item, f"senders.allow[{index}]") for index, item in enumerate(allow))
    return "allow", senders


def _https_feed(value: Any, path: str) -> str:
    url = _text(value, path, maximum=500)
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ConfigError(f"{path} must be an https URL")
    if parsed.username or parsed.password:
        raise ConfigError(f"{path} must not contain credentials")
    if _blocked_host(parsed.hostname):
        raise ConfigError(f"{path} must be a public https URL")
    return url


def _feeds(value: Any, *, default_hours: int) -> tuple[FeedSource, ...]:
    if value is None:
        return ()
    if not isinstance(value, dict):
        raise ConfigError("feeds must be a table")
    extra = set(value) - {"urls", "hours", "max_entries", "sources"}
    if extra:
        raise ConfigError("unknown fields in feeds: " + ", ".join(sorted(extra)))
    hours = _whole(value.get("hours", default_hours), "feeds.hours", minimum=1, maximum=336)
    max_entries = _whole(value.get("max_entries", 8), "feeds.max_entries", minimum=1, maximum=40)
    sources: list[FeedSource] = []
    urls = value.get("urls", [])
    if not isinstance(urls, list):
        raise ConfigError("feeds.urls must be a list")
    for index, item in enumerate(urls):
        sources.append(
            FeedSource(
                url=_https_feed(item, f"feeds.urls[{index}]"),
                section="",
                hours=hours,
                max_entries=max_entries,
            )
        )
    nested = value.get("sources", [])
    if not isinstance(nested, list):
        raise ConfigError("feeds.sources must be a list")
    for index, item in enumerate(nested):
        path = f"feeds.sources[{index}]"
        if not isinstance(item, dict):
            raise ConfigError(f"{path} must be a table")
        item_extra = set(item) - {"url", "section", "hours", "max_entries"}
        if item_extra:
            raise ConfigError(f"unknown fields in {path}: " + ", ".join(sorted(item_extra)))
        section = ""
        if "section" in item and str(item.get("section") or "").strip():
            section = _text(item.get("section"), f"{path}.section", maximum=70)
        sources.append(
            FeedSource(
                url=_https_feed(item.get("url"), f"{path}.url"),
                section=section,
                hours=_whole(item.get("hours", hours), f"{path}.hours", minimum=1, maximum=336),
                max_entries=_whole(
                    item.get("max_entries", max_entries),
                    f"{path}.max_entries",
                    minimum=1,
                    maximum=40,
                ),
            )
        )
    if len(sources) > 20:
        raise ConfigError("feeds must contain at most 20 URLs")
    return tuple(sources)


def _articles(value: Any) -> ArticleConfig:
    if value is None:
        return ArticleConfig(enabled=False, max_articles=4, timeout_seconds=8, max_bytes=500_000)
    if not isinstance(value, dict):
        raise ConfigError("articles must be a table")
    extra = set(value) - {"enabled", "max_articles", "timeout_seconds", "max_bytes"}
    if extra:
        raise ConfigError("unknown fields in articles: " + ", ".join(sorted(extra)))
    enabled = value.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ConfigError("articles.enabled must be true or false")
    return ArticleConfig(
        enabled=enabled,
        max_articles=_whole(
            value.get("max_articles", 4), "articles.max_articles", minimum=1, maximum=20
        ),
        timeout_seconds=_whole(
            value.get("timeout_seconds", 8),
            "articles.timeout_seconds",
            minimum=1,
            maximum=30,
        ),
        max_bytes=_whole(
            value.get("max_bytes", 500_000),
            "articles.max_bytes",
            minimum=10_000,
            maximum=2_000_000,
        ),
    )


def _memory(value: Any, *, config_path: Path) -> MemoryConfig:
    path_text = "output/state.json"
    days = 2
    if value is not None:
        if not isinstance(value, dict):
            raise ConfigError("memory must be a table")
        extra = set(value) - {"path", "days"}
        if extra:
            raise ConfigError("unknown fields in memory: " + ", ".join(sorted(extra)))
        if "path" in value:
            path_text = _text(value.get("path"), "memory.path", maximum=300)
        days = _whole(value.get("days", 2), "memory.days", minimum=1, maximum=30)
    path = Path(path_text)
    if not path.is_absolute():
        path = (config_path.parent / path).resolve()
    return MemoryConfig(path=path, days=days)


def _edition(value: Any) -> tuple[int, int]:
    if value is None:
        return 5, 3
    if not isinstance(value, dict):
        raise ConfigError("edition must be a table")
    extra = set(value) - {"facts", "max_cards"}
    if extra:
        raise ConfigError("unknown fields in edition: " + ", ".join(sorted(extra)))
    facts = _whole(value.get("facts", 5), "edition.facts", minimum=1, maximum=8)
    cards = _whole(value.get("max_cards", 3), "edition.max_cards", minimum=1, maximum=6)
    return facts, cards


def _delivery(value: Any, mailbox_user: str) -> DeliveryConfig:
    if value is None:
        return DeliveryConfig(enabled=False, smtp_host="", smtp_port=587, to=mailbox_user)
    if not isinstance(value, dict):
        raise ConfigError("delivery must be a table")
    enabled = value.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ConfigError("delivery.enabled must be true or false")
    smtp_host = ""
    smtp_port = 587
    recipient = mailbox_user
    if "smtp_host" in value:
        smtp_host = _text(value.get("smtp_host"), "delivery.smtp_host", maximum=200)
    if "smtp_port" in value:
        smtp_port = _whole(value.get("smtp_port"), "delivery.smtp_port", minimum=1, maximum=65535)
    if "to" in value:
        recipient = _text(value.get("to"), "delivery.to", maximum=200)
    if enabled and not smtp_host:
        raise ConfigError("delivery.smtp_host is required when delivery is enabled")
    if enabled and "@" not in recipient:
        raise ConfigError("delivery.to must be the address that receives the brief")
    return DeliveryConfig(
        enabled=enabled, smtp_host=smtp_host, smtp_port=smtp_port, to=recipient
    )
