"""
Sapphire V2 Position Tracker
Unified position management across all platforms.
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Represents an open trading position."""

    symbol: str
    side: str  # BUY or SELL
    quantity: float
    entry_price: float
    platform: str
    open_time: float
    agent_id: Optional[str] = None
    unrealized_pnl: float = 0.0
    current_price: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Trailing stop-loss fields
    highest_price: float = 0.0  # For long positions
    lowest_price: float = float("inf")  # For short positions
    trailing_stop_pct: float = 0.03  # 3% default trailing stop
    trailing_stop_active: bool = False  # Activate after reaching profit threshold
    profit_threshold_pct: float = 0.02  # Activate trailing stop after 2% profit

    def update_trailing_stop(self, current_price: float) -> Optional[float]:
        """
        Update trailing stop levels based on current price.
        Returns stop price if triggered, None otherwise.
        """
        self.current_price = current_price

        if self.side == "BUY":  # Long position
            pnl_pct = (current_price - self.entry_price) / self.entry_price if self.entry_price > 0 else 0

            # Activate trailing stop after reaching profit threshold
            if pnl_pct >= self.profit_threshold_pct and not self.trailing_stop_active:
                self.trailing_stop_active = True
                self.highest_price = current_price
                logger.info(f"📈 Trailing stop ACTIVATED for {self.symbol} at {pnl_pct:.1%} profit")

            if self.trailing_stop_active:
                # Update highest price
                if current_price > self.highest_price:
                    self.highest_price = current_price

                # Calculate trailing stop price
                stop_price = self.highest_price * (1 - self.trailing_stop_pct)

                # Check if stop is triggered
                if current_price <= stop_price:
                    return stop_price

        else:  # Short position
            pnl_pct = (self.entry_price - current_price) / self.entry_price if self.entry_price > 0 else 0

            # Activate trailing stop after reaching profit threshold
            if pnl_pct >= self.profit_threshold_pct and not self.trailing_stop_active:
                self.trailing_stop_active = True
                self.lowest_price = current_price
                logger.info(f"📉 Trailing stop ACTIVATED for {self.symbol} short at {pnl_pct:.1%} profit")

            if self.trailing_stop_active:
                # Update lowest price
                if current_price < self.lowest_price:
                    self.lowest_price = current_price

                # Calculate trailing stop price
                stop_price = self.lowest_price * (1 + self.trailing_stop_pct)

                # Check if stop is triggered
                if current_price >= stop_price:
                    return stop_price

        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "platform": self.platform,
            "open_time": self.open_time,
            "agent_id": self.agent_id,
            "unrealized_pnl": self.unrealized_pnl,
            "current_price": self.current_price,
            "metadata": self.metadata,
            "highest_price": self.highest_price,
            "lowest_price": self.lowest_price if self.lowest_price != float("inf") else 0,
            "trailing_stop_active": self.trailing_stop_active,
            "trailing_stop_pct": self.trailing_stop_pct,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Position":
        return cls(
            symbol=data["symbol"],
            side=data["side"],
            quantity=data["quantity"],
            entry_price=data["entry_price"],
            platform=data.get("platform", "aster"),
            open_time=data.get("open_time", time.time()),
            agent_id=data.get("agent_id"),
            unrealized_pnl=data.get("unrealized_pnl", 0.0),
            current_price=data.get("current_price", 0.0),
            metadata=data.get("metadata", {}),
        )


class PositionTracker:
    """
    Unified position management across all platforms.

    Features:
    - Track positions from Aster, Drift, Symphony, Hyperliquid
    - Persistent storage
    - Real-time P&L calculation
    - Position reconciliation
    """

    def __init__(self, platform_router=None):
        self.router = platform_router
        self._positions: Dict[str, Position] = {}
        self._closed_positions: List[Dict] = []
        self._storage_path = Path("data/positions.json")

        # Load persisted positions
        self._load_positions()

        logger.info(f"📊 PositionTracker initialized with {len(self._positions)} positions")

    async def open(
        self,
        symbol: str,
        side: str,
        quantity: float,
        entry_price: float,
        platform: str,
        agent_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Position:
        """Open a new position."""
        position = Position(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            platform=platform,
            open_time=time.time(),
            agent_id=agent_id,
            metadata=metadata or {},
        )

        self._positions[symbol] = position
        self._save_positions()

        logger.info(f"📈 Opened {side} {symbol}: {quantity} @ ${entry_price:.2f} [{platform}]")
        return position

    async def close(self, symbol: str) -> Optional[Dict]:
        """Close a position and record the outcome."""
        if symbol not in self._positions:
            logger.warning(f"Position {symbol} not found")
            return None

        position = self._positions.pop(symbol)

        # Calculate P&L
        pnl = 0.0
        if position.current_price > 0:
            if position.side == "BUY":
                pnl = (position.current_price - position.entry_price) * position.quantity
            else:
                pnl = (position.entry_price - position.current_price) * position.quantity

        # Record closed position
        closed = {
            **position.to_dict(),
            "close_time": time.time(),
            "close_price": position.current_price,
            "realized_pnl": pnl,
            "duration_seconds": time.time() - position.open_time,
        }

        self._closed_positions.append(closed)
        if len(self._closed_positions) > 100:
            self._closed_positions = self._closed_positions[-100:]

        self._save_positions()

        logger.info(f"📉 Closed {symbol}: P&L ${pnl:.2f}")
        return closed

    async def get_all(self) -> Dict[str, Dict]:
        """Get all open positions."""
        return {sym: pos.to_dict() for sym, pos in self._positions.items()}

    async def get(self, symbol: str) -> Optional[Position]:
        """Get a specific position."""
        return self._positions.get(symbol)

    async def update_prices(self, prices: Dict[str, float]):
        """Update current prices and calculate unrealized P&L."""
        for symbol, position in self._positions.items():
            if symbol in prices:
                position.current_price = prices[symbol]

                if position.side == "BUY":
                    position.unrealized_pnl = (
                        prices[symbol] - position.entry_price
                    ) * position.quantity
                else:
                    position.unrealized_pnl = (
                        position.entry_price - prices[symbol]
                    ) * position.quantity

    async def check_trailing_stops(self, prices: Dict[str, float]) -> List[Dict[str, Any]]:
        """
        Check all positions for trailing stop triggers.

        Args:
            prices: Dict of symbol -> current price

        Returns:
            List of triggered stops with symbol, stop_price, and reason
        """
        triggered = []

        for symbol, position in self._positions.items():
            if symbol not in prices:
                continue

            current_price = prices[symbol]
            stop_price = position.update_trailing_stop(current_price)

            if stop_price is not None:
                pnl_pct = 0
                if position.side == "BUY":
                    pnl_pct = (current_price - position.entry_price) / position.entry_price * 100
                else:
                    pnl_pct = (position.entry_price - current_price) / position.entry_price * 100

                triggered.append({
                    "symbol": symbol,
                    "side": position.side,
                    "entry_price": position.entry_price,
                    "current_price": current_price,
                    "stop_price": stop_price,
                    "highest_price": position.highest_price,
                    "lowest_price": position.lowest_price if position.lowest_price != float("inf") else 0,
                    "pnl_pct": pnl_pct,
                    "platform": position.platform,
                    "reason": "trailing_stop_triggered",
                })

                logger.info(
                    f"🛑 Trailing stop TRIGGERED for {symbol}: "
                    f"Stop @ ${stop_price:.2f}, Current @ ${current_price:.2f}, "
                    f"PnL: {pnl_pct:.1f}%"
                )

        return triggered

    async def set_trailing_stop_params(
        self,
        symbol: str,
        trailing_stop_pct: float = None,
        profit_threshold_pct: float = None,
    ) -> bool:
        """Configure trailing stop parameters for a position."""
        if symbol not in self._positions:
            return False

        position = self._positions[symbol]

        if trailing_stop_pct is not None:
            position.trailing_stop_pct = trailing_stop_pct

        if profit_threshold_pct is not None:
            position.profit_threshold_pct = profit_threshold_pct

        self._save_positions()
        logger.info(
            f"⚙️ Updated trailing stop for {symbol}: "
            f"Stop={position.trailing_stop_pct:.1%}, Threshold={position.profit_threshold_pct:.1%}"
        )
        return True

    def get_total_exposure(self) -> float:
        """Get total exposure across all positions."""
        return sum(pos.quantity * pos.entry_price for pos in self._positions.values())

    def get_unrealized_pnl(self) -> float:
        """Get total unrealized P&L."""
        return sum(pos.unrealized_pnl for pos in self._positions.values())

    def get_position_count(self) -> int:
        """Get number of open positions."""
        return len(self._positions)

    def get_recent_closed(self, limit: int = 10) -> List[Dict]:
        """Get recently closed positions."""
        return self._closed_positions[-limit:]

    def _load_positions(self):
        """Load positions from disk."""
        try:
            if self._storage_path.exists():
                with open(self._storage_path, "r") as f:
                    data = json.load(f)
                    for pos_data in data.get("positions", []):
                        pos = Position.from_dict(pos_data)
                        self._positions[pos.symbol] = pos
                    self._closed_positions = data.get("closed", [])
        except Exception as e:
            logger.warning(f"Failed to load positions: {e}")

    def _save_positions(self):
        """Save positions to disk."""
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._storage_path, "w") as f:
                json.dump(
                    {
                        "positions": [pos.to_dict() for pos in self._positions.values()],
                        "closed": self._closed_positions,
                    },
                    f,
                    indent=2,
                )
        except Exception as e:
            logger.warning(f"Failed to save positions: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get position statistics."""
        if not self._closed_positions:
            return {
                "open_positions": len(self._positions),
                "total_exposure": self.get_total_exposure(),
                "unrealized_pnl": self.get_unrealized_pnl(),
                "closed_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
            }

        wins = sum(1 for p in self._closed_positions if p.get("realized_pnl", 0) > 0)
        total_pnl = sum(p.get("realized_pnl", 0) for p in self._closed_positions)

        return {
            "open_positions": len(self._positions),
            "total_exposure": self.get_total_exposure(),
            "unrealized_pnl": self.get_unrealized_pnl(),
            "closed_trades": len(self._closed_positions),
            "win_rate": wins / len(self._closed_positions) if self._closed_positions else 0.0,
            "total_pnl": total_pnl,
        }
