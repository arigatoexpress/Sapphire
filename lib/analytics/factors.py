"""Cross-sectional factor model for crypto + equity assets.

Factors computed:
- Momentum     : 30-day price return (%)
- Short Mom    : 7-day price return (%)
- Volatility   : 30-day realized vol (lower is better — inverted for ranking)
- Volume Score : 24h volume vs 30d avg (volume z-score proxy)
- Market Cap   : raw log market cap (size factor)
- Dominance    : for crypto, % of total crypto mcap
- Liquidity    : volume / market cap (turnover ratio)

Data source: CoinGecko public API (cached 1h to avoid rate-limit abuse)
Asset universe: BTC, ETH, SOL, BNB, AVAX, LINK, ARB, MATIC

Usage:
    from lib.analytics.factors import CrossSectionalFactors
    csf = CrossSectionalFactors()
    result = csf.compute()
    # result.ranked_assets: assets sorted by composite score
    # result.factor_matrix: {asset: {factor: z-score}}
"""

from __future__ import annotations

import logging
import math
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)

# CoinGecko IDs for the asset universe
ASSET_UNIVERSE = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
    "AVAX": "avalanche-2",
    "LINK": "chainlink",
    "ARB": "arbitrum",
    "MATIC": "matic-network",
}

FACTOR_NAMES = [
    "Momentum 30d",
    "Momentum 7d",
    "Volatility",
    "Volume Score",
    "Market Cap",
    "Liquidity",
]

# 1-hour cache for factor data (avoid CoinGecko rate limits)
_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 3600  # 1 hour


def _cache_get(key: str) -> Any | None:
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if entry and (time.monotonic() - entry[0]) < _CACHE_TTL:
            return entry[1]
    return None


def _cache_set(key: str, value: Any) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic(), value)


@dataclass
class AssetFactors:
    symbol: str
    factors: dict[str, float]  # factor_name -> raw value
    z_scores: dict[str, float]  # factor_name -> z-score (cross-sectional)
    composite_score: float  # equal-weighted z-score average (higher = stronger)
    rank: int = 0  # 1 = strongest


@dataclass
class FactorReport:
    timestamp: float
    assets: list[AssetFactors]
    ranked_assets: list[str]  # symbols in rank order
    factor_matrix: dict[str, dict[str, float]]  # {asset: {factor: z-score}}
    dispersion: float  # spread of composite scores (std dev)
    strongest: str | None
    weakest: str | None


def _safe_pct_change(prices: list[float], lookback: int) -> float | None:
    """Compute % change over `lookback` periods from a price list."""
    if len(prices) < lookback + 1:
        return None
    old = prices[-(lookback + 1)]
    new = prices[-1]
    if old == 0:
        return None
    return (new - old) / old * 100.0


def _realized_vol(prices: list[float], window: int = 30) -> float | None:
    """Annualized realized volatility from daily close prices."""
    if len(prices) < window + 1:
        return None
    returns = []
    for i in range(len(prices) - window, len(prices)):
        if prices[i - 1] > 0:
            returns.append(math.log(prices[i] / prices[i - 1]))
    if len(returns) < 5:
        return None
    n = len(returns)
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / (n - 1)
    return math.sqrt(var * 365) * 100.0  # annualized %


def _cross_sectional_z(values: dict[str, float | None]) -> dict[str, float]:
    """Compute cross-sectional z-scores across assets for one factor."""
    valid = {k: v for k, v in values.items() if v is not None}
    if len(valid) < 2:
        return {k: 0.0 for k in values}
    n = len(valid)
    mean = sum(valid.values()) / n
    var = sum((v - mean) ** 2 for v in valid.values()) / n
    std = math.sqrt(var) if var > 0 else 1.0
    return {k: (values[k] - mean) / std if values[k] is not None else 0.0 for k in values}


def _fetch_market_data(coin_id: str) -> dict | None:
    """Fetch 35d OHLCV + market data from CoinGecko for one coin."""
    cache_key = f"cg_market_{coin_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        from lib.chain.sources import _http_get

        # Market chart: 35 days at daily resolution
        chart = _http_get(
            f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
            f"?vs_currency=usd&days=35&interval=daily"
        )
        # Current market data
        detail = _http_get(
            f"https://api.coingecko.com/api/v3/coins/{coin_id}"
            f"?localization=false&tickers=false&community_data=false"
            f"&developer_data=false&sparkline=false"
        )
        result = {"chart": chart, "detail": detail}
        _cache_set(cache_key, result)
        return result
    except Exception as e:
        log.warning("CoinGecko fetch failed for %s: %s", coin_id, e)
        return None


class CrossSectionalFactors:
    """Compute cross-sectional factor scores for the crypto asset universe."""

    def compute(self, symbols: list[str] | None = None) -> FactorReport:
        """Compute factor scores for the given symbols (defaults to full universe).

        Results are cached for 1 hour to avoid CoinGecko rate limits.
        """
        cache_key = "factor_report"
        cached = _cache_get(cache_key)
        if cached is not None and symbols is None:
            return cached

        if symbols is None:
            symbols = list(ASSET_UNIVERSE.keys())

        raw_factors: dict[str, dict[str, float | None]] = {sym: {} for sym in symbols}

        for sym in symbols:
            cg_id = ASSET_UNIVERSE.get(sym)
            if cg_id is None:
                log.warning("No CoinGecko ID for %s — skipping", sym)
                continue

            data = _fetch_market_data(cg_id)
            if data is None:
                continue

            chart = data.get("chart") or {}
            detail = data.get("detail") or {}

            prices_raw = chart.get("prices") or []
            volumes_raw = chart.get("total_volumes") or []

            prices = [p[1] for p in prices_raw if len(p) == 2]
            volumes = [v[1] for v in volumes_raw if len(v) == 2]

            raw_factors[sym]["Momentum 30d"] = _safe_pct_change(prices, 30)
            raw_factors[sym]["Momentum 7d"] = _safe_pct_change(prices, 7)
            raw_factors[sym]["Volatility"] = _realized_vol(prices, 30)

            # Volume z-score: today vs 30d avg
            if volumes and len(volumes) >= 8:
                vol_30d_avg = (
                    sum(volumes[-31:-1]) / len(volumes[-31:-1])
                    if len(volumes) > 31
                    else sum(volumes[:-1]) / max(len(volumes) - 1, 1)
                )
                today_vol = volumes[-1]
                raw_factors[sym]["Volume Score"] = (
                    (today_vol - vol_30d_avg) / vol_30d_avg * 100.0 if vol_30d_avg > 0 else 0.0
                )
            else:
                raw_factors[sym]["Volume Score"] = None

            market_data = detail.get("market_data") or {}
            mcap = (market_data.get("market_cap") or {}).get("usd")
            raw_factors[sym]["Market Cap"] = math.log10(mcap) if mcap and mcap > 0 else None

            vol_usd = (market_data.get("total_volume") or {}).get("usd")
            if mcap and mcap > 0 and vol_usd:
                raw_factors[sym]["Liquidity"] = vol_usd / mcap * 100.0
            else:
                raw_factors[sym]["Liquidity"] = None

        # Validate fetch coverage before computing z-scores
        fetched_ok = [
            sym for sym in symbols if any(v is not None for v in raw_factors.get(sym, {}).values())
        ]
        if len(fetched_ok) < len(symbols):
            missing = sorted(set(symbols) - set(fetched_ok))
            log.warning(
                "factors: %d/%d assets have data (missing: %s) — z-scores will use 0.0 fill",
                len(fetched_ok),
                len(symbols),
                ", ".join(missing),
            )
        else:
            log.info("factors: all %d assets fetched from CoinGecko", len(symbols))

        # Cross-sectional z-scores per factor
        factor_z: dict[str, dict[str, float]] = {}
        for fn in FACTOR_NAMES:
            vals = {sym: raw_factors[sym].get(fn) for sym in symbols}
            # Volatility: lower is better → invert z-scores
            z = _cross_sectional_z(vals)
            if fn == "Volatility":
                z = {k: -v for k, v in z.items()}
            factor_z[fn] = z

        # Composite score: equal-weighted mean of z-scores
        asset_list: list[AssetFactors] = []
        for sym in symbols:
            z_scores = {fn: factor_z[fn].get(sym, 0.0) for fn in FACTOR_NAMES}
            composite = sum(z_scores.values()) / len(z_scores)
            asset_list.append(
                AssetFactors(
                    symbol=sym,
                    factors={fn: raw_factors[sym].get(fn) for fn in FACTOR_NAMES},  # type: ignore[misc]
                    z_scores=z_scores,
                    composite_score=round(composite, 3),
                )
            )

        # Rank by composite score descending
        asset_list.sort(key=lambda a: a.composite_score, reverse=True)
        for i, a in enumerate(asset_list):
            a.rank = i + 1

        ranked = [a.symbol for a in asset_list]
        factor_matrix = {a.symbol: a.z_scores for a in asset_list}

        scores = [a.composite_score for a in asset_list]
        if len(scores) > 1:
            mean_s = sum(scores) / len(scores)
            dispersion = math.sqrt(sum((s - mean_s) ** 2 for s in scores) / len(scores))
        else:
            dispersion = 0.0

        report = FactorReport(
            timestamp=time.time(),
            assets=asset_list,
            ranked_assets=ranked,
            factor_matrix=factor_matrix,
            dispersion=round(dispersion, 3),
            strongest=ranked[0] if ranked else None,
            weakest=ranked[-1] if ranked else None,
        )

        if symbols is None or set(symbols) == set(ASSET_UNIVERSE.keys()):
            _cache_set(cache_key, report)
        return report


def to_dict(report: FactorReport) -> dict:
    """Serialize FactorReport to JSON-safe dict for dashboard API."""
    return {
        "timestamp": report.timestamp,
        "factor_names": FACTOR_NAMES,
        "ranked_assets": report.ranked_assets,
        "strongest": report.strongest,
        "weakest": report.weakest,
        "dispersion": report.dispersion,
        "asset_count": len(report.assets),
        "assets": [
            {
                "symbol": a.symbol,
                "rank": a.rank,
                "composite_score": a.composite_score,
                "factors": {fn: a.factors.get(fn) for fn in FACTOR_NAMES},
                "z_scores": {fn: round(a.z_scores.get(fn, 0.0), 3) for fn in FACTOR_NAMES},
            }
            for a in report.assets
        ],
        "factor_matrix": {
            sym: {fn: round(z, 3) for fn, z in factors.items()}
            for sym, factors in report.factor_matrix.items()
        },
    }
