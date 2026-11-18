"""Small HTTPS reader with a timeout and a size cap. No cookies and no credentials."""

from __future__ import annotations

import urllib.error
import urllib.request
from collections.abc import Callable
from urllib.parse import urlsplit

from newsletter_brief.inbox import _blocked_host

Getter = Callable[[str], bytes]


class HttpError(RuntimeError):
    """Raised when a remote document cannot be used. The message has no body."""


def _public_https(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise HttpError("only https URLs can be fetched")
    if parsed.username or parsed.password:
        raise HttpError("URL must not contain credentials")
    if _blocked_host(parsed.hostname):
        raise HttpError("URL host is not allowed")
    return url.strip()


class _HttpsRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        try:
            _public_https(newurl)
        except HttpError:
            raise HttpError("redirect was not a public https URL") from None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def read_https(
    url: str,
    *,
    timeout: float,
    max_bytes: int,
    accept: str,
    get: Getter | None = None,
) -> bytes:
    """Read one https document. A test may pass ``get`` and skip the network."""

    target = _public_https(url)
    if get is not None:
        try:
            data = get(target)
        except HttpError:
            raise
        except Exception:
            raise HttpError("could not read the URL") from None
        if not isinstance(data, (bytes, bytearray)):
            raise HttpError("response was empty")
        if len(data) > max_bytes:
            raise HttpError("response is too large")
        return bytes(data)

    request = urllib.request.Request(
        target,
        headers={"User-Agent": "newsletter-brief", "Accept": accept},
        method="GET",
    )
    opener = urllib.request.build_opener(_HttpsRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            final = response.geturl()
            _public_https(final)
            status = getattr(response, "status", 200)
            if status != 200:
                raise HttpError("document was not available")
            data = response.read(max_bytes + 1)
    except HttpError:
        raise
    except urllib.error.URLError:
        raise HttpError("could not read the URL") from None
    except Exception:
        raise HttpError("could not read the URL") from None
    if len(data) > max_bytes:
        raise HttpError("response is too large")
    return data
