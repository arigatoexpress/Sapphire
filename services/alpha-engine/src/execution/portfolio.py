"""
Portfolio tracker for Sapphire Alpha Engine.

Maintains an in-memory position book updated by trade execution events
and enriched with live market prices for real-time P&L.

Design:
- Positions keyed by (venue, symbol) — one open position per pair.
- Fills update quantity and average entry price.
- Close fills zero out the position and record realized P&L.
- Market prices from MarketData feeds drive unrealized P&L.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


@dataclass
class Position:
    """A single open position on a specific venue."""

    venue: str
    symbol: str
    side: str  # LONG or SHORT
    quantity: float = 0.0
    entry_price: float = 0.0
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    opened_at: float = 0.0  # epoch seconds
    updated_at: float = 0.0
    fill_count: int = 0

    @property
    def notional(self) -> float:
        return abs(self.quantity * self.current_price) if self.current_price else 0.0

    def update_market_price(self, price: float) -> None:
        if price <= 0:
            return
        self.current_price = price
        if self.side == "LONG":
            self.unrealized_pnl = (price - self.entry_price) * self.quantity
        else:
            self.unrealized_pnl = (self.entry_price - price) * self.quantity
        self.updated_at = time.time()


@dataclass
class ClosedTrade:
    """Record of a completed (closed) trade."""

    venue: str
    symbol: str
    side: str
    quantity: float
    entry_price: float
    exit_price: float
    realized_pnl: float
    closed_at: float
    duration_seconds: float = 0.0


class PortfolioTracker:
    """In-memory portfolio tracker for all venues."""

    def __init__(self, max_closed_trades: int = 500) -> None:
        # Active positions: key = (VENUE, SYMBOL)
        self._positions: Dict[Tuple[str, str], Position] = {}
        # Closed trade history (ring buffer)
        self._closed_trades: List[ClosedTrade] = []
        self._max_closed = max(1, max_closed_trades)
        # Aggregate stats
        self._total_realized_pnl: float = 0.0
        self._total_trades: int = 0
        self._wins: int = 0
        self._losses: int = 0

    # ── Fill Processing ────────────────────────────────────────────

    def process_fill(self, fill: Dict[str, Any]) -> Optional[ClosedTrade]:
        """Process a trade execution fill.

        Returns a ClosedTrade if the fill closed a position, else None.

        Expected fill keys:
            platform/venue, symbol, side (BUY/SELL/LONG/SHORT/CLOSE),
            filled_quantity, avg_price, success, realized_pnl (optional)
        """
        if not fill.get("success", False):
            return None

        venue = str(fill.get("platform") or fill.get("venue") or "").strip().upper()
        symbol = self._normalize_symbol(venue, str(fill.get("symbol") or ""))
        raw_side = str(fill.get("side") or "").strip().upper()
        qty = float(fill.get("filled_quantity") or fill.get("quantity") or 0)
        price = float(fill.get("avg_price") or fill.get("price") or 0)

        if not venue or not symbol or qty <= 0 or price <= 0:
            return None

        key = (venue, symbol)
        self._total_trades += 1

        # CLOSE action always closes the position
        if raw_side == "CLOSE":
            return self._close_position(key, price, qty, fill)

        # Map side to position direction
        if raw_side in ("BUY", "LONG"):
            fill_side = "LONG"
        elif raw_side in ("SELL", "SHORT"):
            fill_side = "SHORT"
        else:
            logger.warning(f"Unknown fill side: {raw_side}")
            return None

        existing = self._positions.get(key)

        if existing is None:
            # New position
            self._positions[key] = Position(
                venue=venue,
                symbol=symbol,
                side=fill_side,
                quantity=qty,
                entry_price=price,
                current_price=price,
                opened_at=time.time(),
                updated_at=time.time(),
                fill_count=1,
            )
            logger.info(f"📈 New position: {venue} {fill_side} {qty} {symbol} @ {price}")
            return None

        if existing.side == fill_side:
            # Adding to position — compute new average entry
            total_cost = (existing.entry_price * existing.quantity) + (price * qty)
            existing.quantity += qty
            existing.entry_price = total_cost / existing.quantity if existing.quantity else price
            existing.fill_count += 1
            existing.updated_at = time.time()
            existing.update_market_price(price)
            logger.info(
                f"📈 Added to {venue} {fill_side} {symbol}: +{qty} @ {price} "
                f"(total: {existing.quantity:.6f} avg: {existing.entry_price:.4f})"
            )
            return None

        # Opposite side — reducing or closing
        if qty >= existing.quantity:
            # Full close (or flip)
            return self._close_position(key, price, existing.quantity, fill)
        else:
            # Partial close
            if existing.side == "LONG":
                pnl = (price - existing.entry_price) * qty
            else:
                pnl = (existing.entry_price - price) * qty

            existing.quantity -= qty
            existing.fill_count += 1
            existing.updated_at = time.time()
            existing.update_market_price(price)

            self._total_realized_pnl += pnl
            if pnl >= 0:
                self._wins += 1
            else:
                self._losses += 1

            logger.info(
                f"📉 Partial close {venue} {symbol}: -{qty} @ {price} "
                f"PnL: {pnl:+.4f} (remaining: {existing.quantity:.6f})"
            )
            return None

    def _close_position(
        self, key: Tuple[str, str], exit_price: float, qty: float, fill: Dict[str, Any]
    ) -> Optional[ClosedTrade]:
        existing = self._positions.pop(key, None)
        if existing is None:
            return None

        # Use fill-provided PnL if available, otherwise calculate
        fill_pnl = None
        for pnl_key in ("realized_pnl", "pnl", "net_pnl", "realizedPnl"):
            val = fill.get(pnl_key)
            if val is not None:
                try:
                    fill_pnl = float(val)
                    break
                except (TypeError, ValueError):
                    pass

        if fill_pnl is not None:
            pnl = fill_pnl
        elif existing.side == "LONG":
            pnl = (exit_price - existing.entry_price) * existing.quantity
        else:
            pnl = (existing.entry_price - exit_price) * existing.quantity

        duration = time.time() - existing.opened_at if existing.opened_at else 0

        closed = ClosedTrade(
            venue=existing.venue,
            symbol=existing.symbol,
            side=existing.side,
            quantity=existing.quantity,
            entry_price=existing.entry_price,
            exit_price=exit_price,
            realized_pnl=pnl,
            closed_at=time.time(),
            duration_seconds=duration,
        )

        self._total_realized_pnl += pnl
        if pnl >= 0:
            self._wins += 1
        else:
            self._losses += 1

        self._closed_trades.append(closed)
        if len(self._closed_trades) > self._max_closed:
            self._closed_trades = self._closed_trades[-self._max_closed:]

        logger.info(
            f"📊 Position closed: {existing.venue} {existing.side} "
            f"{existing.quantity} {existing.symbol} | "
            f"Entry: {existing.entry_price:.4f} Exit: {exit_price:.4f} | "
            f"PnL: {pnl:+.4f} | Duration: {duration:.0f}s"
        )
        return closed

    # ── Market Price Updates ───────────────────────────────────────

    def update_prices(self, snapshot: Dict[str, Dict[str, Dict[str, Any]]]) -> None:
        """Update all positions with latest market prices.

        snapshot format: {VENUE: {SYMBOL: {price: float, ...}}}
        """
        for key, pos in self._positions.items():
            venue_data = snapshot.get(key[0], {})
            sym_data = venue_data.get(key[1], {})
            price = sym_data.get("price", 0)
            if price and price > 0:
                pos.update_market_price(float(price))

    # ── Queries ────────────────────────────────────────────────────

    @property
    def open_positions(self) -> List[Position]:
        return list(self._positions.values())

    @property
    def closed_trades(self) -> List[ClosedTrade]:
        return list(self._closed_trades)

    def position_for(self, venue: str, symbol: str) -> Optional[Position]:
        key = (venue.upper(), self._normalize_symbol(venue.upper(), symbol))
        return self._positions.get(key)

    def snapshot(self) -> Dict[str, Any]:
        """Full portfolio snapshot for Telegram / API / AI context."""
        positions = []
        total_unrealized = 0.0
        total_notional = 0.0

        for pos in self._positions.values():
            total_unrealized += pos.unrealized_pnl
            total_notional += pos.notional
            positions.append({
                "venue": pos.venue,
                "symbol": pos.symbol,
                "side": pos.side,
                "quantity": round(pos.quantity, 6),
                "entry_price": round(pos.entry_price, 6),
                "current_price": round(pos.current_price, 6),
                "unrealized_pnl": round(pos.unrealized_pnl, 4),
                "notional": round(pos.notional, 2),
                "age_seconds": int(time.time() - pos.opened_at) if pos.opened_at else 0,
            })

        closed_count = self._wins + self._losses
        win_rate = (self._wins / closed_count * 100) if closed_count > 0 else 0
        return {
            "open_count": len(self._positions),
            "open_positions": positions,
            "total_unrealized_pnl": round(total_unrealized, 4),
            "total_realized_pnl": round(self._total_realized_pnl, 4),
            "total_notional": round(total_notional, 2),
            "total_trades": self._total_trades,
            "wins": self._wins,
            "losses": self._losses,
            "win_rate": round(win_rate, 1),
            "recent_closed": [
                {
                    "venue": t.venue,
                    "symbol": t.symbol,
                    "side": t.side,
                    "pnl": round(t.realized_pnl, 4),
                    "duration_s": int(t.duration_seconds),
                }
                for t in self._closed_trades[-10:]
            ],
        }

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _normalize_symbol(venue: str, symbol: str) -> str:
        """Normalize symbol for consistent keying."""
        sym = symbol.strip().upper()
        # Strip quote currency for consistent keying across venues
        for suffix in ("USDT", "USDC", "USD", "BUSD"):
            if sym.endswith(suffix) and len(sym) > len(suffix):
                sym = sym[: -len(suffix)]
                break
        return sym
