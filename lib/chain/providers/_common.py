"""Shared helpers for provider clients.

Rather than duplicate the urllib dance six times, these helpers let each
provider module stay ~40 lines of real logic.
"""

from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ..sources import SourceError, _cache_get, _cache_set  # reuse the same cache

try:
    import certifi

    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

DEFAULT_TIMEOUT = 15
USER_AGENT = "sapphire-os/0.4 (+providers)"


def get_env(name: str) -> str:
    val = os.getenv(name, "")
    if not val:
        raise SourceError(f"missing env var {name}")
    return val


def http_get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    cache: bool = True,
) -> Any:
    if params:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{url}?{query}" if query else url
    cache_key = f"GET {url}"
    if cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        raise SourceError(f"GET {url} → HTTP {e.code}: {e.reason}") from e
    except Exception as e:  # noqa: BLE001 — normalise network failure
        raise SourceError(f"GET {url} → {type(e).__name__}: {e}") from e
    try:
        data = json.loads(body) if body else {}
    except json.JSONDecodeError as e:
        raise SourceError(f"GET {url} → invalid JSON: {e}") from e
    if cache:
        _cache_set(cache_key, data)
    return data


def http_post_json(
    url: str,
    payload: dict,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    cache: bool = True,
) -> Any:
    cache_key = f"POST {url} {json.dumps(payload, sort_keys=True)}"
    if cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
    hdrs = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if headers:
        hdrs.update(headers)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        raise SourceError(f"POST {url} → HTTP {e.code}: {e.reason}") from e
    except Exception as e:  # noqa: BLE001
        raise SourceError(f"POST {url} → {type(e).__name__}: {e}") from e
    try:
        parsed = json.loads(body) if body else {}
    except json.JSONDecodeError as e:
        raise SourceError(f"POST {url} → invalid JSON: {e}") from e
    if cache:
        _cache_set(cache_key, parsed)
    return parsed


# Unused but re-exported for subclasses that need direct cache control.
__all__ = ["get_env", "http_get", "http_post_json", "SourceError", "time"]
