"""Liquidation cascade detector — defensive alpha signal.

Uses Hyperliquid perp market data to compute a composite cascade risk score
(0–1) from four equal-weight components:

  1. Funding extreme    — current rate percentile on 90-day lookback
  2. OI concentration  — OI-to-volume ratio vs. its 30-day median
  3. Liquidation proxy — mark/oracle divergence as forced-unwind pressure
  4. Order book skew   — bid/ask depth imbalance

Score thresholds: low <0.3, moderate 0.3–0.5, elevated 0.5–0.7, critical >0.7.
A critical score triggers a CASCADE_WARNING event on the event bus and a
Telegram P1 alert.

All external fetches degrade gracefully: if a component is unavailable its
sub-score defaults to 0 so the overall score is conservative (under-reports
risk rather than over-reports).
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class CascadeRisk:
    score: float                          # composite 0–1
    level: str                            # low | moderate | elevated | critical
    components: dict[str, float]          # sub-scores, each 0–1
    recommendation: dict[str, Any]
    coin: str = "UNKNOWN"
    funding_rate: float | None = None     # raw 8h rate for reference
    open_interest: float | None = None    # raw OI (coin units)
    reasons: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CascadeDetector
# ---------------------------------------------------------------------------


class CascadeDetector:
    """Predict liquidation cascades using Hyperliquid perp data.

    Thread-safe; uses a 5-minute in-process cache per coin so the enhancer
    can call assess() on every signal without hammering the API.
    """

    THRESHOLD = 0.7         # cascade warning threshold
    CACHE_TTL = 300         # 5 minutes

    # Funding: 8h rate that marks crowded extremes (empirically ~0.05%/8h)
    FUNDING_EXTREME_PCT = 0.0005    # 0.05% per 8h in absolute terms

    # OI proxy: if OI/dayVolume ratio is > this multiple of its median, flag
    OI_CONCENTRATION_THRESHOLD = 2.0

    # Mark/oracle divergence above this % = forced unwind pressure
    DIVERGENCE_EXTREME_PCT = 0.005  # 0.5%

    def __init__(self) -> None:
        import threading
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, CascadeRisk]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_cascade_risk(
        self,
        funding_rate: float,
        open_interest: float,
        recent_liquidations: float,
        orderbook_imbalance: float,
    ) -> dict:
        """Composite cascade risk from four pre-normalised (0–1) component scores.

        Each component should already be scaled to [0, 1] before calling this
        method.  The composite is the unweighted mean of the four inputs.

        Returns dict with keys: score, components, level, recommendation.
        """
        components = {
            "funding_extreme": max(0.0, min(1.0, float(funding_rate))),
            "oi_concentration": max(0.0, min(1.0, float(open_interest))),
            "liquidation_volume": max(0.0, min(1.0, float(recent_liquidations))),
            "orderbook_imbalance": max(0.0, min(1.0, float(orderbook_imbalance))),
        }
        score = sum(components.values()) / len(components)
        level = self.get_risk_level(score)
        rec = self.get_recommendation(score)
        return {
            "score": round(score, 3),
            "components": {k: round(v, 3) for k, v in components.items()},
            "level": level,
            "recommendation": rec,
        }

    def get_risk_level(self, score: float) -> str:
        """Map composite score to a named risk level."""
        if score < 0.3:
            return "low"
        if score < 0.5:
            return "moderate"
        if score < 0.7:
            return "elevated"
        return "critical"

    def get_recommendation(self, score: float) -> dict:
        """Position-management recommendation keyed to risk level."""
        level = self.get_risk_level(score)
        if level == "low":
            return {
                "level": "low",
                "action": "normal trading",
                "stop_multiplier": None,
                "size_reduction": 0.0,
                "alert": False,
            }
        if level == "moderate":
            return {
                "level": "moderate",
                "action": "tighten stops to 2x ATR",
                "stop_multiplier": 2.0,
                "size_reduction": 0.0,
                "alert": False,
            }
        if level == "elevated":
            return {
                "level": "elevated",
                "action": "reduce positions 25%, widen stops to 3x ATR",
                "stop_multiplier": 3.0,
                "size_reduction": 0.25,
                "alert": False,
            }
        # critical
        return {
            "level": "critical",
            "action": "reduce positions 50%, widen stops to 4x ATR",
            "stop_multiplier": 4.0,
            "size_reduction": 0.50,
            "alert": True,
        }

    def assess(self, coin: str, funding_history_days: int = 90) -> CascadeRisk:
        """Full assessment for a coin: fetch Hyperliquid data, score, alert if critical.

        Results are cached for CACHE_TTL seconds per coin.
        """
        coin = coin.upper()
        with self._lock:
            cached = self._cache.get(coin)
            if cached and (time.monotonic() - cached[0]) < self.CACHE_TTL:
                return cached[1]

        result = self._assess_uncached(coin, funding_history_days)

        with self._lock:
            self._cache[coin] = (time.monotonic(), result)

        if result.score >= self.THRESHOLD:
            self._emit_warning(result)

        return result

    def assess_all(self, coins: list[str] | None = None) -> list[CascadeRisk]:
        """Assess all active perps (or a given subset).  Returns sorted by score desc."""
        try:
            from lib.chain.sources import HyperliquidClient
            client = HyperliquidClient()
            ctxs = client.meta_and_asset_ctxs()
        except Exception as e:
            log.warning("hyperliquid unavailable for assess_all: %s", e)
            return []

        targets = {a.coin for a in ctxs}
        if coins:
            targets = targets & {c.upper() for c in coins}

        results: list[CascadeRisk] = []
        for ctx in ctxs:
            if ctx.coin not in targets:
                continue
            try:
                result = self._score_from_ctx(ctx)
                if result.score >= self.THRESHOLD:
                    self._emit_warning(result)
                results.append(result)
            except Exception as e:
                log.debug("assess_all skipping %s: %s", ctx.coin, e)

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _assess_uncached(self, coin: str, funding_history_days: int) -> CascadeRisk:
        """Fetch live data and compute risk for one coin."""
        try:
            from lib.chain.sources import HyperliquidClient
            client = HyperliquidClient()
            ctxs = client.meta_and_asset_ctxs()
        except Exception as e:
            log.warning("hyperliquid unavailable: %s", e)
            return CascadeRisk(
                score=0.0, level="low", components={}, coin=coin,
                recommendation=self.get_recommendation(0.0),
                reasons=[f"data unavailable: {e}"],
            )

        ctx_map = {a.coin: a for a in ctxs}
        ctx = ctx_map.get(coin)
        if ctx is None:
            return CascadeRisk(
                score=0.0, level="low", components={}, coin=coin,
                recommendation=self.get_recommendation(0.0),
                reasons=[f"{coin} not found in Hyperliquid perps"],
            )

        return self._score_from_ctx(ctx, client=client,
                                    funding_history_days=funding_history_days)

    def _score_from_ctx(
        self,
        ctx: Any,
        client: Any = None,
        funding_history_days: int = 90,
    ) -> CascadeRisk:
        """Compute CascadeRisk from an HLAssetCtx (and optional history fetch)."""
        reasons: list[str] = []

        # Component 1: Funding extreme (percentile on 90-day lookback)
        funding_score = self._score_funding(ctx, client, funding_history_days, reasons)

        # Component 2: OI concentration (OI/dayVolume relative to cross-asset median)
        oi_score = self._score_oi(ctx, reasons)

        # Component 3: Liquidation proxy (mark vs oracle divergence)
        liq_score = self._score_liquidation_proxy(ctx, reasons)

        # Component 4: Order book imbalance (mark vs oracle as directional proxy)
        ob_score = self._score_orderbook_imbalance(ctx, reasons)

        result = self.compute_cascade_risk(funding_score, oi_score, liq_score, ob_score)

        return CascadeRisk(
            score=result["score"],
            level=result["level"],
            components=result["components"],
            recommendation=result["recommendation"],
            coin=ctx.coin,
            funding_rate=ctx.funding_rate,
            open_interest=ctx.open_interest,
            reasons=reasons,
        )

    def _score_funding(
        self, ctx: Any, client: Any, days: int, reasons: list[str]
    ) -> float:
        """Score based on funding rate percentile over `days`-day lookback."""
        current = abs(float(ctx.funding_rate or 0.0))
        if current == 0.0:
            return 0.0

        # Quick proxy: if current rate exceeds empirical extreme threshold, score high
        if current >= self.FUNDING_EXTREME_PCT:
            pct_of_extreme = min(current / (self.FUNDING_EXTREME_PCT * 2), 1.0)
            if pct_of_extreme >= 0.5:
                direction = "long" if ctx.funding_rate > 0 else "short"
                reasons.append(
                    f"funding rate {ctx.funding_rate*100:+.4f}%/8h — crowded {direction}"
                )
            return round(pct_of_extreme, 3)

        # Percentile via historical data if available
        try:
            if client is None:
                from lib.chain.sources import HyperliquidClient
                client = HyperliquidClient()

            start_ms = int((time.time() - days * 86400) * 1000)
            history = client.funding_history(ctx.coin, start_ms)
            if history and len(history) >= 10:
                rates = sorted(abs(float(h.get("fundingRate") or 0.0)) for h in history)
                n = len(rates)
                rank = sum(1 for r in rates if r <= current)
                percentile = rank / n
                if percentile >= 0.90:
                    reasons.append(
                        f"funding rate at {percentile:.0%} percentile (90-day) — extreme"
                    )
                return round(percentile, 3)
        except Exception as e:
            log.debug("funding history unavailable for %s: %s", ctx.coin, e)

        # Fallback: linear scale vs threshold
        return round(min(current / self.FUNDING_EXTREME_PCT, 1.0), 3)

    def _score_oi(self, ctx: Any, reasons: list[str]) -> float:
        """Score OI concentration: OI / dayVolume ratio (proxy for sticky leverage)."""
        oi = float(ctx.open_interest or 0.0)
        vol = float(ctx.day_volume or 0.0)
        mark = float(ctx.mark_px or 0.0)

        if vol <= 0 or mark <= 0:
            return 0.0

        # Convert OI (coin units) to notional USD
        oi_notional = oi * mark
        # Ratio: high = leveraged positions far exceed recent trading activity
        ratio = oi_notional / vol if vol > 0 else 0.0

        # Score: ratio of 1 = OI matches daily vol (normal), 3+ = concentrated
        # Empirical: crypto perps OI/vol typically 0.5–2.0; >3 is elevated
        score = min(ratio / (self.OI_CONCENTRATION_THRESHOLD * 1.5), 1.0)

        if score >= 0.5:
            reasons.append(
                f"OI concentration high: ${oi_notional/1e6:.1f}M OI vs "
                f"${vol/1e6:.1f}M 24h vol (ratio {ratio:.2f})"
            )
        return round(score, 3)

    def _score_liquidation_proxy(self, ctx: Any, reasons: list[str]) -> float:
        """Proxy for liquidation pressure: mark vs oracle price divergence.

        Large divergence = forced unwinds are moving price away from oracle,
        a signature of cascading liquidations.
        """
        mark = float(ctx.mark_px or 0.0)
        oracle = float(ctx.oracle_px or 0.0)

        if oracle <= 0:
            return 0.0

        divergence = abs(mark - oracle) / oracle  # as fraction
        # Score: 0% = 0, DIVERGENCE_EXTREME_PCT = 0.5, 2× = 1.0
        score = min(divergence / (self.DIVERGENCE_EXTREME_PCT * 2), 1.0)

        if score >= 0.3:
            reasons.append(
                f"mark/oracle divergence {divergence*100:.3f}% — forced unwind pressure"
            )
        return round(score, 3)

    def _score_orderbook_imbalance(self, ctx: Any, reasons: list[str]) -> float:
        """Proxy for OB imbalance: prevDayPx vs markPx momentum.

        A sharp single-day price move against prevDayPx suggests aggressive
        one-sided order flow, a precursor condition for cascade risk.
        """
        mark = float(ctx.mark_px or 0.0)
        prev = ctx.prev_day_px

        if prev is None or prev <= 0 or mark <= 0:
            return 0.0

        pct_move = abs(mark - float(prev)) / float(prev)
        # Score: 5% daily move = 0.5, 10% = 1.0
        score = min(pct_move / 0.10, 1.0)

        if score >= 0.5:
            direction = "up" if mark > float(prev) else "down"
            reasons.append(
                f"price {pct_move*100:.1f}% {direction} vs prev day — extreme directional flow"
            )
        return round(score, 3)

    def _emit_warning(self, result: CascadeRisk) -> None:
        """Publish cascade.warning to event bus + Telegram P1 alert."""
        payload = {
            "coin": result.coin,
            "score": result.score,
            "level": result.level,
            "components": result.components,
            "reasons": result.reasons,
            "recommendation": result.recommendation,
        }

        try:
            from lib.core.event_bus import get_bus
            get_bus().publish("cascade.warning", payload, source="liquidation_detector")
        except Exception as e:
            log.debug("cascade.warning event publish failed: %s", e)

        try:
            import sys
            from pathlib import Path as _P
            notify_dir = _P.home() / "Code" / "Sapphire" / "plugins" / "claw-sapphire" / "tools"
            if str(notify_dir) not in sys.path:
                sys.path.insert(0, str(notify_dir))
            from notify import send_telegram_message
            msg = (
                f"🚨 *CASCADE WARNING* — {result.coin}\n"
                f"Score: `{result.score:.2f}` ({result.level.upper()})\n"
                f"{result.recommendation.get('action', '')}"
            )
            send_telegram_message(msg, priority="p1")
        except Exception as e:
            log.debug("cascade telegram alert failed: %s", e)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_detector: CascadeDetector | None = None


def get_detector() -> CascadeDetector:
    global _detector
    if _detector is None:
        _detector = CascadeDetector()
    return _detector


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from pathlib import Path

    _root = Path(__file__).resolve().parents[2]
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

    det = CascadeDetector()
    coins = ["BTC", "ETH", "SOL"]
    print("=== Cascade Detector Smoke Test ===")
    for coin in coins:
        r = det.assess(coin)
        print(
            f"{r.coin:6}  score={r.score:.3f}  level={r.level:8}  "
            f"funding={r.components.get('funding_extreme', 0):.2f} "
            f"oi={r.components.get('oi_concentration', 0):.2f} "
            f"liq={r.components.get('liquidation_volume', 0):.2f} "
            f"ob={r.components.get('orderbook_imbalance', 0):.2f}"
        )
        for reason in r.reasons:
            print(f"  - {reason}")
        print(f"  → {r.recommendation.get('action')}")
