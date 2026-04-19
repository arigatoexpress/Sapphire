"""CoinMetrics on-chain data provider (community API — no key required).

Fetches price, supply, active addresses, transaction count, and hash rate
from the CoinMetrics community endpoint for BTC/ETH/SOL.  Results are cached
in `data/chain/coinmetrics/` for 6 hours.

Community tier metrics (verified 2026-04-18): PriceUSD, SplyCur, AdrActCnt,
TxCnt, HashRate.  NVTAdj / CapRealUSD / SoprFree are paid-tier only.

API docs: https://docs.coinmetrics.io/api/v4
"""

from __future__ import annotations

import json
import logging
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import certifi

_SSL_CTX = ssl.create_default_context(cafile=certifi.where())
log = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "chain" / "coinmetrics"
_CACHE_TTL_HOURS = 6
_BASE_URL = "https://community-api.coinmetrics.io/v4"

# Free community-tier metrics (403 on NVTAdj / CapRealUSD / SoprFree)
_METRICS = "PriceUSD,SplyCur,AdrActCnt,TxCnt,HashRate"


@dataclass
class CoinMetricsSnapshot:
    asset: str
    timestamp: str
    price_usd: float | None = None
    supply: float | None = None
    active_addresses: int | None = None
    tx_count: int | None = None
    hash_rate: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "timestamp": self.timestamp,
            "price_usd": self.price_usd,
            "supply": self.supply,
            "active_addresses": self.active_addresses,
            "tx_count": self.tx_count,
            "hash_rate": self.hash_rate,
        }


def _cache_path(asset: str) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / f"{asset.lower()}.json"


def _cache_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return datetime.now(UTC) - mtime < timedelta(hours=_CACHE_TTL_HOURS)


def _fetch_raw(asset: str) -> dict[str, Any]:
    end = datetime.now(UTC).strftime("%Y-%m-%d")
    start = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%d")
    url = (
        f"{_BASE_URL}/timeseries/asset-metrics"
        f"?assets={asset.lower()}&metrics={_METRICS}"
        f"&start_time={start}&end_time={end}&page_size=3"
    )
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Sapphire/1.0"})
            with urllib.request.urlopen(req, context=_SSL_CTX, timeout=10) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise last_exc or OSError(f"fetch failed for {asset}")


def get_snapshot(asset: str) -> CoinMetricsSnapshot:
    """Return latest on-chain metrics for *asset* (BTC/ETH/SOL/etc.)."""
    cache = _cache_path(asset)
    if _cache_fresh(cache):
        try:
            data = json.loads(cache.read_text())
            return CoinMetricsSnapshot(**data)
        except Exception:
            pass

    try:
        raw = _fetch_raw(asset)
        rows = raw.get("data", [])
        if not rows:
            raise ValueError(f"no data rows for {asset}")
        latest = rows[-1]
        snap = CoinMetricsSnapshot(
            asset=asset,
            timestamp=latest.get("time", datetime.now(UTC).isoformat()),
            price_usd=_float(latest.get("PriceUSD")),
            supply=_float(latest.get("SplyCur")),
            active_addresses=_int(latest.get("AdrActCnt")),
            tx_count=_int(latest.get("TxCnt")),
            hash_rate=_float(latest.get("HashRate")),
            raw=latest,
        )
        cache.write_text(json.dumps(snap.to_dict()))
        log.info(
            "coinmetrics: %s price=$%s active_addr=%s tx=%s",
            asset,
            f"{snap.price_usd:,.0f}" if snap.price_usd else "—",
            f"{snap.active_addresses:,}" if snap.active_addresses else "—",
            f"{snap.tx_count:,}" if snap.tx_count else "—",
        )
        return snap
    except Exception as exc:
        log.warning("coinmetrics fetch failed for %s: %s", asset, exc)
        return CoinMetricsSnapshot(
            asset=asset,
            timestamp=datetime.now(UTC).isoformat(),
        )


def _float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _int(v: Any) -> int | None:
    try:
        return int(float(v)) if v is not None else None
    except (TypeError, ValueError):
        return None


def get_multi(assets: list[str] | None = None) -> list[CoinMetricsSnapshot]:
    """Fetch snapshots for a list of assets (default: BTC, ETH, SOL)."""
    if assets is None:
        assets = ["BTC", "ETH", "SOL"]
    return [get_snapshot(a) for a in assets]
