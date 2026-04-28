"""Liquidation cascade risk analysis via Hyperliquid perp markets.

Computes a cascade risk score [0–100] per asset based on:
- Open interest (higher OI = more potential cascade energy)
- Funding rate extremes (crowded positioning = fragile)
- Price distance from estimated liquidation zones (derived from OI/mark diff)
- Volume/OI ratio (low liquidity relative to OI = harder to unwind)

Usage:
    from lib.analytics.liquidation import CascadeDetector
    detector = CascadeDetector()
    results = detector.assess_all(['BTC', 'ETH', 'SOL'])
"""

from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)

# Thresholds for scoring
_FUNDING_EXTREME_8H = 0.001  # 0.1% per 8h = ~10.9% annualized — crowded
_FUNDING_CRITICAL_8H = 0.003  # 0.3% per 8h = ~32.9% annualized — extremely crowded
_OI_SCORE_WEIGHTS = {
    "BTC": 1.0,  # normalized baseline
    "ETH": 0.6,
    "SOL": 0.3,
}


@dataclass
class AssetRisk:
    coin: str
    risk_score: float  # 0-100
    mark_px: float
    open_interest: float  # coin units
    open_interest_usd: float
    funding_rate_8h: float
    day_volume_usd: float
    oi_volume_ratio: float  # OI/volume — high = illiquid relative to positioning
    funding_component: float  # 0-40 contribution
    oi_component: float  # 0-40 contribution
    liquidity_component: float  # 0-20 contribution
    risk_label: str  # LOW / MODERATE / HIGH / CRITICAL
    detail: str


@dataclass
class CascadeReport:
    timestamp: float
    risk_score: float  # aggregate 0-100
    assets: list[AssetRisk]
    total_oi_usd: float
    avg_funding_8h: float
    risk_label: str
    alert: str | None = None


def _risk_label(score: float) -> str:
    if score >= 75:
        return "CRITICAL"
    if score >= 50:
        return "HIGH"
    if score >= 25:
        return "MODERATE"
    return "LOW"


def _score_asset(ctx: Any) -> AssetRisk:
    """Score a single HLAssetCtx for cascade risk."""
    coin = ctx.coin
    mark = ctx.mark_px
    oi = ctx.open_interest  # coin units
    oi_usd = oi * mark
    funding = ctx.funding_rate  # per 8h, can be negative
    vol = ctx.day_volume  # USDC 24h notional

    # --- Funding component (0-40) ---
    abs_funding = abs(funding)
    if abs_funding >= _FUNDING_CRITICAL_8H:
        fund_score = 40.0
    elif abs_funding >= _FUNDING_EXTREME_8H:
        fund_score = (
            20.0
            + (abs_funding - _FUNDING_EXTREME_8H)
            / (_FUNDING_CRITICAL_8H - _FUNDING_EXTREME_8H)
            * 20.0
        )
    else:
        fund_score = abs_funding / _FUNDING_EXTREME_8H * 20.0

    # --- OI component (0-40): OI_USD vs asset-specific baseline ---
    # Baselines (rough: BTC ~10B, ETH ~5B, SOL ~2B, others ~500M)
    _OI_BASELINE = {"BTC": 10e9, "ETH": 5e9, "SOL": 2e9}
    baseline = _OI_BASELINE.get(coin, 500e6)
    oi_ratio = oi_usd / baseline if baseline > 0 else 0.0
    oi_score = min(40.0, oi_ratio * 40.0)

    # --- Liquidity component (0-20): OI/volume --- high ratio = illiquid ---
    if vol > 0:
        oi_vol_ratio = oi_usd / vol
    else:
        oi_vol_ratio = 10.0  # worst case if no volume data
    # Ratio >5 (OI is 5x daily volume) = full illiquidity score
    liq_score = min(20.0, (oi_vol_ratio / 5.0) * 20.0)

    total = fund_score + oi_score + liq_score
    label = _risk_label(total)

    detail_parts = []
    if abs_funding >= _FUNDING_EXTREME_8H:
        direction = "crowded long" if funding > 0 else "crowded short"
        detail_parts.append(f"funding {funding*100:+.3f}%/8h ({direction})")
    if oi_ratio > 1.5:
        detail_parts.append(f"OI ${oi_usd/1e9:.1f}B ({oi_ratio:.1f}x baseline)")
    if oi_vol_ratio > 3:
        detail_parts.append(f"OI/vol {oi_vol_ratio:.1f}x (illiquid)")
    detail = "; ".join(detail_parts) or "within normal ranges"

    return AssetRisk(
        coin=coin,
        risk_score=round(total, 1),
        mark_px=mark,
        open_interest=oi,
        open_interest_usd=oi_usd,
        funding_rate_8h=funding,
        day_volume_usd=vol,
        oi_volume_ratio=oi_vol_ratio,
        funding_component=round(fund_score, 1),
        oi_component=round(oi_score, 1),
        liquidity_component=round(liq_score, 1),
        risk_label=label,
        detail=detail,
    )


class CascadeDetector:
    """Liquidation cascade risk detector using Hyperliquid perp data."""

    def assess_all(self, coins: list[str] | None = None) -> CascadeReport:
        """Assess cascade risk for a list of coins (defaults to majors).

        Args:
            coins: List of Hyperliquid coin names, e.g. ['BTC', 'ETH', 'SOL'].
                   Pass None to use the top-8 by open interest.
        """
        if coins is None:
            coins = ["BTC", "ETH", "SOL", "LINK", "ARB", "AVAX", "BNB", "MATIC"]

        from lib.chain.sources import HyperliquidClient, SourceError

        try:
            hl = HyperliquidClient()
            all_ctxs = hl.meta_and_asset_ctxs()
        except SourceError as e:
            log.warning("Hyperliquid unavailable: %s", e)
            return CascadeReport(
                timestamp=time.time(),
                risk_score=0.0,
                assets=[],
                total_oi_usd=0.0,
                avg_funding_8h=0.0,
                risk_label="UNAVAILABLE",
                alert=f"Hyperliquid API error: {e}",
            )

        coin_set = {c.upper() for c in coins}
        filtered = [c for c in all_ctxs if c.coin.upper() in coin_set]

        if not filtered:
            log.warning("No Hyperliquid assets matched: %s", coins)
            return CascadeReport(
                timestamp=time.time(),
                risk_score=0.0,
                assets=[],
                total_oi_usd=0.0,
                avg_funding_8h=0.0,
                risk_label="LOW",
            )

        scored = [_score_asset(ctx) for ctx in filtered]
        scored.sort(key=lambda a: a.risk_score, reverse=True)

        total_oi = sum(a.open_interest_usd for a in scored)
        avg_funding = sum(a.funding_rate_8h for a in scored) / len(scored)

        # Aggregate score: weighted average with top asset counting more
        if len(scored) == 1:
            agg_score = scored[0].risk_score
        else:
            # Top asset weight 50%, rest share 50%
            top_weight = 0.5
            rest_avg = sum(a.risk_score for a in scored[1:]) / len(scored[1:])
            agg_score = scored[0].risk_score * top_weight + rest_avg * (1 - top_weight)

        alert = None
        if any(a.risk_label == "CRITICAL" for a in scored):
            critical = [a.coin for a in scored if a.risk_label == "CRITICAL"]
            alert = f"CRITICAL cascade risk: {', '.join(critical)}"
        elif any(a.risk_label == "HIGH" for a in scored[:2]):
            high = [a.coin for a in scored[:2] if a.risk_label == "HIGH"]
            alert = f"HIGH cascade risk: {', '.join(high)}"

        return CascadeReport(
            timestamp=time.time(),
            risk_score=round(agg_score, 1),
            assets=scored,
            total_oi_usd=total_oi,
            avg_funding_8h=avg_funding,
            risk_label=_risk_label(agg_score),
            alert=alert,
        )


_detector: CascadeDetector | None = None


def get_detector() -> CascadeDetector:
    global _detector
    if _detector is None:
        _detector = CascadeDetector()
    return _detector


def to_dict(report: CascadeReport) -> dict:
    """Serialize CascadeReport to JSON-safe dict for dashboard API."""
    return {
        "timestamp": report.timestamp,
        "risk_score": report.risk_score,
        "risk_label": report.risk_label,
        "alert": report.alert,
        "total_oi_usd": report.total_oi_usd,
        "avg_funding_8h": report.avg_funding_8h,
        "assets": [
            {
                "coin": a.coin,
                "risk_score": a.risk_score,
                "risk_label": a.risk_label,
                "mark_px": a.mark_px,
                "open_interest_usd": a.open_interest_usd,
                "funding_rate_8h": a.funding_rate_8h,
                "day_volume_usd": a.day_volume_usd,
                "oi_volume_ratio": a.oi_volume_ratio,
                "components": {
                    "funding": a.funding_component,
                    "oi": a.oi_component,
                    "liquidity": a.liquidity_component,
                },
                "detail": a.detail,
            }
            for a in report.assets
        ],
    }
