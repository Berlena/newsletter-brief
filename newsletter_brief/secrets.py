"""Read secrets from the environment or the OS keychain. Never log them."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable

KEYCHAIN_SERVICE = "newsletter-brief"
MAILBOX_ACCOUNT = "mailbox"
LLM_ACCOUNT = "llm"
MAILBOX_ENV = "NEWSLETTER_BRIEF_MAILBOX_PASSWORD"
LLM_API_ENV = "LLM_API_KEY"
LEGACY_API_ENV = "OPENAI_API_KEY"

Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


class SecretError(RuntimeError):
    """Raised when a required secret is missing. The message names the variable only."""


def redact(text: str, secrets: Iterable[str]) -> str:
    """Replace known secret values. Short strings are left alone so logs stay readable."""

    redacted = text
    values = sorted({secret for secret in secrets if secret and len(secret) >= 4}, key=len, reverse=True)
    for secret in values:
        redacted = redacted.replace(secret, "[redacted]")
    return redacted


def _default_runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )


def _keychain_value(account: str, runner: Runner) -> str | None:
    if sys.platform == "darwin":
        argv = [
            "security",
            "find-generic-password",
            "-s",
            KEYCHAIN_SERVICE,
            "-a",
            account,
            "-w",
        ]
    elif shutil.which("secret-tool"):
        argv = [
            "secret-tool",
            "lookup",
            "service",
            KEYCHAIN_SERVICE,
            "account",
            account,
        ]
    else:
        return None
    try:
        result = runner(argv)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    # Keep interior spaces. Drop only the trailing newline the tool adds.
    value = result.stdout.removesuffix("\n")
    if not value:
        return None
    return value


def read_secret(
    env_name: str,
    account: str,
    *,
    runner: Runner | None = None,
) -> str | None:
    """Environment first, then the OS keychain. The value is not logged."""

    from_env = os.environ.get(env_name, "")
    if from_env:
        return from_env
    return _keychain_value(account, runner or _default_runner)


def require_secret(
    env_name: str,
    account: str,
    *,
    runner: Runner | None = None,
) -> str:
    value = read_secret(env_name, account, runner=runner)
    if not value:
        raise SecretError(
            f"{env_name} is not set and was not found in the keychain "
            f"(service {KEYCHAIN_SERVICE}, account {account})"
        )
    return value
