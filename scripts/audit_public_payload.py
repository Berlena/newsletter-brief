"""Fail closed when the staged public payload drifts beyond its whitelist."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "PUBLIC_MANIFEST.txt"
EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w.-])", re.IGNORECASE
)
URL_PATTERN = re.compile(r"https://[A-Za-z0-9.-]+(?::\d+)?(?:/[^\s\"'<>)\]]*)?")
SECRET_PATTERNS = {
    "OpenAI-style secret": re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    "GitHub token": re.compile(r"\b(?:ghp_|github_pat_)[A-Za-z0-9_]{16,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
# Vendor setup pages and the keyless market-data sources. Newsletter content
# still has to use a .example host. Anything else fails the audit.
ALLOWED_PUBLIC_HOSTS = {
    "github.com",
    "berlena.github.io",
    "support.google.com",
    "support.apple.com",
    "support.microsoft.com",
    "www.fastmail.help",
    "www.ecb.europa.eu",
    "api.coingecko.com",
    "www.coingecko.com",
    "api.openai.com",
    "developers.openai.com",
    "api.mistral.ai",
    "docs.mistral.ai",
    "docs.ollama.com",
    "lmstudio.ai",
    "en.wikipedia.org",
    "openrouter.ai",
    "huggingface.co",
    "lmarena.ai",
    "artificialanalysis.ai",
}
_EXAMPLE_EMAIL_DOMAINS = {"example", "example.com", "example.org", "example.net"}


def _email_allowed(address: str) -> bool:
    domain = address.rsplit("@", 1)[-1].casefold().rstrip(".")
    return domain in _EXAMPLE_EMAIL_DOMAINS or domain.endswith(".example")


def _tracked_paths() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return {entry.decode("utf-8") for entry in result.stdout.split(b"\0") if entry}


def _manifest_paths() -> set[str]:
    return {
        line.strip()
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def _is_allowed_url(url: str) -> bool:
    try:
        host = (urlsplit(url.rstrip(".,;:")).hostname or "").casefold()
    except ValueError:
        return False
    return host in ALLOWED_PUBLIC_HOSTS or host.endswith(".example")


def audit() -> list[str]:
    errors: list[str] = []
    tracked = _tracked_paths()
    expected = _manifest_paths()

    for path in sorted(tracked - expected):
        errors.append(f"tracked path is not whitelisted: {path}")
    for path in sorted(expected - tracked):
        errors.append(f"whitelisted path is not tracked: {path}")

    license_file = ROOT / "LICENSE"
    if "LICENSE" not in tracked or not license_file.read_text(
        encoding="utf-8"
    ).startswith("MIT License"):
        errors.append("LICENSE must be tracked and contain the MIT license")

    for path in sorted(tracked):
        name = Path(path).name.casefold()
        if name.startswith("license") and path != "LICENSE":
            errors.append(f"unexpected license file: {path}")

        data = (ROOT / path).read_bytes()
        if b"\0" in data:
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            errors.append(f"tracked non-binary file is not UTF-8: {path}")
            continue

        for match in EMAIL_PATTERN.finditer(text):
            if not _email_allowed(match.group(0)):
                errors.append(f"email address found in {path}: {match.group(0)}")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                errors.append(f"{label} found in {path}")
        for match in URL_PATTERN.finditer(text):
            url = match.group(0)
            if not _is_allowed_url(url):
                errors.append(f"unexpected URL host in {path}: {url}")

    return errors


def main() -> int:
    try:
        errors = audit()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"public payload audit could not run: {exc}", file=sys.stderr)
        return 2

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Public payload audit passed.")
    print(f"Whitelisted tracked files: {len(_tracked_paths())}")
    print("Email addresses: 0")
    print("Secret-shaped values: 0")
    print("Unexpected URL hosts: 0")
    print("License: MIT (LICENSE)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
