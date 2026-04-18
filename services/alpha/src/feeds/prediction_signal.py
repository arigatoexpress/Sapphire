"""
Prediction Market Signal Dataclass & Base Feed

Core data structures for prediction market intelligence:
- PredictionSignal: normalized signal from any prediction platform
- PredictionMarketFeed: async base class for platform-specific feeds
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore[assignment]
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from loguru import logger


class PredictionSource(StrEnum):
    POLYMARKET = "polymarket"
    KALSHI = "kalshi"


class SignalRelevance(StrEnum):
    """How relevant a prediction market is to crypto trading."""
    DIRECT = "direct"        # Directly about crypto prices (e.g., "BTC > $100K")
    MACRO = "macro"          # Macro events affecting crypto (Fed, CPI, jobs)
    REGULATORY = "regulatory"  # Crypto regulation events
    INDIRECT = "indirect"    # Loosely correlated events


@dataclass
class PredictionSignal:
    """Normalized prediction market signal from any platform."""

    market_id: str
    source: PredictionSource
    question: str
    probability: float           # 0.0 - 1.0
    volume_usd: float            # Total traded volume in USD
    liquidity_usd: float         # Current available liquidity
    relevance: SignalRelevance
    symbols: list[str]           # Crypto symbols this market affects
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Optional enrichment
    probability_1h_ago: float | None = None
    probability_24h_ago: float | None = None
    volume_1h_ago: float | None = None
    end_date: datetime | None = None
    category: str = ""
    tags: list[str] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)

    @property
    def momentum(self) -> float | None:
        """Probability change over last hour (-1.0 to 1.0)."""
        if self.probability_1h_ago is not None:
            return self.probability - self.probability_1h_ago
        return None

    @property
    def sentiment(self) -> str:
        """Map probability to sentiment for cognition context."""
        if self.probability >= 0.75:
            return "strongly_bullish"
        if self.probability >= 0.60:
            return "bullish"
        if self.probability <= 0.25:
            return "strongly_bearish"
        if self.probability <= 0.40:
            return "bearish"
        return "neutral"

    @property
    def volume_change(self) -> float | None:
        """Volume change over last hour (ratio). >2.0 = doubled."""
        if self.volume_1h_ago is not None and self.volume_1h_ago > 0:
            return self.volume_usd / self.volume_1h_ago
        return None

    @property
    def is_volume_spike(self) -> bool:
        """Detect unusual volume spike (>3x in 1 hour)."""
        vc = self.volume_change
        return vc is not None and vc >= 3.0

    @property
    def is_whale_activity(self) -> bool:
        """Detect whale-like behavior: large volume spike with significant price move.

        Pattern: >2x volume AND >5% probability shift in same hour = likely large player.
        """
        vc = self.volume_change
        m = self.momentum
        if vc is None or m is None:
            return False
        return vc >= 2.0 and abs(m) >= 0.05

    @property
    def manipulation_risk(self) -> str:
        """Assess manipulation risk level based on observable patterns.

        Flags:
        - wash_trading: Volume spike with no price movement (inflated liquidity)
        - insider_pattern: Large probability jump before any public catalyst
        - low_liquidity_pump: High volume relative to liquidity (easy to manipulate)
        - clean: No red flags detected
        """
        vc = self.volume_change
        m = self.momentum

        # Wash trading: big volume spike but price didn't move
        if vc is not None and vc >= 3.0 and (m is None or abs(m) < 0.01):
            return "wash_trading"

        # Low liquidity pump: volume >> liquidity (easy to push price)
        if self.liquidity_usd > 0 and self.volume_usd > self.liquidity_usd * 10:
            return "low_liquidity_pump"

        # Insider pattern: large sudden probability jump with moderate volume
        if m is not None and abs(m) >= 0.15 and (vc is None or vc < 2.0):
            return "insider_pattern"

        return "clean"

    @property
    def is_high_conviction(self) -> bool:
        """Signal has enough volume and probability skew to be actionable."""
        return self.volume_usd >= 50_000 and (
            self.probability >= 0.70 or self.probability <= 0.30
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id,
            "source": self.source.value,
            "question": self.question,
            "probability": round(self.probability, 4),
            "volume_usd": round(self.volume_usd, 2),
            "liquidity_usd": round(self.liquidity_usd, 2),
            "relevance": self.relevance.value,
            "symbols": self.symbols,
            "sentiment": self.sentiment,
            "momentum": round(self.momentum, 4) if self.momentum is not None else None,
            "volume_change": round(self.volume_change, 2) if self.volume_change is not None else None,
            "is_high_conviction": self.is_high_conviction,
            "is_volume_spike": self.is_volume_spike,
            "is_whale_activity": self.is_whale_activity,
            "manipulation_risk": self.manipulation_risk,
            "timestamp": self.timestamp.isoformat(),
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "category": self.category,
            "tags": self.tags,
        }

    def context_string(self) -> str:
        """Compact string for LLM cognition prompts."""
        momentum_str = ""
        if self.momentum is not None:
            direction = "↑" if self.momentum > 0 else "↓" if self.momentum < 0 else "→"
            momentum_str = f" ({direction}{abs(self.momentum):.1%} 1h)"
        flags = []
        if self.is_whale_activity:
            flags.append("🐋WHALE")
        if self.is_volume_spike:
            flags.append("📈SPIKE")
        risk = self.manipulation_risk
        if risk != "clean":
            flags.append(f"⚠️{risk.upper()}")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        return (
            f"[{self.source.value}] {self.question}: "
            f"{self.probability:.1%}{momentum_str} "
            f"(vol=${self.volume_usd:,.0f}, {self.sentiment}){flag_str}"
        )


@dataclass
class ArbitrageOpportunity:
    """Cross-venue price discrepancy detected between prediction markets.

    Inspired by TheOddsDesk arbitrage detection — fuzzy-matches market
    questions across Polymarket and Kalshi, flags spreads above threshold.
    """

    id: str
    market_name: str          # Normalized question/title
    venue_a: str              # Source A (e.g., "polymarket")
    price_a: float            # Probability on venue A (0.0-1.0)
    signal_a: PredictionSignal
    venue_b: str              # Source B (e.g., "kalshi")
    price_b: float            # Probability on venue B (0.0-1.0)
    signal_b: PredictionSignal
    spread: float             # Absolute difference (0.0-1.0)
    spread_pct: float         # Spread as percentage (e.g., 5.2)
    confidence: float         # 0-100, based on volume and data freshness
    symbols: list[str]        # Affected crypto symbols
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def direction(self) -> str:
        """Which venue is higher — useful for cognition context."""
        if self.price_a > self.price_b:
            return f"{self.venue_a} > {self.venue_b}"
        return f"{self.venue_b} > {self.venue_a}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "market_name": self.market_name,
            "venue_a": self.venue_a,
            "price_a": round(self.price_a, 4),
            "venue_b": self.venue_b,
            "price_b": round(self.price_b, 4),
            "spread": round(self.spread, 4),
            "spread_pct": round(self.spread_pct, 2),
            "confidence": round(self.confidence, 1),
            "direction": self.direction,
            "symbols": self.symbols,
            "timestamp": self.timestamp.isoformat(),
        }

    def context_string(self) -> str:
        """Compact string for LLM cognition prompts."""
        return (
            f"[ARB] {self.market_name[:60]}: "
            f"{self.venue_a}={self.price_a:.1%} vs {self.venue_b}={self.price_b:.1%} "
            f"(spread={self.spread_pct:.1f}%, conf={self.confidence:.0f})"
        )


class PredictionMarketFeed(ABC):
    """Base class for prediction market data feeds."""

    def __init__(self, source: PredictionSource, poll_interval: float = 60.0):
        self.source = source
        self.poll_interval = max(10.0, poll_interval)
        self.running = False
        self._signals: dict[str, PredictionSignal] = {}
        self._history: dict[str, list[float]] = {}  # market_id → [prob_t-1, prob_t-2, ...]
        self._volume_history: dict[str, list[float]] = {}  # market_id → [vol_t-1, vol_t-2, ...]
        self._last_fetch_ts = 0.0
        self._consecutive_errors = 0
        self._max_consecutive_errors = 10
        self._last_error_msg = ""
        self._last_error_ts = 0.0

    @abstractmethod
    async def _fetch_markets(self, session: aiohttp.ClientSession) -> list[PredictionSignal]:
        """Fetch current prediction market data. Implement per platform."""
        ...

    async def start(self, session: aiohttp.ClientSession) -> None:
        """Start the polling loop."""
        self.running = True
        logger.info(f"🔮 {self.source.value} prediction feed starting (interval={self.poll_interval}s)")
        while self.running:
            try:
                signals = await self._fetch_markets(session)
                for sig in signals:
                    self._update_history(sig)
                    self._signals[sig.market_id] = sig
                self._consecutive_errors = 0
                self._last_fetch_ts = time.time()
                logger.debug(
                    f"🔮 {self.source.value}: fetched {len(signals)} markets"
                )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._consecutive_errors += 1
                self._log_error(f"{self.source.value} feed error: {exc}")
                if self._consecutive_errors >= self._max_consecutive_errors:
                    logger.error(
                        f"🔮 {self.source.value}: {self._max_consecutive_errors} consecutive errors, "
                        f"backing off to 5x interval"
                    )
            # Backoff on repeated errors
            interval = self.poll_interval
            if self._consecutive_errors >= self._max_consecutive_errors:
                interval = self.poll_interval * 5
            elif self._consecutive_errors >= 3:
                interval = self.poll_interval * 2
            await asyncio.sleep(interval)

    async def stop(self) -> None:
        self.running = False
        logger.info(f"🔮 {self.source.value} prediction feed stopped")

    def get_signals(self, min_volume: float = 0.0) -> list[PredictionSignal]:
        """Get all current signals, optionally filtered by volume."""
        signals = list(self._signals.values())
        if min_volume > 0:
            signals = [s for s in signals if s.volume_usd >= min_volume]
        return sorted(signals, key=lambda s: s.volume_usd, reverse=True)

    def get_signal(self, market_id: str) -> PredictionSignal | None:
        return self._signals.get(market_id)

    def get_status(self) -> dict[str, Any]:
        return {
            "source": self.source.value,
            "running": self.running,
            "market_count": len(self._signals),
            "last_fetch": self._last_fetch_ts,
            "consecutive_errors": self._consecutive_errors,
            "last_error": self._last_error_msg,
        }

    def _update_history(self, signal: PredictionSignal) -> None:
        """Track probability and volume history for momentum + whale detection."""
        # Probability history
        history = self._history.setdefault(signal.market_id, [])
        history.append(signal.probability)
        if len(history) > 120:
            history[:] = history[-120:]
        if len(history) >= 60:
            signal.probability_1h_ago = history[-60]

        # Volume history — track for spike / whale detection
        vol_history = self._volume_history.setdefault(signal.market_id, [])
        vol_history.append(signal.volume_usd)
        if len(vol_history) > 120:
            vol_history[:] = vol_history[-120:]
        if len(vol_history) >= 60:
            signal.volume_1h_ago = vol_history[-60]

    def _log_error(self, message: str) -> None:
        """Deduplicated error logging."""
        now = time.time()
        if message != self._last_error_msg or (now - self._last_error_ts) >= 60:
            logger.warning(f"⚠️ {message}")
            self._last_error_msg = message
            self._last_error_ts = now
