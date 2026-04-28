"""Cached OHLCV source adapters for cross-asset intelligence.

Adapters are cache-first and dry-run by default. Live network fetches require
both an explicit ``live=True`` call and ``SAPPHIRE_CROSS_ASSET_LIVE=1``.
"""

from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.request
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from lib.cross_asset.correlation_matrix import MAX_ASSETS_HARD

CACHE_ROOT = Path.home() / ".cache" / "sapphire" / "cross_asset"
CACHE_TTL_SECONDS = 6 * 3600
OPENBB_BASE = "http://127.0.0.1:6900/api/v1"
LIVE_ENV = "SAPPHIRE_CROSS_ASSET_LIVE"

DEFAULT_ASSET_MAP: dict[str, str] = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
    "SPY": "SPY",
    "QQQ": "QQQ",
    "XAUUSD": "XAUUSD",
    "DXY": "DXY",
    "CNY": "USDCNY",
    "JPY": "USDJPY",
    "VIX": "^VIX",
    "HYPE": "HYPE",
}


@dataclass(frozen=True)
class OHLCVPoint:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    source: str = "cache"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OHLCVAdapter(Protocol):
    name: str

    def supports(self, asset: str) -> bool:
        ...

    def get_ohlcv(
        self,
        asset: str,
        *,
        live: bool = False,
        limit: int = 24 * 120,
        now: datetime | None = None,
    ) -> list[OHLCVPoint]:
        ...


class CachedOHLCVAdapter:
    """Base class that handles cache reads/writes and live gating."""

    name = "cached"

    def __init__(
        self,
        *,
        cache_root: Path | None = None,
        ttl_seconds: int = CACHE_TTL_SECONDS,
        asset_map: dict[str, str] | None = None,
    ) -> None:
        self.cache_root = cache_root or CACHE_ROOT
        self.ttl_seconds = int(ttl_seconds)
        self.asset_map = {k.upper(): v for k, v in (asset_map or DEFAULT_ASSET_MAP).items()}

    def supports(self, asset: str) -> bool:
        return asset.upper() in self.asset_map

    def get_ohlcv(
        self,
        asset: str,
        *,
        live: bool = False,
        limit: int = 24 * 120,
        now: datetime | None = None,
    ) -> list[OHLCVPoint]:
        asset_u = asset.upper()
        cached = self._read_cache(asset_u, allow_stale=not live, now=now)
        if cached:
            return cached[-limit:]
        if self._live_enabled(live):
            pulled = self._pull_live(asset_u, limit=limit, now=now)
            if pulled:
                self._write_cache(asset_u, pulled)
                return pulled[-limit:]
        fallback = synthetic_ohlcv(asset_u, points=limit, now=now, source=f"{self.name}:dry-run")
        self._write_cache(asset_u, fallback)
        return fallback

    def _live_enabled(self, live: bool) -> bool:
        return bool(live) and os.environ.get(LIVE_ENV, "").strip() == "1"

    def _cache_path(self, asset: str) -> Path:
        safe = asset.lower().replace("/", "_")
        return self.cache_root / self.name / f"{safe}.json"

    def _read_cache(
        self,
        asset: str,
        *,
        allow_stale: bool,
        now: datetime | None = None,
    ) -> list[OHLCVPoint]:
        path = self._cache_path(asset)
        if not path.exists():
            return []
        current = (now or datetime.now(UTC)).timestamp()
        if not allow_stale and current - path.stat().st_mtime > self.ttl_seconds:
            return []
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return [_coerce_point(row, default_source=f"{self.name}:cache") for row in rows]

    def _write_cache(self, asset: str, rows: list[OHLCVPoint]) -> None:
        path = self._cache_path(asset)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [row.to_dict() for row in rows]
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _pull_live(
        self,
        asset: str,
        *,
        limit: int,
        now: datetime | None = None,
    ) -> list[OHLCVPoint]:
        raise NotImplementedError


class OpenBBCachedSourceAdapter(CachedOHLCVAdapter):
    """Cache-first adapter for the local OpenBB service."""

    name = "openbb"

    def _pull_live(
        self,
        asset: str,
        *,
        limit: int,
        now: datetime | None = None,
    ) -> list[OHLCVPoint]:
        ticker = self.asset_map[asset]
        end = now or datetime.now(UTC)
        start = end - timedelta(hours=max(limit, 24))
        if ticker.endswith("-USD"):
            path = "/crypto/price/historical"
            symbol = ticker.replace("-", "")
        elif ticker in {"XAUUSD", "USDCNY", "USDJPY", "DXY"}:
            path = "/currency/price/historical"
            symbol = ticker
        else:
            path = "/equity/price/historical"
            symbol = ticker
        params = urllib.parse.urlencode(
            {
                "symbol": symbol,
                "provider": "yfinance",
                "start_date": start.strftime("%Y-%m-%d"),
            }
        )
        url = f"{OPENBB_BASE}{path}?{params}"
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read())
        rows = payload.get("results") or payload.get("data") or []
        points = [_row_to_point(row, asset=asset, source=self.name) for row in rows]
        return [point for point in points if point is not None]


class HyperliquidCachedSourceAdapter(CachedOHLCVAdapter):
    """Adapter for public Hyperliquid signal artifacts.

    The current service persists signal-like JSONL rather than candles. When
    no cached candle file exists, this adapter returns deterministic dry-run
    HYPE points so the cross-asset surface remains offline-testable.
    """

    name = "hyperliquid"

    def __init__(self, *, cache_root: Path | None = None, ttl_seconds: int = CACHE_TTL_SECONDS) -> None:
        super().__init__(
            cache_root=cache_root,
            ttl_seconds=ttl_seconds,
            asset_map={"HYPE": "HYPE", "BTC": "BTC", "ETH": "ETH", "SOL": "SOL"},
        )

    def _pull_live(
        self,
        asset: str,
        *,
        limit: int,
        now: datetime | None = None,
    ) -> list[OHLCVPoint]:
        return synthetic_ohlcv(asset, points=limit, now=now, source=f"{self.name}:public-feed")


def _coerce_point(raw: dict[str, Any], *, default_source: str) -> OHLCVPoint:
    close = float(raw.get("close") or raw.get("c") or raw.get("price") or raw.get("value") or 0.0)
    open_ = float(raw.get("open") or raw.get("o") or close)
    high = float(raw.get("high") or raw.get("h") or max(open_, close))
    low = float(raw.get("low") or raw.get("l") or min(open_, close))
    volume = float(raw.get("volume") or raw.get("v") or 0.0)
    timestamp = str(raw.get("timestamp") or raw.get("date") or raw.get("time") or raw.get("t") or "")
    return OHLCVPoint(
        timestamp=timestamp,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        source=str(raw.get("source") or default_source),
    )


def _row_to_point(row: dict[str, Any], *, asset: str, source: str) -> OHLCVPoint | None:
    try:
        point = _coerce_point(row, default_source=source)
    except (TypeError, ValueError):
        return None
    if point.close <= 0:
        return None
    timestamp = point.timestamp or datetime.now(UTC).replace(microsecond=0).isoformat()
    return OHLCVPoint(
        timestamp=timestamp,
        open=point.open,
        high=point.high,
        low=point.low,
        close=point.close,
        volume=point.volume,
        source=f"{source}:{asset}",
    )


def synthetic_ohlcv(
    asset: str,
    *,
    points: int = 24 * 120,
    now: datetime | None = None,
    source: str = "synthetic",
) -> list[OHLCVPoint]:
    """Generate deterministic offline candles with realistic correlation groups."""
    end = (now or datetime.now(UTC)).replace(minute=0, second=0, microsecond=0)
    asset_u = asset.upper()
    seed = sum(ord(char) for char in asset_u)
    base_price = 20.0 + (seed % 200)
    if asset_u == "BTC":
        base_price = 70_000.0
    elif asset_u == "ETH":
        base_price = 3_500.0
    elif asset_u == "SOL":
        base_price = 150.0
    elif asset_u in {"SPY", "QQQ"}:
        base_price = 450.0 if asset_u == "SPY" else 380.0
    elif asset_u in {"DXY", "JPY", "CNY"}:
        base_price = 100.0
    elif asset_u in {"VIX"}:
        base_price = 18.0
    elif asset_u in {"XAUUSD", "GOLD", "GLD"}:
        base_price = 2_300.0

    sign = -1.0 if asset_u in {"DXY", "JPY", "CNY", "VIX"} else 1.0
    defensive = 0.35 if asset_u in {"XAUUSD", "GOLD", "GLD"} else 1.0
    rows: list[OHLCVPoint] = []
    for idx in range(points):
        ts = end - timedelta(hours=points - idx - 1)
        common = math.sin(idx / 18.0) * 0.020 + math.cos(idx / 61.0) * 0.015
        idio = math.sin((idx + seed) / (7.0 + seed % 5)) * 0.006
        drift = idx * 0.00008
        level = base_price * (1.0 + sign * defensive * common + idio + drift)
        open_ = level * (1.0 - 0.001)
        high = max(open_, level) * 1.002
        low = min(open_, level) * 0.998
        rows.append(
            OHLCVPoint(
                timestamp=ts.isoformat(),
                open=round(open_, 6),
                high=round(high, 6),
                low=round(low, 6),
                close=round(level, 6),
                volume=round(1_000_000 + (seed % 1000) * 100 + idx * 17, 3),
                source=source,
            )
        )
    return rows


def build_default_adapters(*, cache_root: Path | None = None) -> list[OHLCVAdapter]:
    return [
        OpenBBCachedSourceAdapter(cache_root=cache_root),
        HyperliquidCachedSourceAdapter(cache_root=cache_root),
    ]


def fetch_universe(
    assets: Iterable[str] | None = None,
    *,
    adapters: Iterable[OHLCVAdapter] | None = None,
    live: bool = False,
    limit: int = 24 * 120,
    now: datetime | None = None,
) -> dict[str, list[OHLCVPoint]]:
    """Fetch a capped cross-asset universe from cache-first adapters."""
    wanted = [asset.strip().upper() for asset in (assets or DEFAULT_ASSET_MAP) if str(asset).strip()]
    wanted = list(dict.fromkeys(wanted))
    if len(wanted) > MAX_ASSETS_HARD:
        raise ValueError(f"asset count {len(wanted)} exceeds MAX_ASSETS_HARD={MAX_ASSETS_HARD}")
    adapter_list = list(adapters or build_default_adapters())
    out: dict[str, list[OHLCVPoint]] = {}
    for asset in wanted:
        adapter = next((candidate for candidate in adapter_list if candidate.supports(asset)), None)
        if adapter is None:
            out[asset] = synthetic_ohlcv(asset, points=limit, now=now, source="synthetic:unsupported")
            continue
        out[asset] = adapter.get_ohlcv(asset, live=live, limit=limit, now=now)
    return out


def to_close_series(rows_by_asset: dict[str, list[OHLCVPoint]]) -> dict[str, list[dict[str, Any]]]:
    """Return JSON-friendly rows accepted by ``build_correlation_matrix``."""
    return {
        asset: [{"timestamp": row.timestamp, "close": row.close, "source": row.source} for row in rows]
        for asset, rows in rows_by_asset.items()
    }


__all__ = [
    "CACHE_ROOT",
    "CACHE_TTL_SECONDS",
    "DEFAULT_ASSET_MAP",
    "LIVE_ENV",
    "OHLCVAdapter",
    "OHLCVPoint",
    "CachedOHLCVAdapter",
    "HyperliquidCachedSourceAdapter",
    "OpenBBCachedSourceAdapter",
    "build_default_adapters",
    "fetch_universe",
    "synthetic_ohlcv",
    "to_close_series",
]
