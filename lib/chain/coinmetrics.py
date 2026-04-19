"""CoinMetrics on-chain data provider (community API — no key required).

Fetches NVT ratio, realized cap, SOPR, and active addresses from the
CoinMetrics community endpoint for BTC/ETH/SOL.  Results are cached in
`data/chain/coinmetrics/` for 6 hours to avoid hammering the public API.

API docs: https://docs.coinmetrics.io/api/v4
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "chain" / "coinmetrics"
_CACHE_TTL_HOURS = 6
_BASE_URL = "https://community-api.coinmetrics.io/v4"

# Community API metrics available without a key
_METRICS = "NVTAdj,CapRealUSD,SoprFree,AdrActCnt"


@dataclass
class CoinMetricsSnapshot:
    asset: str
    timestamp: str
    nvt: float | None = None
    realized_cap_usd: float | None = None
    sopr: float | None = None
    active_addresses: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "timestamp": self.timestamp,
            "nvt": self.nvt,
            "realized_cap_usd": self.realized_cap_usd,
            "sopr": self.sopr,
            "active_addresses": self.active_addresses,
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
        f"?assets={asset.lower()}&metrics={_METRICS}&start_time={start}&end_time={end}&limit=3"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Sapphire/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


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
            nvt=_float(latest.get("NVTAdj")),
            realized_cap_usd=_float(latest.get("CapRealUSD")),
            sopr=_float(latest.get("SoprFree")),
            active_addresses=_int(latest.get("AdrActCnt")),
            raw=latest,
        )
        cache.write_text(json.dumps(snap.to_dict()))
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
