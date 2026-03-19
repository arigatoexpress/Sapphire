"""
Prediction Market Signal Aggregator

Combines signals from Polymarket, Kalshi, and future sources into a unified
prediction intelligence layer. Provides:
  - Cross-source consensus detection
  - Cross-venue arbitrage detection (Polymarket vs Kalshi spread finding)
  - Symbol-level sentiment aggregation
  - Cognition context generation for DualSpeedCognition prompts
  - Forum summary generation for Scout posts
"""

import asyncio
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp
from loguru import logger

from .kalshi_client import KalshiClient
from .polymarket_client import PolymarketClient
from .prediction_accuracy import PredictionAccuracyTracker
from .prediction_signal import (
    ArbitrageOpportunity,
    PredictionMarketFeed,
    PredictionSignal,
    PredictionSource,
    SignalRelevance,
)

# ── Fuzzy Market Name Matching ──────────────────────────────────────
# Ported from TheOddsDesk arbitrageService.ts normalizeName().
# Strips noise words and non-alphanumeric chars so "Will Bitcoin exceed $100K
# by end of 2026?" and "Bitcoin above 100000 by year end 2026" map to the same key.

_NOISE_WORDS = re.compile(
    r"\b(will|the|be|at|by|to|end|of|month|year|before|after|"
    r"above|below|exceed|reach|hit|price|go|than|more|less|over|under|"
    r"on|in|for|or|and|a|an|is|are|has|have|this|that|its|it)\b",
    re.IGNORECASE,
)

_NON_ALNUM = re.compile(r"[^a-z0-9]")


def _normalize_market_name(name: str) -> str:
    """Normalize a market question for cross-venue matching.

    Strips noise words, punctuation, and whitespace so identical events
    phrased differently on Polymarket vs Kalshi produce the same key.
    """
    text = name.lower()
    text = _NOISE_WORDS.sub("", text)
    text = _NON_ALNUM.sub("", text)
    return text.strip()


class PredictionAggregator:
    """
    Aggregates prediction market signals across platforms.

    Integration points:
      - AlphaSignalScanner: call `get_cognition_context(symbol)` in scan cycle
      - Forum: call `generate_forum_summary()` periodically
      - Telegram: call `get_status()`, `get_signals_for_symbol()`
    """

    def __init__(self):
        self._enabled = str(
            os.getenv("SAPPHIRE_PREDICTION_MARKET_ENABLED", "false")
        ).strip().lower() in {"1", "true", "yes", "on"}

        poly_interval = max(30.0, float(os.getenv("SAPPHIRE_PM_POLYMARKET_INTERVAL", "60")))
        kalshi_interval = max(30.0, float(os.getenv("SAPPHIRE_PM_KALSHI_INTERVAL", "90")))
        poly_min_volume = max(0.0, float(os.getenv("SAPPHIRE_PM_POLYMARKET_MIN_VOLUME", "10000")))
        kalshi_min_volume = max(0, int(os.getenv("SAPPHIRE_PM_KALSHI_MIN_VOLUME", "100")))

        self._polymarket = PolymarketClient(
            poll_interval=poly_interval,
            min_volume_usd=poly_min_volume,
        )
        self._kalshi = KalshiClient(
            poll_interval=kalshi_interval,
            min_volume=kalshi_min_volume,
        )
        self._feeds: List[PredictionMarketFeed] = [self._polymarket, self._kalshi]
        self._session: Optional[aiohttp.ClientSession] = None
        self._feed_tasks: List[asyncio.Task] = []
        self._last_forum_post_ts = 0.0
        self._forum_post_interval = max(
            300, int(os.getenv("SAPPHIRE_PM_FORUM_INTERVAL", "3600"))
        )
        self._accuracy_tracker = PredictionAccuracyTracker(max_snapshots=500)

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def start(self) -> None:
        """Start all prediction market feeds."""
        if not self._enabled:
            logger.info("🔮 Prediction market feeds disabled (SAPPHIRE_PREDICTION_MARKET_ENABLED)")
            return

        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30, connect=5, sock_read=20),
            headers={"User-Agent": "Sapphire/1.0"},
        )

        for feed in self._feeds:
            task = asyncio.create_task(
                feed.start(self._session),
                name=f"pm_feed_{feed.source.value}",
            )
            self._feed_tasks.append(task)

        logger.info(f"🔮 Prediction aggregator started ({len(self._feeds)} feeds)")

    async def stop(self) -> None:
        """Stop all feeds and close session."""
        for feed in self._feeds:
            await feed.stop()
        for task in self._feed_tasks:
            task.cancel()
        self._feed_tasks.clear()
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("🔮 Prediction aggregator stopped")

    # ── Signal Access ────────────────────────────────────────────

    def get_all_signals(
        self, min_volume: float = 0.0, relevance: Optional[SignalRelevance] = None
    ) -> List[PredictionSignal]:
        """Get all current signals across all feeds."""
        signals: List[PredictionSignal] = []
        for feed in self._feeds:
            signals.extend(feed.get_signals(min_volume=min_volume))
        if relevance:
            signals = [s for s in signals if s.relevance == relevance]
        return sorted(signals, key=lambda s: s.volume_usd, reverse=True)

    def get_signals_for_symbol(self, symbol: str) -> List[PredictionSignal]:
        """Get all signals relevant to a specific crypto symbol."""
        symbol_upper = symbol.strip().upper()
        results = []
        for feed in self._feeds:
            for sig in feed.get_signals():
                if symbol_upper in sig.symbols:
                    results.append(sig)
        return sorted(results, key=lambda s: s.volume_usd, reverse=True)

    def get_high_conviction_signals(self) -> List[PredictionSignal]:
        """Get signals with strong probability skew and high volume."""
        return [s for s in self.get_all_signals() if s.is_high_conviction]

    # ── Consensus Detection ──────────────────────────────────────

    def get_symbol_sentiment(self, symbol: str) -> Dict[str, Any]:
        """
        Aggregate sentiment for a symbol across all prediction markets.

        Returns weighted sentiment based on volume and number of signals.
        """
        signals = self.get_signals_for_symbol(symbol)
        if not signals:
            return {
                "symbol": symbol,
                "sentiment": "neutral",
                "confidence": 0.0,
                "signal_count": 0,
                "sources": [],
            }

        # Volume-weighted probability
        total_volume = sum(s.volume_usd for s in signals)
        if total_volume == 0:
            weighted_prob = sum(s.probability for s in signals) / len(signals)
        else:
            weighted_prob = sum(
                s.probability * s.volume_usd for s in signals
            ) / total_volume

        # Determine consensus sentiment
        if weighted_prob >= 0.75:
            sentiment = "strongly_bullish"
        elif weighted_prob >= 0.60:
            sentiment = "bullish"
        elif weighted_prob <= 0.25:
            sentiment = "strongly_bearish"
        elif weighted_prob <= 0.40:
            sentiment = "bearish"
        else:
            sentiment = "neutral"

        # Confidence based on agreement and volume
        agreement = 1.0 - (
            max(s.probability for s in signals) - min(s.probability for s in signals)
        ) if len(signals) > 1 else 0.5
        volume_factor = min(1.0, total_volume / 1_000_000)
        confidence = round((agreement * 0.6 + volume_factor * 0.4), 3)

        sources = list({s.source.value for s in signals})

        return {
            "symbol": symbol,
            "sentiment": sentiment,
            "weighted_probability": round(weighted_prob, 4),
            "confidence": confidence,
            "signal_count": len(signals),
            "total_volume_usd": round(total_volume, 2),
            "sources": sources,
        }

    # ── Arbitrage Detection ──────────────────────────────────────

    def find_arbitrage_opportunities(
        self,
        min_spread: float = 0.02,
        min_confidence: float = 30.0,
    ) -> List[ArbitrageOpportunity]:
        """Detect cross-venue price discrepancies between prediction markets.

        Ported from TheOddsDesk arbitrageService.ts — groups markets by
        normalized name, then compares probabilities across venues.

        Args:
            min_spread: Minimum probability spread to flag (default 2%).
            min_confidence: Minimum confidence score (0-100) to include.

        Returns:
            List of ArbitrageOpportunity sorted by spread descending.
        """
        all_signals = self.get_all_signals()
        if not all_signals:
            return []

        # Group signals by normalized question
        groups: Dict[str, List[PredictionSignal]] = defaultdict(list)
        for sig in all_signals:
            key = _normalize_market_name(sig.question)
            if key:  # Skip empty keys
                groups[key].append(sig)

        opportunities: List[ArbitrageOpportunity] = []

        for name_key, signals in groups.items():
            if len(signals) < 2:
                continue

            # Compare all pairs from different venues
            for i in range(len(signals)):
                for j in range(i + 1, len(signals)):
                    sig_a = signals[i]
                    sig_b = signals[j]

                    # Only flag cross-venue discrepancies
                    if sig_a.source == sig_b.source:
                        continue

                    spread = abs(sig_a.probability - sig_b.probability)
                    if spread < min_spread:
                        continue

                    confidence = self._calculate_arb_confidence(sig_a, sig_b)
                    if confidence < min_confidence:
                        continue

                    # Merge symbols from both signals
                    merged_symbols = list(set(sig_a.symbols + sig_b.symbols))

                    opp = ArbitrageOpportunity(
                        id=f"arb-{sig_a.market_id}-{sig_b.market_id}",
                        market_name=sig_a.question,
                        venue_a=sig_a.source.value,
                        price_a=sig_a.probability,
                        signal_a=sig_a,
                        venue_b=sig_b.source.value,
                        price_b=sig_b.probability,
                        signal_b=sig_b,
                        spread=spread,
                        spread_pct=round(spread * 100, 2),
                        confidence=confidence,
                        symbols=merged_symbols,
                    )
                    opportunities.append(opp)

        return sorted(opportunities, key=lambda o: o.spread, reverse=True)

    @staticmethod
    def _calculate_arb_confidence(sig_a: PredictionSignal, sig_b: PredictionSignal) -> float:
        """Calculate confidence score for an arbitrage opportunity.

        Mirrors TheOddsDesk confidence logic:
        - Higher volume on both sides → higher confidence
        - Penalize stale or synthetic data
        """
        total_vol = sig_a.volume_usd + sig_b.volume_usd

        # Base confidence from combined volume
        if total_vol > 1_000_000:
            base = 90.0
        elif total_vol > 500_000:
            base = 80.0
        elif total_vol > 100_000:
            base = 70.0
        elif total_vol > 25_000:
            base = 55.0
        else:
            base = 40.0

        # Bonus for having volume on BOTH sides (not just one)
        min_vol = min(sig_a.volume_usd, sig_b.volume_usd)
        if min_vol > 50_000:
            base += 5.0
        elif min_vol < 5_000:
            base -= 10.0

        # Bonus for liquidity
        total_liq = sig_a.liquidity_usd + sig_b.liquidity_usd
        if total_liq > 100_000:
            base += 5.0

        return max(0.0, min(100.0, base))

    def get_arbitrage_context(self) -> str:
        """Generate arbitrage context for cognition prompts."""
        if not self._enabled:
            return ""

        opps = self.find_arbitrage_opportunities()
        if not opps:
            return ""

        lines = [f"Cross-Venue Arbitrage ({len(opps)} opportunities):"]
        for opp in opps[:3]:
            lines.append(f"  {opp.context_string()}")
        return "\n".join(lines)

    def format_telegram_arbitrage(self, limit: int = 8) -> str:
        """Format arbitrage opportunities for Telegram display."""
        if not self._enabled:
            return "🔮 Prediction markets: disabled"

        opps = self.find_arbitrage_opportunities()
        if not opps:
            return "⚡ **Cross-Venue Arbitrage**\n\nNo arbitrage opportunities detected."

        lines = [f"⚡ **Cross-Venue Arbitrage** ({len(opps)} found)\n"]
        for opp in opps[:limit]:
            conf_icon = "🟢" if opp.confidence >= 70 else "🟡" if opp.confidence >= 50 else "🔴"
            lines.append(
                f"{conf_icon} {opp.market_name[:55]}\n"
                f"  {opp.venue_a}: {opp.price_a:.1%} vs {opp.venue_b}: {opp.price_b:.1%}\n"
                f"  Spread: **{opp.spread_pct:.1f}%** | Conf: {opp.confidence:.0f}"
            )

        return "\n".join(lines)

    # ── Cognition Context ────────────────────────────────────────

    def get_cognition_context(self, symbol: str) -> str:
        """
        Generate a compact context string for DualSpeedCognition prompts.

        This is injected into the AlphaScanner's market context before
        sending to Gemini for trade decisions.
        """
        if not self._enabled:
            return ""

        signals = self.get_signals_for_symbol(symbol)
        if not signals:
            return ""

        lines = [f"Prediction Markets ({len(signals)} signals for {symbol}):"]
        for sig in signals[:5]:  # Top 5 by volume
            lines.append(f"  {sig.context_string()}")

        sentiment = self.get_symbol_sentiment(symbol)
        lines.append(
            f"  Consensus: {sentiment['sentiment']} "
            f"(prob={sentiment['weighted_probability']:.1%}, "
            f"conf={sentiment['confidence']:.2f}, "
            f"vol=${sentiment['total_volume_usd']:,.0f})"
        )

        # Append arbitrage alerts for this symbol
        arbs = self.find_arbitrage_opportunities()
        symbol_arbs = [a for a in arbs if symbol in a.symbols]
        if symbol_arbs:
            lines.append(f"  Arbitrage ({len(symbol_arbs)} cross-venue spreads):")
            for arb in symbol_arbs[:3]:
                lines.append(f"    {arb.context_string()}")

        # Whale activity & manipulation warnings for this symbol
        whale_alerts = self._detect_whale_and_manipulation(symbol)
        if whale_alerts:
            lines.append(f"  ⚠️ Market Intelligence Alerts:")
            for alert in whale_alerts[:5]:
                lines.append(f"    {alert}")

        return "\n".join(lines)

    def get_macro_context(self) -> str:
        """
        Generate macro event context from prediction markets.

        Covers Fed rates, CPI, GDP, etc. — useful for all trading decisions.
        """
        if not self._enabled:
            return ""

        macro = self.get_all_signals(relevance=SignalRelevance.MACRO)
        if not macro:
            return ""

        lines = ["Macro Prediction Markets:"]
        for sig in macro[:5]:
            lines.append(f"  {sig.context_string()}")
        return "\n".join(lines)

    # ── Whale & Manipulation Detection ──────────────────────────

    def _detect_whale_and_manipulation(self, symbol: str = "") -> List[str]:
        """Detect whale activity and manipulation patterns in prediction markets.

        Returns human-readable alert strings for cognition context.
        """
        alerts: List[str] = []
        signals = self.get_signals_for_symbol(symbol) if symbol else self.get_all_signals()

        for sig in signals:
            if sig.is_whale_activity:
                vc = sig.volume_change
                m = sig.momentum
                vc_str = f"{vc:.1f}x" if vc is not None else "?"
                m_str = f"{m:+.1%}" if m is not None else "?"
                alerts.append(
                    f"🐋 WHALE [{sig.source.value}] {sig.question[:50]}: "
                    f"vol {vc_str} spike, prob {m_str} shift"
                )

            risk = sig.manipulation_risk
            if risk == "wash_trading":
                alerts.append(
                    f"⚠️ WASH TRADE [{sig.source.value}] {sig.question[:50]}: "
                    f"volume spike with no price movement — possible fake liquidity"
                )
            elif risk == "low_liquidity_pump":
                ratio = sig.volume_usd / sig.liquidity_usd if sig.liquidity_usd > 0 else 0
                alerts.append(
                    f"⚠️ LOW LIQ [{sig.source.value}] {sig.question[:50]}: "
                    f"vol/liq ratio {ratio:.0f}x — easily manipulated"
                )
            elif risk == "insider_pattern":
                m = sig.momentum
                m_str = f"{m:+.1%}" if m is not None else "?"
                alerts.append(
                    f"⚠️ INSIDER [{sig.source.value}] {sig.question[:50]}: "
                    f"{m_str} prob jump without volume catalyst"
                )

            if sig.is_volume_spike and not sig.is_whale_activity:
                vc = sig.volume_change
                alerts.append(
                    f"📈 VOL SPIKE [{sig.source.value}] {sig.question[:50]}: "
                    f"{vc:.1f}x volume increase"
                )

        return alerts

    def format_telegram_whale_alerts(self, limit: int = 10) -> str:
        """Format whale activity and manipulation alerts for Telegram."""
        if not self._enabled:
            return "🔮 Prediction markets: disabled"

        alerts = self._detect_whale_and_manipulation()
        if not alerts:
            return "🐋 **Whale & Manipulation Monitor**\n\nNo suspicious activity detected."

        lines = [f"🐋 **Whale & Manipulation Monitor** ({len(alerts)} alerts)\n"]
        for alert in alerts[:limit]:
            lines.append(alert)

        return "\n".join(lines)

    # ── Forum Summaries ──────────────────────────────────────────

    def generate_forum_summary(self) -> Optional[Dict[str, Any]]:
        """
        Generate a forum post summary of current prediction market state.

        Returns None if not enough time has elapsed since last post,
        or if there are no meaningful signals.
        """
        now = time.time()
        if (now - self._last_forum_post_ts) < self._forum_post_interval:
            return None

        signals = self.get_all_signals(min_volume=25_000)
        if not signals:
            return None

        high_conviction = [s for s in signals if s.is_high_conviction]

        # Build summary body
        lines = ["🔮 **Prediction Market Intelligence Update**\n"]
        lines.append(f"Sources: {', '.join({s.source.value for s in signals})}")
        lines.append(f"Markets tracked: {len(signals)}")
        lines.append(f"High-conviction signals: {len(high_conviction)}\n")

        if high_conviction:
            lines.append("**High-Conviction Signals:**")
            for sig in high_conviction[:8]:
                momentum_str = ""
                if sig.momentum is not None:
                    arrow = "↑" if sig.momentum > 0 else "↓" if sig.momentum < 0 else "→"
                    momentum_str = f" {arrow}{abs(sig.momentum):.1%}"
                lines.append(
                    f"- [{sig.source.value}] {sig.question}: "
                    f"**{sig.probability:.1%}**{momentum_str} "
                    f"(${sig.volume_usd:,.0f} vol)"
                )

        # Arbitrage opportunities
        arbs = self.find_arbitrage_opportunities()
        if arbs:
            lines.append(f"\n**Cross-Venue Arbitrage ({len(arbs)} found):**")
            for arb in arbs[:5]:
                lines.append(
                    f"- {arb.market_name[:60]}: "
                    f"{arb.venue_a}={arb.price_a:.1%} vs {arb.venue_b}={arb.price_b:.1%} "
                    f"(spread={arb.spread_pct:.1f}%, conf={arb.confidence:.0f})"
                )

        # Whale & Manipulation alerts
        whale_alerts = self._detect_whale_and_manipulation()
        if whale_alerts:
            lines.append(f"\n**⚠️ Market Intelligence ({len(whale_alerts)} alerts):**")
            for alert in whale_alerts[:5]:
                lines.append(f"- {alert}")

        # Symbol-level sentiment
        seen_symbols = set()
        for sig in signals:
            seen_symbols.update(sig.symbols)

        if seen_symbols:
            lines.append("\n**Symbol Sentiment:**")
            for sym in sorted(seen_symbols):
                sent = self.get_symbol_sentiment(sym)
                if sent["signal_count"] > 0:
                    lines.append(
                        f"- {sym}: {sent['sentiment']} "
                        f"(prob={sent['weighted_probability']:.1%}, "
                        f"{sent['signal_count']} signals)"
                    )

        self._last_forum_post_ts = now

        return {
            "lane": "trading",
            "category": "market_analysis",
            "title": f"Prediction Market Update — {datetime.now(timezone.utc).strftime('%b %d %H:%M UTC')}",
            "body": "\n".join(lines),
            "author": "SCOUT",
            "tags": ["prediction-market", "automated-insight"],
            "priority": "high" if high_conviction else "medium",
        }

    # ── Status & Monitoring ──────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Get aggregator status for Telegram /predictions status command."""
        feed_statuses = {feed.source.value: feed.get_status() for feed in self._feeds}
        total_signals = sum(s["market_count"] for s in feed_statuses.values())
        high_conviction = len(self.get_high_conviction_signals())
        arb_count = len(self.find_arbitrage_opportunities())

        accuracy = self._accuracy_tracker.get_accuracy_stats()

        return {
            "enabled": self._enabled,
            "feeds": feed_statuses,
            "total_signals": total_signals,
            "high_conviction_signals": high_conviction,
            "arbitrage_opportunities": arb_count,
            "accuracy_tracked": accuracy["total_tracked"],
            "accuracy_resolved": accuracy["total_resolved"],
            "last_forum_post": self._last_forum_post_ts,
        }

    def format_telegram_status(self) -> str:
        """Format status for Telegram display."""
        if not self._enabled:
            return "🔮 Prediction markets: disabled"

        status = self.get_status()
        lines = ["🔮 **Prediction Market Intelligence**\n"]

        for source, feed_status in status["feeds"].items():
            emoji = "🟢" if feed_status["running"] and feed_status["consecutive_errors"] == 0 else "🟡" if feed_status["running"] else "🔴"
            lines.append(
                f"{emoji} {source}: {feed_status['market_count']} markets"
            )
            if feed_status["consecutive_errors"] > 0:
                lines.append(f"  ⚠️ {feed_status['consecutive_errors']} errors")

        lines.append(f"\nTotal signals: {status['total_signals']}")
        lines.append(f"High conviction: {status['high_conviction_signals']}")
        lines.append(f"Arbitrage opportunities: {status['arbitrage_opportunities']}")
        lines.append(f"Accuracy tracked: {status['accuracy_tracked']} ({status['accuracy_resolved']} resolved)")

        return "\n".join(lines)

    def format_telegram_signals(self, symbol: Optional[str] = None, limit: int = 10) -> str:
        """Format signals for Telegram display."""
        if not self._enabled:
            return "🔮 Prediction markets: disabled"

        if symbol:
            signals = self.get_signals_for_symbol(symbol)
            header = f"🔮 **Prediction Markets — {symbol}**"
        else:
            signals = self.get_high_conviction_signals()
            header = "🔮 **High-Conviction Prediction Signals**"

        if not signals:
            return f"{header}\n\nNo signals found."

        lines = [header, ""]
        for sig in signals[:limit]:
            momentum_str = ""
            if sig.momentum is not None:
                arrow = "↑" if sig.momentum > 0 else "↓" if sig.momentum < 0 else "→"
                momentum_str = f" {arrow}{abs(sig.momentum):.1%}"

            lines.append(
                f"• [{sig.source.value}] {sig.question[:60]}\n"
                f"  Prob: {sig.probability:.1%}{momentum_str} | "
                f"Vol: ${sig.volume_usd:,.0f} | "
                f"{sig.sentiment}"
            )

        if symbol:
            sent = self.get_symbol_sentiment(symbol)
            lines.append(
                f"\n📊 Consensus: {sent['sentiment']} "
                f"(conf={sent['confidence']:.2f})"
            )

        return "\n".join(lines)

    # ── Accuracy Tracking ─────────────────────────────────────────

    @property
    def accuracy_tracker(self) -> PredictionAccuracyTracker:
        return self._accuracy_tracker

    def record_signals_for_accuracy(self) -> int:
        """Snapshot all current signals for accuracy tracking.

        Should be called periodically (e.g., in the poll loop).
        Returns the number of new signals recorded.
        """
        recorded = 0
        for signal in self.get_all_signals():
            # Only record if not already tracked
            if signal.market_id not in self._accuracy_tracker._snapshots:
                self._accuracy_tracker.record_signal(signal)
                recorded += 1
        return recorded

    def format_telegram_accuracy(self) -> str:
        """Format prediction accuracy stats for Telegram display."""
        return self._accuracy_tracker.format_telegram_accuracy()

    def get_prediction_dashboard_data(self) -> Dict[str, Any]:
        """Get full prediction market data for the dashboard API.

        Combines status, signals, arbitrage, accuracy, and sentiment.
        """
        status = self.get_status()
        accuracy = self._accuracy_tracker.get_accuracy_stats()

        # Top signals by volume
        top_signals = [s.to_dict() for s in self.get_all_signals(min_volume=10_000)[:15]]

        # High conviction signals
        hc_signals = [s.to_dict() for s in self.get_high_conviction_signals()[:10]]

        # Arbitrage opportunities
        arb_opps = [o.to_dict() for o in self.find_arbitrage_opportunities()[:10]]

        # Symbol sentiments
        symbols_seen: set[str] = set()
        for s in self.get_all_signals():
            symbols_seen.update(s.symbols)
        sentiments = {}
        for sym in sorted(symbols_seen):
            sentiments[sym] = self.get_symbol_sentiment(sym)

        # Whale & manipulation alerts
        whale_alerts = self._detect_whale_and_manipulation()

        return {
            "status": status,
            "accuracy": accuracy,
            "signals": top_signals,
            "high_conviction": hc_signals,
            "arbitrage": arb_opps,
            "sentiments": sentiments,
            "whale_alerts": whale_alerts[:20],
            "pending_accuracy": self._accuracy_tracker.get_pending_markets()[:20],
        }
