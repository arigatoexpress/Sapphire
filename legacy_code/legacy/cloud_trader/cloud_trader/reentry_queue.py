"""
Re-Entry Queue System for Adversarial PvP Trading

When stopped out, we queue for re-entry at BETTER prices.
This creates asymmetric upside - we lose small, but can re-enter
at better prices when market makers exhaust their stop hunt.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ReEntryReason(Enum):
    """Reasons for re-entry being triggered."""

    PRICE_TARGET_HIT = "price_target_hit"
    MOMENTUM_REVERSAL = "momentum_reversal"
    VOLUME_CAPITULATION = "volume_capitulation"
    STOP_HUNT_DETECTED = "stop_hunt_detected"
    HIGHER_TF_SUPPORT = "higher_tf_support"


@dataclass
class ReEntryOrder:
    """A queued re-entry order after stop-out."""

    symbol: str
    direction: str  # "LONG" or "SHORT"
    original_stop_price: float
    target_entry_price: float  # Better price to re-enter
    confidence: float  # Higher confidence on re-entry (was right direction)
    created_at: float
    expiry: float  # When this re-entry expires
    original_thesis: str
    atr_at_stop: float  # ATR when stopped out (for dynamic scaling)
    attempts: int = 0
    max_attempts: int = 3

    def is_expired(self) -> bool:
        return time.time() > self.expiry

    def should_trigger(
        self, current_price: float, current_momentum: float = 0
    ) -> Optional[ReEntryReason]:
        """Check if re-entry conditions are met."""
        if self.is_expired():
            return None

        if self.direction == "LONG":
            # Price dropped below target (better entry)
            if current_price <= self.target_entry_price:
                return ReEntryReason.PRICE_TARGET_HIT
            # Momentum reversing bullish after stop
            if current_momentum > 0.6:
                return ReEntryReason.MOMENTUM_REVERSAL
        else:  # SHORT
            # Price rose above target (better entry)
            if current_price >= self.target_entry_price:
                return ReEntryReason.PRICE_TARGET_HIT
            # Momentum reversing bearish after stop
            if current_momentum < -0.6:
                return ReEntryReason.MOMENTUM_REVERSAL

        return None


class ReEntryQueue:
    """
    Manages re-entry orders for positions that were stopped out.

    Philosophy: When we're stopped out, we were often RIGHT about direction
    but WRONG about timing. Market makers hunt stops, then price continues
    our way. We queue for re-entry at better prices.
    """

    def __init__(self):
        self._queue: Dict[str, ReEntryOrder] = {}
        self._completed: List[Dict[str, Any]] = []
        self._stats = {
            "queued": 0,
            "triggered": 0,
            "expired": 0,
            "successful": 0,
        }

    def queue_reentry(
        self,
        symbol: str,
        direction: str,
        stop_price: float,
        atr: float,
        thesis: str = "",
        confidence_boost: float = 1.1,  # 10% confidence boost on re-entry
    ) -> ReEntryOrder:
        """
        Queue a re-entry after stop-out.

        Dynamic re-entry price based on ATR:
        - High volatility = wait for bigger pullback (2-3x ATR)
        - Low volatility = smaller pullback (1-1.5x ATR)
        """
        # Dynamic re-entry distance based on ATR
        # Higher ATR = wait for bigger move (market is volatile)
        atr_multiplier = 1.5 + min(atr / stop_price * 100, 1.5)  # 1.5x to 3x ATR
        reentry_distance = atr * atr_multiplier

        if direction == "LONG":
            # Re-enter BELOW our stop (better price for long)
            target_price = stop_price - reentry_distance
        else:
            # Re-enter ABOVE our stop (better price for short)
            target_price = stop_price + reentry_distance

        # Dynamic expiry based on volatility
        # Higher volatility = longer wait (more time for stop hunt to complete)
        expiry_hours = 2 + min(atr / stop_price * 200, 6)  # 2-8 hours

        order = ReEntryOrder(
            symbol=symbol,
            direction=direction,
            original_stop_price=stop_price,
            target_entry_price=target_price,
            confidence=min(0.95, 0.75 * confidence_boost),  # Boosted confidence
            created_at=time.time(),
            expiry=time.time() + expiry_hours * 3600,
            original_thesis=thesis,
            atr_at_stop=atr,
        )

        self._queue[symbol] = order
        self._stats["queued"] += 1

        distance_pct = abs(target_price - stop_price) / stop_price * 100
        logger.info(
            f"📋 QUEUED RE-ENTRY: {symbol} {direction} "
            f"target=${target_price:.4f} ({distance_pct:.1f}% from stop) "
            f"expires in {expiry_hours:.1f}h"
        )
        print(
            f"📋 QUEUED RE-ENTRY: {symbol} {direction} "
            f"target=${target_price:.4f} ({distance_pct:.1f}% from stop) "
            f"expires in {expiry_hours:.1f}h"
        )

        return order

    def check_reentries(
        self,
        ticker_map: Dict[str, Any],
        momentum_scores: Dict[str, float] = None,
    ) -> List[ReEntryOrder]:
        """
        Check all queued re-entries and return ones that should trigger.
        """
        triggered = []
        expired = []

        for symbol, order in list(self._queue.items()):
            if order.is_expired():
                expired.append(symbol)
                continue

            ticker = ticker_map.get(symbol)
            if not ticker:
                continue

            current_price = float(ticker.get("lastPrice", 0))
            if current_price == 0:
                continue

            momentum = (momentum_scores or {}).get(symbol, 0)
            reason = order.should_trigger(current_price, momentum)

            if reason:
                order.attempts += 1
                triggered.append(order)
                self._stats["triggered"] += 1

                logger.info(
                    f"🔄 RE-ENTRY TRIGGERED: {symbol} {order.direction} "
                    f"reason={reason.value} price=${current_price:.4f}"
                )
                print(
                    f"🔄 RE-ENTRY TRIGGERED: {symbol} {order.direction} "
                    f"reason={reason.value} price=${current_price:.4f}"
                )

        # Clean up expired
        for symbol in expired:
            self._stats["expired"] += 1
            del self._queue[symbol]
            print(f"⏰ RE-ENTRY EXPIRED: {symbol}")

        return triggered

    def mark_successful(self, symbol: str):
        """Mark a re-entry as successfully executed."""
        if symbol in self._queue:
            order = self._queue.pop(symbol)
            self._completed.append(
                {
                    "symbol": symbol,
                    "direction": order.direction,
                    "completed_at": time.time(),
                }
            )
            self._stats["successful"] += 1

    def remove(self, symbol: str):
        """Remove a pending re-entry."""
        if symbol in self._queue:
            del self._queue[symbol]

    def get_pending(self, symbol: str) -> Optional[ReEntryOrder]:
        """Get pending re-entry for a symbol."""
        return self._queue.get(symbol)

    def get_all_pending(self) -> Dict[str, ReEntryOrder]:
        """Get all pending re-entries."""
        return dict(self._queue)

    def get_stats(self) -> Dict[str, int]:
        """Get re-entry statistics."""
        return dict(self._stats)


# Global instance
_reentry_queue: Optional[ReEntryQueue] = None


def get_reentry_queue() -> ReEntryQueue:
    """Get or create the global re-entry queue."""
    global _reentry_queue
    if _reentry_queue is None:
        _reentry_queue = ReEntryQueue()
    return _reentry_queue
