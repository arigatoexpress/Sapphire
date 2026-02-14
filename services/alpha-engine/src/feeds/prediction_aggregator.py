"""
Prediction Market Signal Aggregator

Combines signals from Polymarket, Kalshi, and future sources into a unified
prediction intelligence layer. Provides:
  - Cross-source consensus detection
  - Symbol-level sentiment aggregation
  - Cognition context generation for DualSpeedCognition prompts
  - Forum summary generation for Scout posts
"""

import asyncio
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp
from loguru import logger

from .kalshi_client import KalshiClient
from .polymarket_client import PolymarketClient
from .prediction_signal import (
    PredictionMarketFeed,
    PredictionSignal,
    PredictionSource,
    SignalRelevance,
)


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

        return {
            "enabled": self._enabled,
            "feeds": feed_statuses,
            "total_signals": total_signals,
            "high_conviction_signals": high_conviction,
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
