"""Newest notable models from public, keyless catalogs.

Facts (name, maker, context length, price) come from those catalogs.
A summary model may add one sentence, and only when that sentence cites a
URL we actually handed it. A failed fetch leaves the block out.
"""

from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime, timedelta, timezone
from collections.abc import Callable, Sequence
from urllib.parse import urlsplit

from newsletter_brief.http_get import HttpError, read_https
from newsletter_brief.models import ModelNote, ModelRelease

LOGGER = logging.getLogger("newsletter_brief.model_mania")

OPENROUTER_URL = "https://openrouter.ai/api/v1/models"
HF_URL = (
    "https://huggingface.co/api/models"
    "?pipeline_tag=text-generation&sort=trendingScore&direction=-1&limit=30"
)
LMARENA_URL = "https://lmarena.ai/"
ARTIFICIAL_ANALYSIS_URL = "https://artificialanalysis.ai/leaderboards/models"
LEADERBOARD_URLS = (LMARENA_URL, ARTIFICIAL_ANALYSIS_URL)

DEFAULT_WINDOW_HOURS = 60
DEFAULT_MAX_MODELS = 6

_PLUMBING = re.compile(r"open\s*router|listed on|hugging\s*face\s+api", re.IGNORECASE)
_BENCHMARK = re.compile(
    r"\b(beats?|beating|outperforms?|outperformed|benchmarks?|leaderboards?|"
    r"sota|state of the art|better than|wins? against|#1|number one)\b",
    re.IGNORECASE,
)
_ATTRIBUTION = re.compile(
    r"\b(says|said|reports|reported|according to|claims|claimed|finds|found)\b",
    re.IGNORECASE,
)
_URL_IN_TEXT = re.compile(r"https://[^\s<>\"']+")
_HF_ID = re.compile(r"^[\w.-]+/[\w.-]+$")
_MAKERS = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google",
    "meta-llama": "Meta",
    "meta": "Meta",
    "mistralai": "Mistral",
    "mistral": "Mistral",
    "x-ai": "xAI",
    "xai": "xAI",
    "deepseek": "DeepSeek",
    "qwen": "Qwen",
    "cohere": "Cohere",
    "amazon": "Amazon",
    "microsoft": "Microsoft",
    "nvidia": "NVIDIA",
    "ai21": "AI21",
    "perplexity": "Perplexity",
}

Getter = Callable[[str], bytes]


class ModelCatalogError(ValueError):
    """Raised when a catalog payload cannot be read. The message has no body."""


def maker_from_id(model_id: str) -> str:
    slug = model_id.split("/", 1)[0].strip()
    known = _MAKERS.get(slug.casefold())
    if known:
        return known
    parts = [part for part in re.split(r"[-_]+", slug) if part]
    if not parts:
        return "Unknown"
    return " ".join(part[:1].upper() + part[1:] for part in parts)


def price_per_million(raw: object) -> str:
    """Turn a per-token USD amount into a per-million display string."""

    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        return ""
    try:
        per_token = float(str(raw).strip())
    except (TypeError, ValueError):
        return ""
    if math.isnan(per_token) or math.isinf(per_token) or per_token < 0:
        return ""
    amount = per_token * 1_000_000
    if amount == 0:
        return "$0"
    if amount >= 100:
        return f"${amount:,.0f}"
    return f"${amount:.2f}"


def _created_seconds(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    stamp = int(value)
    if stamp > 10_000_000_000:
        stamp //= 1000
    if stamp <= 0:
        return None
    return stamp


def _within(stamp: int, *, now: datetime, hours: int) -> bool:
    moment = datetime.fromtimestamp(stamp, timezone.utc)
    current = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return current - timedelta(hours=hours) <= moment <= current + timedelta(minutes=5)


def _is_text_model(model_id: str, modality: str) -> bool:
    folded_id = model_id.casefold()
    folded_mode = modality.casefold()
    if "embed" in folded_id or "embed" in folded_mode:
        return False
    if modality and "text" not in folded_mode:
        return False
    return True


def _safe_blurb(value: object) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = " ".join(value.split())
    if not cleaned or _PLUMBING.search(cleaned):
        return ""
    return cleaned[:600]


def _hf_page(model_id: str) -> str:
    if _HF_ID.fullmatch(model_id):
        return f"https://huggingface.co/{model_id}"
    return ""


def _context_length(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value <= 0 or value > 10_000_000:
        return None
    return value


def releases_from_openrouter(
    payload: bytes,
    *,
    now: datetime,
    window_hours: int,
    limit: int,
) -> tuple[ModelRelease, ...]:
    """Keep text models listed inside the window, newest first, up to ``limit``."""

    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ModelCatalogError("catalog was not JSON") from exc
    rows = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        raise ModelCatalogError("catalog had no model list")

    found: list[tuple[int, ModelRelease]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        model_id = row.get("id")
        if not isinstance(model_id, str) or not model_id.strip():
            continue
        model_id = model_id.strip()
        architecture = row.get("architecture")
        modality = ""
        if isinstance(architecture, dict) and isinstance(architecture.get("modality"), str):
            modality = architecture["modality"]
        if not _is_text_model(model_id, modality):
            continue
        created = _created_seconds(row.get("created"))
        if created is None or not _within(created, now=now, hours=window_hours):
            continue
        name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            name = model_id.split("/", 1)[-1]
        name = " ".join(name.split())
        if not name or _PLUMBING.search(name):
            continue
        pricing = row.get("pricing") if isinstance(row.get("pricing"), dict) else {}
        prompt = price_per_million(pricing.get("prompt"))
        completion = price_per_million(pricing.get("completion"))
        sources: list[str] = []
        hf_id = row.get("hugging_face_id")
        if isinstance(hf_id, str):
            page = _hf_page(hf_id.strip())
            if page:
                sources.append(page)
        found.append(
            (
                created,
                ModelRelease(
                    model_id=model_id,
                    name=name,
                    maker=maker_from_id(model_id),
                    context_length=_context_length(row.get("context_length")),
                    input_per_million=prompt,
                    output_per_million=completion,
                    source_urls=tuple(sources),
                    blurb=_safe_blurb(row.get("description")),
                    open_weights=bool(sources),
                ),
            )
        )
    found.sort(key=lambda item: (-item[0], item[1].model_id))
    return tuple(item for _, item in found[:limit])


def _hf_created(value: object) -> int | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return int(moment.timestamp())


def releases_from_huggingface(
    payload: bytes,
    *,
    now: datetime,
    max_age_hours: int,
    min_likes: int,
    limit: int,
) -> tuple[ModelRelease, ...]:
    """Keep recent open-weight text models at or above the like floor."""

    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ModelCatalogError("catalog was not JSON") from exc
    rows = raw if isinstance(raw, list) else None
    if rows is None:
        raise ModelCatalogError("catalog had no model list")

    found: list[ModelRelease] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("gated") is True:
            continue
        model_id = row.get("id") or row.get("modelId")
        if not isinstance(model_id, str) or not _HF_ID.fullmatch(model_id):
            continue
        pipeline = row.get("pipeline_tag")
        if isinstance(pipeline, str) and pipeline not in {"text-generation", "text2text-generation"}:
            continue
        likes = row.get("likes")
        if isinstance(likes, bool) or not isinstance(likes, int) or likes < min_likes:
            continue
        created = _hf_created(row.get("createdAt"))
        if created is None or not _within(created, now=now, hours=max_age_hours):
            continue
        if not _is_text_model(model_id, ""):
            continue
        name = model_id.split("/", 1)[-1].replace("-", " ").replace("_", " ")
        name = " ".join(name.split())
        card = row.get("cardData") if isinstance(row.get("cardData"), dict) else {}
        context = _context_length(card.get("context_length") if isinstance(card, dict) else None)
        if context is None:
            context = _context_length(row.get("context_length"))
        page = _hf_page(model_id)
        found.append(
            ModelRelease(
                model_id=model_id,
                name=name,
                maker=maker_from_id(model_id),
                context_length=context,
                input_per_million="",
                output_per_million="",
                source_urls=(page,) if page else (),
                blurb="",
                open_weights=True,
            )
        )
        if len(found) >= limit:
            break
    return tuple(found)


def merge_releases(
    primary: Sequence[ModelRelease],
    extra: Sequence[ModelRelease],
    limit: int,
) -> tuple[ModelRelease, ...]:
    """Keep catalog order. A model already in the primary list is not repeated."""

    kept: list[ModelRelease] = []
    seen: set[str] = set()

    def remember(release: ModelRelease) -> None:
        keys = {release.model_id.casefold()}
        if "/" in release.model_id:
            keys.add(release.model_id.split("/", 1)[-1].casefold())
        for url in release.source_urls:
            path = urlsplit(url).path.strip("/")
            if path:
                keys.add(path.casefold())
                keys.add(path.split("/")[-1].casefold())
        if keys & seen:
            return
        seen.update(keys)
        kept.append(release)

    for release in primary:
        if len(kept) >= limit:
            break
        remember(release)
    for release in extra:
        if len(kept) >= limit:
            break
        remember(release)
    return tuple(kept)


def note_source_allowlist(releases: Sequence[ModelRelease]) -> set[str]:
    allowed = set(LEADERBOARD_URLS)
    for release in releases:
        allowed.update(url for url in release.source_urls if url.startswith("https://"))
    return allowed


def _urls_in(text: str) -> set[str]:
    found: set[str] = set()
    for match in _URL_IN_TEXT.findall(text):
        found.add(match.rstrip(".,;:)]>"))
    return found


def accept_model_note(text: str, source_url: str, allowed: set[str]) -> str:
    """Return the sentence, or empty when it is unsourced or unattributed."""

    cleaned = " ".join(text.split())
    if not cleaned or not source_url or source_url not in allowed:
        return ""
    if _PLUMBING.search(cleaned):
        return ""
    if _urls_in(cleaned) - allowed:
        return ""
    if _BENCHMARK.search(cleaned) and not _ATTRIBUTION.search(cleaned):
        return ""
    if len(cleaned) > 280:
        return ""
    sentences = [part for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]
    if len(sentences) > 1:
        return ""
    return cleaned


def bind_notes(
    releases: Sequence[ModelRelease],
    notes: Sequence[ModelNote],
) -> tuple[ModelRelease, ...]:
    """Attach a valid note to its model. Anything else is left off."""

    allowed = note_source_allowlist(releases)
    chosen: dict[str, ModelNote] = {}
    for note in notes:
        if note.model_id in chosen:
            continue
        cleaned = accept_model_note(note.text, note.source_url, allowed)
        if not cleaned:
            continue
        chosen[note.model_id] = ModelNote(note.model_id, cleaned, note.source_url)
    bound: list[ModelRelease] = []
    for release in releases:
        note = chosen.get(release.model_id)
        if note is None:
            bound.append(release)
            continue
        bound.append(
            release.__class__(
                model_id=release.model_id,
                name=release.name,
                maker=release.maker,
                context_length=release.context_length,
                input_per_million=release.input_per_million,
                output_per_million=release.output_per_million,
                source_urls=release.source_urls,
                blurb=release.blurb,
                open_weights=release.open_weights,
                note=note.text,
                note_source=note.source_url,
            )
        )
    return tuple(bound)


def catalog_for_prompt(releases: Sequence[ModelRelease]) -> list[dict[str, object]]:
    """What the summary model is allowed to see. Prices stay out of this list."""

    rows: list[dict[str, object]] = []
    for release in releases:
        sources = list(release.source_urls) + list(LEADERBOARD_URLS)
        rows.append(
            {
                "model_id": release.model_id,
                "name": release.name,
                "maker": release.maker,
                "description": release.blurb,
                "allowed_sources": sources,
            }
        )
    return rows


def _read(url: str, *, timeout: int, max_bytes: int, get: Getter | None) -> bytes:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise HttpError("only https URLs can be fetched")
    if get is not None:
        try:
            data = get(url)
        except HttpError:
            raise
        except Exception:
            raise HttpError("could not read the URL") from None
        if not isinstance(data, (bytes, bytearray)) or not data:
            raise HttpError("response was empty")
        if len(data) > max_bytes:
            raise HttpError("response is too large")
        return bytes(data)
    return read_https(
        url,
        timeout=float(timeout),
        max_bytes=max_bytes,
        accept="application/json",
    )


def _warn(message: str) -> None:
    LOGGER.warning("model mania: %s", message)


def fetch_model_releases(
    *,
    enabled: bool,
    window_hours: int = DEFAULT_WINDOW_HOURS,
    max_models: int = DEFAULT_MAX_MODELS,
    timeout_seconds: int = 8,
    max_bytes: int = 2_000_000,
    huggingface: bool = False,
    huggingface_min_likes: int = 100,
    huggingface_max_age_hours: int = 168,
    now: datetime | None = None,
    get: Getter | None = None,
) -> tuple[ModelRelease, ...]:
    """Fetch the block. Any network or payload failure becomes an empty tuple."""

    if not enabled:
        return ()
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    cap = max(1, min(max_models, DEFAULT_MAX_MODELS))
    primary: tuple[ModelRelease, ...] = ()
    try:
        payload = _read(
            OPENROUTER_URL,
            timeout=timeout_seconds,
            max_bytes=max_bytes,
            get=get,
        )
        primary = releases_from_openrouter(
            payload,
            now=moment,
            window_hours=window_hours,
            limit=cap,
        )
    except (HttpError, ModelCatalogError, OSError, ValueError):
        _warn("the public model catalog was not used")
        primary = ()

    extra: tuple[ModelRelease, ...] = ()
    if huggingface:
        try:
            payload = _read(HF_URL, timeout=timeout_seconds, max_bytes=max_bytes, get=get)
            extra = releases_from_huggingface(
                payload,
                now=moment,
                max_age_hours=huggingface_max_age_hours,
                min_likes=huggingface_min_likes,
                limit=cap,
            )
        except (HttpError, ModelCatalogError, OSError, ValueError):
            _warn("the open-weight catalog was not used")
            extra = ()
    return merge_releases(primary, extra, cap)
