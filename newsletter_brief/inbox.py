"""Read newsletters from IMAP or a folder of .eml files. Read-only."""

from __future__ import annotations

import base64
import imaplib
import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email import message_from_bytes
from email.message import Message
from email.utils import parsedate_to_datetime, parseaddr
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit
import ipaddress

from newsletter_brief.models import NewsletterItem
from newsletter_brief.prefilter import strip_boilerplate

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_TRACKING_KEYS = {
    "fbclid",
    "gclid",
    "gclsrc",
    "dclid",
    "igshid",
    "mc_eid",
    "mc_cid",
    "mkt_tok",
    "_hsenc",
    "_hsmi",
    "vero_id",
    "vero_conv",
    "oly_enc_id",
    "oly_anon_id",
    "mbid",
    "ml_subscriber",
    "ml_subscriber_hash",
    "ns_mchannel",
    "ns_source",
    "ns_campaign",
    "nr_email_referer",
}
_UNWRAP_KEYS = {"url", "u", "redirect", "dest", "destination", "target"}
_GENERIC_TITLES = {
    "click here",
    "read more",
    "here",
    "link",
    "this",
    "open",
    "continue reading",
    "read on",
    "learn more",
    "view in browser",
    "view online",
    "view this email",
}
_SKIP_MARKERS = ("unsubscribe", "preferences", "email-protection", "manage-subscription")
_REDIRECT_SUFFIXES = ("list-manage.com", "sendgrid.net", "mandrillapp.com", "emltrk.com")
_PLAIN_URL = re.compile(r"https://[^\s<>\"']+")
_MAX_RAW_BYTES = 2_000_000
_MAX_CANDIDATES_PER_MESSAGE = 8
_MAX_ITEMS = 40

Connector = Callable[[str, int], "imaplib.IMAP4"]
HeadGetter = Callable[[str], str | None]


class InboxError(RuntimeError):
    """Raised when the mailbox cannot be read. The message does not include secrets."""


@dataclass(frozen=True, slots=True)
class CollectedMail:
    items: tuple[NewsletterItem, ...]
    kept_messages: int
    skipped_senders: int
    trimmed: bool


def imap_since(moment: datetime) -> str:
    return f"{moment.day:02d}-{_MONTHS[moment.month - 1]}-{moment.year}"


def sender_allowed(address: str, allowlist: Sequence[str]) -> bool:
    addr = address.casefold().strip()
    if "@" not in addr:
        return False
    domain = addr.split("@", 1)[1]
    if not domain:
        return False
    for entry in allowlist:
        item = entry.casefold().strip()
        if not item:
            continue
        if "@" in item:
            if addr == item:
                return True
        elif domain == item or domain.endswith("." + item):
            return True
    return False


def _blocked_host(hostname: str) -> bool:
    host = hostname.casefold().rstrip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _is_tracking(key: str) -> bool:
    lowered = key.casefold()
    return lowered.startswith("utm_") or lowered in _TRACKING_KEYS


def clean_url(url: str, depth: int = 0) -> str | None:
    """Drop tracking parameters and unwrap an embedded https link. No network."""

    if depth > 2:
        return None
    candidate = url.strip().strip("<>").strip()
    if not candidate:
        return None
    parsed = urlsplit(candidate)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    if parsed.username or parsed.password or _blocked_host(parsed.hostname):
        return None
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    for key, value in pairs:
        if key.casefold() in _UNWRAP_KEYS:
            inner = unquote(value).strip()
            if inner.startswith("https://"):
                return clean_url(inner, depth + 1)
    kept = [(key, value) for key, value in pairs if not _is_tracking(key)]
    query = urlencode(kept, doseq=True)
    fragment = parsed.fragment
    if not fragment or fragment.casefold().startswith("utm"):
        fragment = ""
    cleaned = urlunsplit(("https", parsed.netloc, parsed.path or "/", query, fragment))
    if len(cleaned) > 500:
        return None
    return cleaned


def _looks_like_redirect(url: str) -> bool:
    host = (urlsplit(url).hostname or "").casefold()
    return any(host == suffix or host.endswith("." + suffix) for suffix in _REDIRECT_SUFFIXES)


def resolve_redirect(url: str, head: HeadGetter | None) -> str:
    """Follow one redirect only when the host is a known tracker and the call is cheap."""

    if head is None or not _looks_like_redirect(url):
        return url
    try:
        target = head(url)
    except Exception:
        return url
    if not target:
        return url
    cleaned = clean_url(target)
    return cleaned or url


def default_head(url: str) -> str | None:
    """One HEAD request, two-second timeout. Returns a single https Location and does not follow it."""

    import urllib.request

    captured: dict[str, str] = {}

    class _OneHop(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
            captured["url"] = newurl
            return None

    opener = urllib.request.build_opener(_OneHop)
    request = urllib.request.Request(
        url, method="HEAD", headers={"User-Agent": "newsletter-brief"}
    )
    try:
        response = opener.open(request, timeout=2)
        response.close()
    except Exception:
        pass
    target = captured.get("url", "")
    host = urlsplit(target).hostname or ""
    if target.startswith("https://") and not _blocked_host(host):
        return target
    return None


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.text_parts: list[str] = []
        self._ignore = 0
        self._href: str | None = None
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        if name in {"script", "style", "noscript"}:
            self._ignore += 1
            return
        if self._ignore:
            return
        if name == "br":
            self.text_parts.append("\n")
        if name == "a" and self._href is None:
            attr = {key.lower(): value or "" for key, value in attrs}
            self._href = attr.get("href", "")
            self._chunks = []

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name in {"script", "style", "noscript"} and self._ignore:
            self._ignore -= 1
            return
        if name == "a" and self._href is not None:
            text = " ".join("".join(self._chunks).split())
            self.links.append((self._href, text))
            self._href = None
        if name in {"p", "div", "li", "h1", "h2", "h3", "tr", "section"}:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignore:
            return
        if self._href is not None:
            self._chunks.append(data)
        self.text_parts.append(data)


def _skip_link(href: str, text: str) -> bool:
    blob = f"{href} {text}".casefold()
    return any(marker in blob for marker in _SKIP_MARKERS)


def _title_for(text: str, subject: str) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) >= 8 and cleaned.casefold() not in _GENERIC_TITLES:
        return cleaned[:180]
    return subject[:180] or cleaned[:180]


def extract_links(html: str, plain: str, *, subject: str, max_chars: int) -> tuple[tuple[str, str, str], ...]:
    parser = _LinkParser()
    parser.feed(html[: max_chars * 4])
    parser.close()
    visible = " ".join("".join(parser.text_parts).split())
    if not visible:
        visible = " ".join(plain.split())
    visible = strip_boilerplate(visible)
    excerpt = visible[:max_chars]
    if subject and subject not in excerpt[: len(subject) + 2]:
        excerpt = f"{subject}\n{excerpt}"[:max_chars]

    found: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    def add(raw_url: str, text: str) -> None:
        if _skip_link(raw_url, text):
            return
        cleaned = clean_url(raw_url)
        if cleaned is None or cleaned in seen:
            return
        title = _title_for(text, subject)
        if not title:
            return
        seen.add(cleaned)
        found.append((cleaned, title, excerpt))

    for href, text in parser.links:
        add(href, text)
    for match in _PLAIN_URL.findall(plain[: max_chars * 4]):
        add(match, "")
    return tuple(found[:_MAX_CANDIDATES_PER_MESSAGE])


def _decode_part(part: Message) -> str:
    payload = part.get_payload(decode=True) or b""
    if len(payload) > 500_000:
        payload = payload[:500_000]
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def message_bodies(message: Message) -> tuple[str, str]:
    plain_parts: list[str] = []
    html_parts: list[str] = []
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        if part.get_content_maintype() == "multipart":
            continue
        disposition = (part.get("Content-Disposition") or "").casefold()
        if "attachment" in disposition:
            continue
        content_type = part.get_content_type()
        if content_type == "text/html":
            html_parts.append(_decode_part(part))
        elif content_type == "text/plain":
            plain_parts.append(_decode_part(part))
    return "\n".join(plain_parts), "\n".join(html_parts)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def message_when(message: Message, fallback: datetime | None = None) -> datetime | None:
    raw = message.get("Date")
    if raw:
        try:
            return _as_utc(parsedate_to_datetime(raw))
        except (TypeError, ValueError, IndexError, OverflowError):
            pass
    return _as_utc(fallback)


def items_from_message(
    raw: bytes,
    *,
    allowlist: Sequence[str],
    max_chars: int,
    fallback_when: datetime | None = None,
    head: HeadGetter | None = None,
    accept_all: bool = False,
    section: str = "",
) -> tuple[str, datetime | None, tuple[NewsletterItem, ...]] | None:
    """Return (address, when, items) or None when the sender is not allowed."""

    if len(raw) > _MAX_RAW_BYTES:
        return None
    message = message_from_bytes(raw)
    _name, address = parseaddr(message.get("From", ""))
    if not accept_all and not sender_allowed(address, allowlist):
        return None
    when = message_when(message, fallback_when)
    display = parseaddr(message.get("From", ""))[0].strip() or address.split("@", 1)[-1]
    subject = " ".join((message.get("Subject") or "").split())[:180]
    plain, html = message_bodies(message)
    links = extract_links(html, plain, subject=subject or display, max_chars=max_chars)
    items: list[NewsletterItem] = []
    for index, (url, title, excerpt) in enumerate(links, start=1):
        resolved = resolve_redirect(url, head)
        items.append(
            NewsletterItem(
                item_id="",
                publication=display[:120],
                topic=(subject or display)[:80],
                title=title[:180],
                excerpt=excerpt[:max_chars],
                source_url=resolved,
                section=section,
                origin="mail",
                published_at=when,
            )
        )
        if index >= _MAX_CANDIDATES_PER_MESSAGE:
            break
    return address, when, tuple(items)


def _within_hours(when: datetime | None, *, now: datetime, hours: int) -> bool:
    if when is None:
        return False
    return when >= now - timedelta(hours=hours)


def _assign_ids(collected: list[tuple[datetime | None, tuple[NewsletterItem, ...]]], *, max_total_chars: int) -> CollectedMail:
    collected.sort(key=lambda item: item[0] or datetime.min.replace(tzinfo=timezone.utc))
    items: list[NewsletterItem] = []
    used = 0
    trimmed = False
    message_count = 0
    for _when, group in collected:
        if not group:
            continue
        message_count += 1
        for offset, item in enumerate(group, start=1):
            if len(items) >= _MAX_ITEMS or used + len(item.excerpt) > max_total_chars:
                trimmed = True
                break
            used += len(item.excerpt)
            items.append(
                NewsletterItem(
                    item_id=f"m{message_count}-l{offset}",
                    publication=item.publication,
                    topic=item.topic,
                    title=item.title,
                    excerpt=item.excerpt,
                    source_url=item.source_url,
                    section=item.section,
                    origin=item.origin,
                    published_at=item.published_at,
                )
            )
        if trimmed:
            break
    return CollectedMail(
        items=tuple(items),
        kept_messages=message_count if not trimmed else message_count,
        skipped_senders=0,
        trimmed=trimmed,
    )


def read_eml_directory(
    path: Path,
    *,
    allowlist: Sequence[str],
    hours: int,
    max_chars: int,
    max_total_chars: int,
    now: datetime | None = None,
    head: HeadGetter | None = None,
    accept_all: bool = False,
    section: str = "",
) -> CollectedMail:
    if not path.is_dir():
        raise InboxError(f"{path} is not a folder of .eml files")
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    grouped: list[tuple[datetime | None, tuple[NewsletterItem, ...]]] = []
    skipped = 0
    for file in sorted(path.glob("*.eml")):
        parsed = items_from_message(
            file.read_bytes(),
            allowlist=allowlist,
            max_chars=max_chars,
            head=head,
            accept_all=accept_all,
            section=section,
        )
        if parsed is None:
            skipped += 1
            continue
        _address, when, items = parsed
        if not _within_hours(when, now=moment, hours=hours):
            continue
        grouped.append((when, items))
    collected = _assign_ids(grouped, max_total_chars=max_total_chars)
    return CollectedMail(
        items=collected.items,
        kept_messages=collected.kept_messages,
        skipped_senders=skipped,
        trimmed=collected.trimmed,
    )


def _default_connector(host: str, port: int) -> imaplib.IMAP4_SSL:
    return imaplib.IMAP4_SSL(host, port, timeout=30)


def encode_modified_utf7(text: str) -> str:
    """Encode a mailbox name as IMAP modified UTF-7 (RFC 3501)."""

    pieces: list[str] = []
    pending: list[str] = []

    def flush() -> None:
        if not pending:
            return
        raw = "".join(pending).encode("utf-16-be")
        token = base64.b64encode(raw).decode("ascii").rstrip("=").replace("/", ",")
        pieces.append("&" + token + "-")
        pending.clear()

    for char in text:
        code = ord(char)
        if char == "&":
            flush()
            pieces.append("&-")
        elif 0x20 <= code <= 0x7E:
            flush()
            pieces.append(char)
        else:
            pending.append(char)
    flush()
    return "".join(pieces)


def decode_modified_utf7(text: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(text):
        if text[index] != "&":
            out.append(text[index])
            index += 1
            continue
        end = text.find("-", index)
        if end < 0:
            raise ValueError("truncated modified UTF-7")
        token = text[index + 1 : end]
        index = end + 1
        if token == "":
            out.append("&")
            continue
        padded = token.replace(",", "/")
        padded += "=" * ((4 - len(padded) % 4) % 4)
        out.append(base64.b64decode(padded).decode("utf-16-be"))
    return "".join(out)


def _is_imap_atom(value: str) -> bool:
    if not value:
        return False
    for char in value:
        code = ord(char)
        if code <= 0x1F or code >= 0x7F or char in ' (){%*"\\]':
            return False
    return True


def imap_mailbox_arg(folder: str) -> str:
    """Mailbox argument for EXAMINE. imaplib sends this string unchanged.

    ``select(arg, readonly=True)`` is the EXAMINE command. Names that are not
    atoms are quoted. Non-ASCII names are modified UTF-7 first.
    """

    encoded = encode_modified_utf7(folder)
    if _is_imap_atom(encoded):
        return encoded
    escaped = encoded.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def section_active(days: Sequence[str], moment: datetime) -> bool:
    """True when a section's weekday filter includes this local day."""

    if not days:
        return True
    local = moment.astimezone() if moment.tzinfo is not None else moment
    weekday = local.weekday()
    token = "sat" if weekday == 5 else "sun" if weekday == 6 else "weekday"
    return token in days


@dataclass(frozen=True, slots=True)
class FolderRead:
    folder: str
    hours: int
    name: str = ""
    days: tuple[str, ...] = ()
    unread_only: bool = True


def sender_domain(from_header: str) -> str | None:
    _name, address = parseaddr(from_header)
    addr = address.casefold().strip()
    if "@" not in addr:
        return None
    domain = addr.rsplit("@", 1)[-1].strip().strip(">").strip(".")
    if not domain or "." not in domain or " " in domain:
        return None
    return domain


def format_sender_domains(counts: Mapping[str, int]) -> str:
    """Domains and counts only, most common first."""

    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    if not ordered:
        return ""
    return "".join(f"{domain} {count}\n" for domain, count in ordered)


_SENDER_FETCH = "(INTERNALDATE BODY.PEEK[HEADER.FIELDS (FROM DATE)])"
_MAX_SENDER_SCAN = 5000


def _parse_fetch(payload: object) -> tuple[bytes | None, datetime | None]:
    raw: bytes | None = None
    internal: datetime | None = None
    if not isinstance(payload, list):
        return None, None
    for part in payload:
        if not isinstance(part, tuple) or len(part) < 2:
            continue
        meta = part[0] if isinstance(part[0], bytes) else b""
        match = re.search(br'INTERNALDATE "([^"]+)"', meta)
        if match:
            try:
                internal = _as_utc(parsedate_to_datetime(match.group(1).decode("ascii", "replace")))
            except (TypeError, ValueError, OverflowError):
                internal = None
        if isinstance(part[1], (bytes, bytearray)):
            raw = bytes(part[1])
    return raw, internal


def _search_ids(imap: imaplib.IMAP4, *criteria: str) -> list[bytes]:
    try:
        status, data = imap.search(None, *criteria)
    except Exception:
        raise InboxError("could not search the mailbox") from None
    if status != "OK" or not data or not data[0]:
        return []
    return data[0].split()


def _examine(imap: imaplib.IMAP4, folder: str) -> None:
    """Open one folder read-only. imaplib sends EXAMINE when readonly is true."""

    try:
        status, _data = imap.select(imap_mailbox_arg(folder), readonly=True)
    except Exception:
        raise InboxError("could not open the mailbox folder") from None
    if status != "OK":
        raise InboxError("could not open the mailbox folder")


def read_imap(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    folder: str,
    hours: int,
    allowlist: Sequence[str],
    max_messages: int,
    max_chars: int,
    max_total_chars: int,
    now: datetime | None = None,
    connector: Connector | None = None,
    head: HeadGetter | None = None,
    accept_all: bool = False,
    unread_only: bool = True,
    section: str = "",
    folders: Sequence[FolderRead] | None = None,
) -> CollectedMail:
    """Read recent mail. The folder is opened with EXAMINE and fetched with BODY.PEEK.

    Flags are not changed. Nothing is moved or deleted. ``unread_only`` adds
    the UNSEEN search key; it does not mark mail as read.
    """

    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    specs = tuple(folders) if folders is not None else (
        FolderRead(
            folder=folder,
            hours=hours,
            name=section,
            unread_only=unread_only,
        ),
    )
    connect = connector or _default_connector
    try:
        imap = connect(host, port)
    except Exception:
        raise InboxError("could not connect to the mailbox") from None
    try:
        try:
            imap.login(user, password)
        except Exception:
            raise InboxError("mailbox login failed") from None
        grouped: list[tuple[datetime | None, tuple[NewsletterItem, ...]]] = []
        skipped = 0
        for spec in specs:
            if not section_active(spec.days, moment):
                continue
            _examine(imap, spec.folder)
            since = imap_since(moment - timedelta(hours=spec.hours))
            criteria: list[str] = ["SINCE", since]
            if spec.unread_only:
                criteria.insert(0, "UNSEEN")
            ids = _search_ids(imap, *criteria)[-max_messages:]
            for message_id in ids:
                try:
                    status, fetched = imap.fetch(message_id, "(INTERNALDATE BODY.PEEK[])")
                except Exception:
                    raise InboxError("could not read a message") from None
                if status != "OK":
                    continue
                raw, internal = _parse_fetch(fetched)
                if raw is None:
                    continue
                parsed = items_from_message(
                    raw,
                    allowlist=allowlist,
                    max_chars=max_chars,
                    fallback_when=internal,
                    head=head,
                    accept_all=accept_all,
                    section=spec.name,
                )
                if parsed is None:
                    skipped += 1
                    continue
                _address, when, items = parsed
                if not _within_hours(when, now=moment, hours=spec.hours):
                    continue
                grouped.append((when, items))
        collected = _assign_ids(grouped, max_total_chars=max_total_chars)
        return CollectedMail(
            items=collected.items,
            kept_messages=collected.kept_messages,
            skipped_senders=skipped,
            trimmed=collected.trimmed,
        )
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def list_sender_domains(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    folders: Sequence[str],
    hours: int,
    now: datetime | None = None,
    connector: Connector | None = None,
) -> dict[str, int]:
    """Count sender domains in the named folders. Headers only, still read-only."""

    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    connect = connector or _default_connector
    try:
        imap = connect(host, port)
    except Exception:
        raise InboxError("could not connect to the mailbox") from None
    counts: Counter[str] = Counter()
    try:
        try:
            imap.login(user, password)
        except Exception:
            raise InboxError("mailbox login failed") from None
        since = imap_since(moment - timedelta(hours=hours))
        for folder in folders:
            _examine(imap, folder)
            ids = _search_ids(imap, "SINCE", since)[-_MAX_SENDER_SCAN:]
            for message_id in ids:
                try:
                    status, fetched = imap.fetch(message_id, _SENDER_FETCH)
                except Exception:
                    raise InboxError("could not read a message") from None
                if status != "OK":
                    continue
                raw, internal = _parse_fetch(fetched)
                if raw is None:
                    continue
                message = message_from_bytes(raw)
                when = message_when(message, internal)
                if not _within_hours(when, now=moment, hours=hours):
                    continue
                domain = sender_domain(message.get("From", ""))
                if domain:
                    counts[domain] += 1
        return dict(counts)
    finally:
        try:
            imap.logout()
        except Exception:
            pass
