"""Load the personal-run config. Secrets are rejected if they appear in the file."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from newsletter_brief.figures import SUPPORTED_FIGURE_RE

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
}


class ConfigError(ValueError):
    """Raised when config.toml is missing a field or contains a secret."""


@dataclass(frozen=True, slots=True)
class MailboxConfig:
    host: str
    port: int
    user: str
    folder: str
    hours: int


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
    mailbox = MailboxConfig(
        host=_text(mailbox_raw.get("host"), "mailbox.host", maximum=200),
        port=_whole(mailbox_raw.get("port", 993), "mailbox.port", minimum=1, maximum=65535),
        user=_text(mailbox_raw.get("user"), "mailbox.user", maximum=200),
        folder=_text(mailbox_raw.get("folder", "INBOX"), "mailbox.folder", maximum=200),
        hours=_whole(hours, "mailbox.hours", minimum=1, maximum=168),
    )
    if "://" in mailbox.host or " " in mailbox.host:
        raise ConfigError("mailbox.host must be a hostname, without https://")

    senders_raw = raw.get("senders")
    if not isinstance(senders_raw, dict) or "allow" not in senders_raw:
        raise ConfigError("senders.allow must list at least one address or domain")
    allow = senders_raw["allow"]
    if not isinstance(allow, list) or not allow:
        raise ConfigError("senders.allow must list at least one address or domain")
    extra_sender_keys = set(senders_raw) - {"allow"}
    if extra_sender_keys:
        raise ConfigError("unknown fields in senders: " + ", ".join(sorted(extra_sender_keys)))
    senders = tuple(_sender(item, f"senders.allow[{index}]") for index, item in enumerate(allow))

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
    llm_base_url, llm_model = _llm(raw.get("llm"))
    limits = raw.get("limits", {})
    if not isinstance(limits, dict):
        raise ConfigError("limits must be a table")
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
    )


def _llm(value: Any) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    if not isinstance(value, dict):
        raise ConfigError("llm must be a table")
    extra = set(value) - {"base_url", "model"}
    if extra:
        raise ConfigError("unknown fields in llm: " + ", ".join(sorted(extra)))
    base_url = None
    model = None
    if "base_url" in value and str(value.get("base_url") or "").strip():
        base_url = _text(value.get("base_url"), "llm.base_url", maximum=300)
        if not base_url.startswith(("http://", "https://")):
            raise ConfigError("llm.base_url must start with http:// or https://")
    if "model" in value and str(value.get("model") or "").strip():
        model = _text(value.get("model"), "llm.model", maximum=120)
    return base_url, model


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
