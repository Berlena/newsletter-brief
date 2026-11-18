"""Which model provider a run talks to. The key never comes from the config file."""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from newsletter_brief.secrets import Runner, read_secret

DEFAULT_BASE_URL = "https://api.openai.com/v1"
LLM_BASE_ENV = "LLM_BASE_URL"
LLM_API_ENV = "LLM_API_KEY"
LLM_MODEL_ENV = "LLM_MODEL"
LLM_SMALL_ENV = "LLM_SMALL_MODEL"
LEGACY_API_ENV = "OPENAI_API_KEY"
LEGACY_MODEL_ENV = "OPENAI_MODEL"
LLM_ACCOUNT = "llm"
# The OpenAI client refuses an empty key. Local servers ignore this value.
LOCAL_PLACEHOLDER = "local"


class ProviderError(ValueError):
    """Raised when the provider settings are incomplete. The message has no secrets."""


@dataclass(frozen=True, slots=True)
class ProviderSettings:
    base_url: str
    model: str
    api_key: str | None

    @property
    def sends_openai_flags(self) -> bool:
        return is_openai_base(self.base_url)

    def client_key(self) -> str:
        return self.api_key or LOCAL_PLACEHOLDER


def _hostname(url: str) -> str:
    host = (urlsplit(url).hostname or "").casefold().rstrip(".").strip("[]")
    return host


def is_openai_base(url: str) -> bool:
    return _hostname(url) == "api.openai.com"


def is_local_base(url: str) -> bool:
    host = _hostname(url)
    if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"} or host.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private or address.is_link_local


def resolve_provider(
    *,
    config_base_url: str | None = None,
    config_model: str | None = None,
    runner: Runner | None = None,
) -> ProviderSettings:
    """Environment wins over the config file. The default base URL is OpenAI."""

    base_url = (
        os.environ.get(LLM_BASE_ENV, "").strip()
        or (config_base_url or "").strip()
        or DEFAULT_BASE_URL
    )
    if not base_url.startswith(("http://", "https://")):
        raise ProviderError(f"{LLM_BASE_ENV} must start with http:// or https://")
    if base_url.startswith("http://") and not is_local_base(base_url):
        raise ProviderError(f"{LLM_BASE_ENV} must use https, except for a model on your own machine")
    parsed = urlsplit(base_url)
    if not parsed.hostname:
        raise ProviderError(f"{LLM_BASE_ENV} needs a hostname")

    model = (
        os.environ.get(LLM_MODEL_ENV, "").strip()
        or os.environ.get(LEGACY_MODEL_ENV, "").strip()
        or (config_model or "").strip()
    )
    api_key = os.environ.get(LLM_API_ENV, "").strip() or os.environ.get(LEGACY_API_ENV, "").strip()
    if not api_key:
        found = read_secret(LLM_API_ENV, LLM_ACCOUNT, runner=runner)
        api_key = found or ""

    missing: list[str] = []
    if not model:
        missing.append(LLM_MODEL_ENV)
    if not api_key and not is_local_base(base_url):
        missing.append(LLM_API_ENV)
    if missing:
        raise ProviderError("LLM settings are missing: " + ", ".join(missing))

    return ProviderSettings(
        base_url=base_url.rstrip("/"),
        model=model,
        api_key=api_key or None,
    )


def resolve_small_model(config_model: str | None = None) -> str | None:
    """Optional cheaper model. The environment wins. Unset means one model call."""

    value = os.environ.get(LLM_SMALL_ENV, "").strip() or (config_model or "").strip()
    return value or None
