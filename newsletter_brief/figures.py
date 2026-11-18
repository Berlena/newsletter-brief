"""Market figures from free, keyless sources. The model never supplies these numbers."""

from __future__ import annotations

import json
import math
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from newsletter_brief.models import Figure

ECB_DAILY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
ECB_INFO_URL = (
    "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/"
    "euro_reference_exchange_rates/html/index.en.html"
)
COINGECKO_URL = (
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=bitcoin,ethereum&vs_currencies=usd&include_last_updated_at=true"
)
COINGECKO_INFO = {
    "btc-usd": "https://www.coingecko.com/en/coins/bitcoin",
    "eth-usd": "https://www.coingecko.com/en/coins/ethereum",
}
CRYPTO_IDS = {
    "btc-usd": ("bitcoin", "Bitcoin"),
    "eth-usd": ("ethereum", "Ether"),
}
ECB_NS = {"e": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}
UNAVAILABLE = "unavailable"
SUPPORTED_FIGURE_RE = re.compile(r"eur-[a-z]{3}|btc-usd|eth-usd")
_DECIMAL = re.compile(r"^\d+(?:\.\d+)?$")

Getter = Callable[[str], bytes]


class FigureDataError(ValueError):
    """Raised when a source answered with something we will not treat as a number."""


@dataclass(frozen=True, slots=True)
class _EcbRates:
    day: str
    rates: dict[str, str]


def _unavailable(figure_id: str, label: str, source_name: str, source_url: str) -> Figure:
    return Figure(
        figure_id=figure_id,
        label=label,
        value=UNAVAILABLE,
        source_name=source_name,
        source_url=source_url,
        as_of="",
        available=False,
    )


def _http_get(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "newsletter-brief",
            "Accept": "application/xml, application/json;q=0.9, */*;q=0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise OSError(f"HTTP {status}")
            return response.read(1_000_000)
    except urllib.error.URLError as exc:
        raise OSError(str(exc.reason)) from None


def parse_ecb_daily(payload: bytes) -> _EcbRates:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise FigureDataError("ECB response was not XML") from exc
    day_node = None
    for node in root.findall(".//e:Cube", ECB_NS):
        if node.get("time"):
            day_node = node
            break
    if day_node is None:
        raise FigureDataError("ECB response had no rate date")
    day = day_node.get("time") or ""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise FigureDataError("ECB rate date was not usable")
    rates: dict[str, str] = {}
    for node in day_node.findall("e:Cube", ECB_NS):
        currency = node.get("currency") or ""
        rate = node.get("rate") or ""
        if re.fullmatch(r"[A-Z]{3}", currency) and _DECIMAL.fullmatch(rate):
            rates[currency] = rate
    if not rates:
        raise FigureDataError("ECB response had no rates")
    return _EcbRates(day=day, rates=rates)


def _format_usd(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FigureDataError("crypto price was not a number")
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        raise FigureDataError("crypto price was not a number")
    if value < 0:
        raise FigureDataError("crypto price was negative")
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{float(value):,.2f}"


def parse_coingecko(payload: bytes) -> dict[str, tuple[str, str]]:
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise FigureDataError("CoinGecko response was not JSON") from exc
    if not isinstance(raw, dict):
        raise FigureDataError("CoinGecko response was not an object")
    parsed: dict[str, tuple[str, str]] = {}
    for figure_id, (coin_id, _label) in CRYPTO_IDS.items():
        coin = raw.get(coin_id)
        if not isinstance(coin, dict) or "usd" not in coin or "last_updated_at" not in coin:
            continue
        stamp = coin.get("last_updated_at")
        if isinstance(stamp, bool) or not isinstance(stamp, int) or stamp <= 0:
            continue
        try:
            value = _format_usd(coin.get("usd"))
            as_of = datetime.fromtimestamp(stamp, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        except (FigureDataError, OverflowError, OSError, ValueError):
            continue
        parsed[figure_id] = (value, as_of)
    if not parsed:
        raise FigureDataError("CoinGecko response had no usable prices")
    return parsed


def _label_for(figure_id: str) -> tuple[str, str, str]:
    if figure_id in CRYPTO_IDS:
        return CRYPTO_IDS[figure_id][1], "CoinGecko", COINGECKO_INFO[figure_id]
    currency = figure_id.split("-", 1)[1].upper()
    return f"EUR to {currency}", "ECB reference rate", ECB_INFO_URL


def fetch_figures(ids: tuple[str, ...] | list[str], *, get: Getter | None = None) -> tuple[Figure, ...]:
    """Fetch each configured figure. A failed fetch becomes 'unavailable'."""

    getter = get or _http_get
    ecb_ids = [figure_id for figure_id in ids if figure_id.startswith("eur-")]
    crypto_ids = [figure_id for figure_id in ids if figure_id in CRYPTO_IDS]
    ecb: _EcbRates | None = None
    if ecb_ids:
        try:
            ecb = parse_ecb_daily(getter(ECB_DAILY_URL))
        except (OSError, FigureDataError, ET.ParseError):
            ecb = None
    crypto: dict[str, tuple[str, str]] | None = None
    if crypto_ids:
        try:
            crypto = parse_coingecko(getter(COINGECKO_URL))
        except (OSError, FigureDataError):
            crypto = None

    figures: list[Figure] = []
    for figure_id in ids:
        label, source_name, source_url = _label_for(figure_id)
        if figure_id.startswith("eur-"):
            currency = figure_id.split("-", 1)[1].upper()
            if ecb is None or currency not in ecb.rates:
                figures.append(_unavailable(figure_id, label, source_name, source_url))
                continue
            figures.append(
                Figure(
                    figure_id=figure_id,
                    label=label,
                    value=ecb.rates[currency],
                    source_name=source_name,
                    source_url=source_url,
                    as_of=ecb.day,
                    available=True,
                )
            )
            continue
        if figure_id in CRYPTO_IDS:
            found = None if crypto is None else crypto.get(figure_id)
            if found is None:
                figures.append(_unavailable(figure_id, label, source_name, source_url))
                continue
            value, as_of = found
            figures.append(
                Figure(
                    figure_id=figure_id,
                    label=label,
                    value=value,
                    source_name=source_name,
                    source_url=source_url,
                    as_of=as_of,
                    available=True,
                )
            )
            continue
        figures.append(_unavailable(figure_id, figure_id, "unknown", ""))
    return tuple(figures)
