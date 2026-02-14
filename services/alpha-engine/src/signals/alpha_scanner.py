"""
Internal Alpha Signal Scanner — Autonomous Trade Idea Generation

This module gives the Sapphire agents their own "eyes" on the market.
Instead of passively waiting for TradingView webhooks, the scanner
periodically evaluates market conditions using the Dual-Speed Cognition
system and generates internal trade signals.

Flow:
  1. Collect real-time market snapshots (prices, tick history, volume proxy)
  2. Build a structured market context prompt
  3. Run through Dual-Speed Cognition (System 1 fast + System 2 deep)
  4. If cognition says BUY/SELL with sufficient confidence → emit signal
  5. Signal enters the same execution pipeline as TradingView webhooks

The scanner respects:
  - Kill switch state
  - Execution stage multiplier (paper/staged_live/full_live)
  - Venue allocation & pause state
  - Cognition override thresholds
  - Rate limiting to avoid signal spam
"""

import asyncio
import logging
import os
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class AlphaSignalScanner:
    """Periodically scans market data and generates internal trade signals."""

    # Minimum confidence from cognition to emit a signal
    MIN_SIGNAL_CONFIDENCE = 0.72

    # Cooldown between signals for the same symbol (seconds)
    SYMBOL_COOLDOWN_SECONDS = 600  # 10 min

    # Maximum open signals (prevent runaway)
    MAX_PENDING_SIGNALS = 5

    def __init__(
        self,
        market_data: Any,
        cognition: Any,
        memory: Any,
        strategy: Any,
        *,
        prediction_aggregator: Any = None,
        scan_interval_seconds: int = 0,
        enabled: bool = False,
        scan_symbols: Optional[List[str]] = None,
    ):
        self.market_data = market_data
        self.cognition = cognition
        self.memory = memory
        self.strategy = strategy
        self.prediction_aggregator = prediction_aggregator

        self._enabled = enabled or _env_flag(
            "SAPPHIRE_ALPHA_SCANNER_ENABLED", default=False
        )
        self._scan_interval = max(
            60,
            scan_interval_seconds
            or int(os.getenv("SAPPHIRE_ALPHA_SCAN_INTERVAL_SECONDS", "300")),
        )
        self._scan_symbols = scan_symbols or _parse_symbols(
            os.getenv(
                "SAPPHIRE_ALPHA_SCAN_SYMBOLS",
                os.getenv("SAPPHIRE_PREFERRED_SYMBOLS", "BTC,ETH,SOL"),
            )
        )
        self._min_confidence = max(
            0.5,
            min(
                0.95,
                float(os.getenv("SAPPHIRE_ALPHA_MIN_CONFIDENCE", str(self.MIN_SIGNAL_CONFIDENCE))),
            ),
        )
        self._max_pending = max(
            1,
            int(os.getenv("SAPPHIRE_ALPHA_MAX_PENDING_SIGNALS", str(self.MAX_PENDING_SIGNALS))),
        )
        self._symbol_cooldown = max(
            60,
            int(os.getenv("SAPPHIRE_ALPHA_SYMBOL_COOLDOWN_SECONDS", str(self.SYMBOL_COOLDOWN_SECONDS))),
        )

        # State
        self._last_signal_at: Dict[str, float] = {}
        self._pending_count = 0
        self._total_scans = 0
        self._total_signals_emitted = 0
        self._signal_history: Deque[Dict[str, Any]] = deque(maxlen=100)
        self._running = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def get_metrics(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "scan_interval_seconds": self._scan_interval,
            "scan_symbols": list(self._scan_symbols),
            "min_confidence": self._min_confidence,
            "total_scans": self._total_scans,
            "total_signals_emitted": self._total_signals_emitted,
            "pending_count": self._pending_count,
            "recent_signals": list(self._signal_history)[-5:],
        }

    async def run_loop(self, signal_callback) -> None:
        """Main scan loop — call this as an asyncio task.

        Args:
            signal_callback: async fn(signal_dict) that feeds into the
                             TradingView signal handler pipeline.
        """
        if not self._enabled:
            logger.info("Alpha scanner disabled (SAPPHIRE_ALPHA_SCANNER_ENABLED=false)")
            return

        self._running = True
        logger.info(
            f"🔍 Alpha scanner starting — interval={self._scan_interval}s, "
            f"symbols={','.join(self._scan_symbols[:6])}, "
            f"min_confidence={self._min_confidence}"
        )

        while self._running:
            try:
                await asyncio.sleep(self._scan_interval)
                signals = await self._scan_cycle()
                for sig in signals:
                    try:
                        await signal_callback(sig)
                        self._total_signals_emitted += 1
                    except Exception as exc:
                        logger.warning(f"Signal callback error: {exc}")
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Alpha scanner cycle error: {exc}")
                await asyncio.sleep(30)  # backoff on error

        logger.info("Alpha scanner stopped")

    def stop(self):
        self._running = False

    async def _scan_cycle(self) -> List[Dict[str, Any]]:
        """Run one full scan cycle across all symbols."""
        self._total_scans += 1
        signals: List[Dict[str, Any]] = []

        if self._pending_count >= self._max_pending:
            logger.debug(f"Alpha scanner: max pending signals ({self._max_pending}), skipping")
            return signals

        snapshot = self.market_data.get_multi_symbol_snapshot()
        execution_state = self.strategy.execution_state()
        stage = execution_state.get("dex_execution_stage", "paper")
        multiplier = float(execution_state.get("stage_multiplier", 0.0))

        if multiplier <= 0:
            logger.debug(f"Alpha scanner: stage={stage} multiplier=0, skipping")
            return signals

        now = time.time()
        for symbol in self._scan_symbols:
            # Cooldown check
            last = self._last_signal_at.get(symbol, 0)
            if now - last < self._symbol_cooldown:
                continue

            # Build market context for this symbol
            context = self._build_market_context(symbol, snapshot)
            if not context:
                continue

            # Run cognition
            signal = await self._evaluate_symbol(symbol, context, execution_state)
            if signal:
                signals.append(signal)
                self._last_signal_at[symbol] = now
                self._pending_count += 1
                self._signal_history.append({
                    "symbol": symbol,
                    "action": signal.get("action", ""),
                    "confidence": signal.get("_confidence", 0),
                    "timestamp": int(now),
                })

        return signals

    def _build_market_context(
        self, symbol: str, snapshot: Dict[str, Dict[str, Dict[str, Any]]]
    ) -> Optional[Dict[str, Any]]:
        """Build a market context dict for cognition evaluation."""
        venues_with_price = {}
        for venue in ("ASTER", "LIGHTER"):
            venue_data = snapshot.get(venue, {})
            sym_data = venue_data.get(symbol, {})
            price = sym_data.get("price", 0)
            if price > 0:
                venues_with_price[venue] = {
                    "price": price,
                    "age_seconds": sym_data.get("age_seconds"),
                    "tick_count": sym_data.get("tick_count", 0),
                }

        if not venues_with_price:
            return None

        # Pick best venue (most recent data)
        best_venue = min(
            venues_with_price,
            key=lambda v: venues_with_price[v].get("age_seconds") or 9999,
        )
        best = venues_with_price[best_venue]

        # Get tick history for momentum calculation
        ticks = self.market_data._tick_history.get(best_venue, {}).get(symbol, deque())
        recent_ticks = list(ticks)[-30:]  # last 30 ticks

        momentum_1m = 0.0
        momentum_5m = 0.0
        if len(recent_ticks) >= 2:
            current_price = recent_ticks[-1][1]  # (timestamp, price, volume)
            # 1-min: compare to tick ~1 min ago
            one_min_ago = time.time() - 60
            older = [t for t in recent_ticks if t[0] <= one_min_ago]
            if older:
                momentum_1m = ((current_price - older[-1][1]) / older[-1][1]) * 100

            five_min_ago = time.time() - 300
            older_5 = [t for t in recent_ticks if t[0] <= five_min_ago]
            if older_5:
                momentum_5m = ((current_price - older_5[-1][1]) / older_5[-1][1]) * 100

        return {
            "symbol": symbol,
            "venue": best_venue,
            "price": best["price"],
            "age_seconds": best.get("age_seconds", 0),
            "tick_count": best.get("tick_count", 0),
            "momentum_1m_pct": round(momentum_1m, 4),
            "momentum_5m_pct": round(momentum_5m, 4),
            "venues_available": list(venues_with_price.keys()),
        }

    async def _evaluate_symbol(
        self,
        symbol: str,
        context: Dict[str, Any],
        execution_state: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Evaluate a symbol using Dual-Speed Cognition."""
        from shared.dual_speed_cognition import CognitionRequest, CognitionSpeed

        price = context["price"]
        momentum_1m = context["momentum_1m_pct"]
        momentum_5m = context["momentum_5m_pct"]
        venues = context["venues_available"]

        # Memory recall for past lessons
        memory_advice = ""
        try:
            if self.memory and hasattr(self.memory, "recall_for_decision"):
                from shared.enhanced_episodic_memory import MarketSnapshot

                market_snap = MarketSnapshot(prices={symbol: price})
                memory_advice = (
                    await self.memory.recall_for_decision(
                        symbol=symbol,
                        snapshot=market_snap,
                        context=f"Internal alpha scan: {symbol} @ ${price:.2f}",
                    )
                    or ""
                )
        except Exception:
            pass  # Memory is non-critical

        # Prediction market context
        pm_context = ""
        if self.prediction_aggregator:
            try:
                pm_context = self.prediction_aggregator.get_cognition_context(symbol)
                macro_ctx = self.prediction_aggregator.get_macro_context()
                if macro_ctx:
                    pm_context = f"{pm_context}\n{macro_ctx}" if pm_context else macro_ctx
            except Exception:
                pass  # Prediction market data is non-critical

        prompt = (
            f"INTERNAL ALPHA SCAN — {symbol}\n"
            f"Current price: ${price:,.2f}\n"
            f"1-min momentum: {momentum_1m:+.3f}%\n"
            f"5-min momentum: {momentum_5m:+.3f}%\n"
            f"Available venues: {', '.join(venues)}\n"
            f"Execution stage: {execution_state.get('dex_execution_stage', 'unknown')}\n"
        )
        if memory_advice:
            prompt += f"Past experience: {memory_advice[:300]}\n"
        if pm_context:
            prompt += f"\n{pm_context}\n"
        prompt += (
            "\nBased on momentum, price action, prediction market probabilities, and market conditions:\n"
            "Should we BUY, SELL, or HOLD this asset?\n"
            "Only recommend BUY/SELL if you see a clear short-term opportunity.\n"
            "Default to HOLD if uncertain.\n"
            "Respond with DECISION: BUY/SELL/HOLD, CONFIDENCE: 0-1, REASONING: <why>"
        )

        try:
            result = await self.cognition.process(
                CognitionRequest(
                    prompt=prompt,
                    speed=CognitionSpeed.DUAL,
                    max_latency_ms=8000,
                )
            )
        except Exception as exc:
            logger.warning(f"Cognition error for {symbol}: {exc}")
            return None

        logger.info(
            f"🔍 Alpha scan {symbol}: {result.decision} "
            f"(conf={result.confidence:.2f}, latency={result.latency_ms:.0f}ms)"
        )

        if result.decision in ("BUY", "SELL") and result.confidence >= self._min_confidence:
            base_qty = float(execution_state.get("base_quantity", 0.02))
            return {
                "action": result.decision.lower(),
                "symbol": symbol,
                "venue": "ALL",
                "quantity": base_qty,
                "source": "alpha_scanner",
                "strategy": "internal_alpha",
                "_confidence": result.confidence,
                "_reasoning": result.reasoning[:300],
                "_cognition_latency_ms": result.latency_ms,
            }

        return None

    def resolve_signal(self, signal_key: str, success: bool):
        """Called when a signal's trade completes (success or fail)."""
        self._pending_count = max(0, self._pending_count - 1)


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_symbols(raw: str) -> List[str]:
    import re

    tokens = re.split(r"[,;|\s]+", str(raw or "").strip())
    seen = set()
    result = []
    for t in tokens:
        s = t.strip().upper()
        if s and s not in seen:
            seen.add(s)
            result.append(s)
    return result or ["BTC", "ETH", "SOL"]
