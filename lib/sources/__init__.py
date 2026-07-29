"""Dry-run-default external intelligence sources for Sapphire.

Live pulls are disabled unless the source-specific ``SAPPHIRE_<NAME>_LIVE=1``
flag is set. Secrets are loaded from ``~/.sapphire/secrets.env`` when needed,
and raw caches stay under ``~/.cache/sapphire/<source>/``.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_USER_AGENT = (
    "SapphireIntelBreadth/0.1 "
    "(+https://github.com/arigatoexpress/Sapphire; contact=ops@sapphirealpha.xyz)"
)
SECRETS_PATH = Path.home() / ".sapphire" / "secrets.env"


class SourceError(RuntimeError):
    """Source pull failed in a recoverable way."""


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def cache_dir(source: str) -> Path:
    root = Path(os.environ.get("SAPPHIRE_CACHE_DIR", Path.home() / ".cache" / "sapphire"))
    path = root.expanduser() / source
    path.mkdir(parents=True, exist_ok=True)
    return path


def live_enabled(name: str) -> bool:
    return os.environ.get(f"SAPPHIRE_{name.upper()}_LIVE") == "1"


def load_secrets(path: Path = SECRETS_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    for line in lines:
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def secret_value(name: str, *, secrets: Mapping[str, str] | None = None) -> str | None:
    return os.environ.get(name) or dict(secrets or load_secrets()).get(name)


def read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def read_fresh_json(path: Path, *, ttl_seconds: int, now: float | None = None) -> Any | None:
    if not path.exists():
        return None
    current = time.time() if now is None else now
    if current - path.stat().st_mtime > ttl_seconds:
        return None
    return read_json(path)


def http_get_text(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    safe_headers = {"User-Agent": DEFAULT_USER_AGENT, **dict(headers or {})}
    request = urllib.request.Request(url, headers=safe_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise SourceError(f"source http get failed for {url}: {exc}") from exc


def http_get_json(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Any:
    return json.loads(http_get_text(url, headers=headers, timeout=timeout))


def build_url(base: str, params: Mapping[str, Any]) -> str:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    return f"{base}?{query}" if query else base


def parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        if isinstance(value, int | float):
            return datetime.fromtimestamp(float(value), tz=UTC)
        text = str(value).strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except (OSError, ValueError):
        return None


def age_seconds(timestamp: datetime | None, *, now: datetime | None = None) -> float:
    if timestamp is None:
        return float("inf")
    current = now or utc_now()
    return max(0.0, (current - timestamp.astimezone(UTC)).total_seconds())


def clamp(value: Any, *, default: float = 0.5) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:
        return default
    return max(0.0, min(1.0, number))


def canonical_symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    return {
        "BTC-USD": "BTC",
        "BTCUSD": "BTC",
        "BTCUSDT": "BTC",
        "ETH-USD": "ETH",
        "ETHUSD": "ETH",
        "ETHUSDT": "ETH",
        "SOL-USD": "SOL",
        "SOLUSD": "SOL",
        "SOLUSDT": "SOL",
    }.get(text, text)


from .defillama import DeFiLlamaSource
from .dune import DuneNamedQuerySource
from .earnings_calls import EarningsCallSource
from .labor import LaborSource
from .news import NewsAPISource
from .sec_edgar import SECEdgarSource
from .tdr_pro import TDRProSource
from .tdr_pro_email import TDRProEmailSource
from .x_sentiment import XSentimentSource

__all__ = [
    "DEFAULT_USER_AGENT",
    "DeFiLlamaSource",
    "DuneNamedQuerySource",
    "EarningsCallSource",
    "LaborSource",
    "NewsAPISource",
    "SECEdgarSource",
    "SourceError",
    "TDRProEmailSource",
    "TDRProSource",
    "XSentimentSource",
    "age_seconds",
    "build_url",
    "cache_dir",
    "canonical_symbol",
    "clamp",
    "http_get_json",
    "http_get_text",
    "live_enabled",
    "load_secrets",
    "parse_iso",
    "read_fresh_json",
    "read_json",
    "secret_value",
    "utc_now",
    "write_json",
]
