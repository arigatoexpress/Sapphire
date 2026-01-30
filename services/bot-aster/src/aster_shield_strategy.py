"""
Aster Shield Strategy - High-Leverage HFT with Intelligent Protection

"Shield" Concept: Software-level protective layer for high-leverage trading

Components:
1. Rapid SL Placement: Stop-loss placed within 100ms of entry
2. Dynamic Leverage: 10-125x based on asset and confidence
3. Position Chasing: Trail winning positions with dynamic stops
4. Intelligent SL Distance: Tighter stops for higher leverage

Shield SL Formula:
  sl_distance = base_volatility / √leverage

Examples:
- 10x leverage, 2% volatility → 0.63% SL
- 50x leverage, 2% volatility → 0.28% SL
- 125x leverage, 2% volatility → 0.18% SL

Safety Features:
- Maximum leverage caps per asset (BTC: 125x, ETH: 100x, Altcoins: 75x)
- Volatility-adjusted position sizing
- Confidence-based leverage scaling
- Portfolio-level risk limits
"""

import asyncio
import logging
import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class ShieldStatus(Enum):
    """Shield execution status"""
    PENDING = "pending"
    ENTRY_EXECUTED = "entry_executed"
    SL_PLACED = "sl_placed"
    ACTIVE = "active"
    TRAILING = "trailing"
    CLOSED = "closed"
    FAILED = "failed"


@dataclass
class ShieldTradeResult:
    """Result of a shield trade execution"""
    status: ShieldStatus
    entry_order_id: Optional[str] = None
    sl_order_id: Optional[str] = None
    entry_price: float = 0.0
    sl_price: float = 0.0
    leverage: float = 0.0
    quantity: float = 0.0
    entry_timestamp: float = 0.0
    sl_timestamp: float = 0.0
    sl_placement_latency_ms: float = 0.0
    error: Optional[str] = None
    reasoning: str = ""


class AsterShieldStrategy:
    """
    High-frequency trading strategy with intelligent stop-loss protection

    Key Features:
    - Ultra-fast SL placement (<100ms target)
    - Dynamic leverage (10-125x based on asset and confidence)
    - Trailing stops for profit protection
    - Volatility-adjusted risk management
    """

    # Asset-specific maximum leverage
    ASSET_MAX_LEVERAGE = {
        "btc": 125,
        "eth": 100,
        "default": 75,  # Altcoins
    }

    # Base leverage per asset (before adjustments)
    ASSET_BASE_LEVERAGE = {
        "btc": 20,
        "eth": 15,
        "default": 10,  # Altcoins
    }

    def __init__(self, aster_client):
        """
        Initialize Aster Shield Strategy

        Args:
            aster_client: Aster API client for order execution
        """
        self.aster_client = aster_client
        self.active_shields: Dict[str, Dict[str, Any]] = {}

        # Performance tracking
        self.shield_stats = {
            "total_shields": 0,
            "successful_shields": 0,
            "avg_sl_latency_ms": 0.0,
            "fastest_sl_ms": float('inf'),
            "slowest_sl_ms": 0.0,
        }

        logger.info(f"🛡️ AsterShieldStrategy initialized | Max leverage: BTC {self.ASSET_MAX_LEVERAGE['btc']}x, ETH {self.ASSET_MAX_LEVERAGE['eth']}x")

    def get_asset_base_name(self, symbol: str) -> str:
        """
        Extract base asset name from symbol

        Examples:
        - BTCUSDT → btc
        - ETH-PERP → eth
        - SOL/USD → sol
        """
        # Remove common suffixes and delimiters
        base = symbol.upper().split('-')[0].split('/')[0].replace('USDT', '').replace('USD', '').replace('PERP', '')
        return base.lower()

    def calculate_intelligent_leverage(
        self,
        symbol: str,
        confidence: float,
        signal_strength: float,
        volatility: float,
        portfolio_leverage: float = 0.0
    ) -> float:
        """
        Calculate optimal leverage for shield trade

        Formula:
        leverage = base_leverage × confidence × signal_strength × volatility_adj × portfolio_adj

        Capped by asset maximum leverage

        Args:
            symbol: Trading symbol
            confidence: Signal confidence (0-1)
            signal_strength: Signal strength (0-1)
            volatility: Recent volatility (e.g., 0.02 for 2%)
            portfolio_leverage: Current portfolio aggregate leverage

        Returns:
            Optimal leverage (10-125x depending on asset)
        """
        base_asset = self.get_asset_base_name(symbol)

        # Get base and max leverage for asset
        base_leverage = self.ASSET_BASE_LEVERAGE.get(base_asset, self.ASSET_BASE_LEVERAGE["default"])
        max_leverage = self.ASSET_MAX_LEVERAGE.get(base_asset, self.ASSET_MAX_LEVERAGE["default"])

        # Confidence adjustment (0.3-1.0)
        confidence = max(0.3, min(1.0, confidence))

        # Volatility adjustment (reduce leverage for higher volatility)
        # 1% vol = 1.0x, 5% vol = 0.6x, 10% vol = 0.3x
        volatility_adj = 1.0 - (volatility - 0.01) * 8.0
        volatility_adj = max(0.3, min(1.0, volatility_adj))

        # Portfolio leverage adjustment
        if portfolio_leverage < 5.0:
            portfolio_adj = 1.0
        elif portfolio_leverage < 10.0:
            portfolio_adj = 0.7
        else:
            portfolio_adj = 0.5

        # Calculate leverage
        leverage = base_leverage * confidence * signal_strength * volatility_adj * portfolio_adj

        # Cap at asset maximum
        leverage = max(10.0, min(leverage, max_leverage))

        logger.info(
            f"🎯 Shield leverage for {symbol}: {leverage:.1f}x | "
            f"Base: {base_leverage}x | Conf: {confidence:.2f} | "
            f"Vol adj: {volatility_adj:.2f} | Max: {max_leverage}x"
        )

        return leverage

    def calculate_shield_sl(
        self,
        entry_price: float,
        leverage: float,
        volatility: float,
        side: str = "LONG"
    ) -> float:
        """
        Calculate shield stop-loss price

        Formula: sl_distance = base_volatility / √leverage

        Tighter stops for higher leverage to limit absolute risk

        Args:
            entry_price: Entry price
            leverage: Position leverage
            volatility: Recent volatility (e.g., 0.02 for 2%)
            side: Position side (LONG or SHORT)

        Returns:
            Stop-loss price
        """
        # Shield SL distance formula
        sl_distance_pct = volatility / math.sqrt(leverage)

        # Minimum SL distance (0.1% for extremely high leverage)
        sl_distance_pct = max(0.001, sl_distance_pct)

        # Calculate SL price
        if side.upper() == "LONG":
            sl_price = entry_price * (1 - sl_distance_pct)
        else:
            sl_price = entry_price * (1 + sl_distance_pct)

        logger.debug(
            f"Shield SL: {entry_price:.4f} → {sl_price:.4f} | "
            f"Distance: {sl_distance_pct:.2%} | Leverage: {leverage:.1f}x"
        )

        return sl_price

    async def execute_shield_trade(
        self,
        symbol: str,
        signal_strength: float,
        confidence: float,
        current_price: float,
        side: str = "LONG",
        volatility: float = 0.02,
        portfolio_leverage: float = 0.0,
        quantity: Optional[float] = None
    ) -> ShieldTradeResult:
        """
        Execute a shield-protected trade with rapid SL placement

        Execution flow:
        1. Calculate optimal leverage (10-125x)
        2. Calculate shield SL distance
        3. Execute entry order
        4. Place SL order (< 100ms after entry)
        5. Monitor position with trailing stop

        Args:
            symbol: Trading symbol
            signal_strength: Signal strength (0-1)
            confidence: Signal confidence (0-1)
            current_price: Current market price
            side: Position side (LONG or SHORT)
            volatility: Recent volatility
            portfolio_leverage: Current portfolio leverage
            quantity: Position quantity (calculated if None)

        Returns:
            ShieldTradeResult with execution details
        """
        result = ShieldTradeResult(status=ShieldStatus.PENDING)

        try:
            # 1. Calculate optimal leverage
            leverage = self.calculate_intelligent_leverage(
                symbol, confidence, signal_strength, volatility, portfolio_leverage
            )
            result.leverage = leverage

            # 2. Calculate shield SL
            sl_price = self.calculate_shield_sl(current_price, leverage, volatility, side)
            result.sl_price = sl_price

            # 3. Calculate quantity if not provided
            if quantity is None:
                # Use client's position sizing logic
                quantity = self.aster_client.calculate_position_size(
                    symbol, leverage, current_price
                )
            result.quantity = quantity

            # 4. Execute entry order
            entry_start = time.time()
            entry_order = await self.aster_client.place_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                leverage=leverage,
                order_type="MARKET"
            )
            result.entry_timestamp = time.time()
            result.entry_order_id = entry_order.get("orderId")
            result.entry_price = entry_order.get("price", current_price)
            result.status = ShieldStatus.ENTRY_EXECUTED

            logger.info(
                f"✅ Shield entry executed: {symbol} {side} {quantity} @ {result.entry_price:.4f} | "
                f"{leverage:.1f}x leverage"
            )

            # 5. Place SL order (CRITICAL: Must be fast <100ms)
            sl_start = time.time()
            sl_order = await self.aster_client.place_order(
                symbol=symbol,
                side="SELL" if side == "LONG" else "BUY",
                quantity=quantity,
                price=sl_price,
                order_type="STOP_LOSS",
                reduce_only=True
            )
            sl_end = time.time()

            result.sl_timestamp = sl_end
            result.sl_order_id = sl_order.get("orderId")
            result.sl_placement_latency_ms = (sl_end - sl_start) * 1000
            result.status = ShieldStatus.SL_PLACED

            # Update stats
            self.shield_stats["total_shields"] += 1
            self.shield_stats["successful_shields"] += 1
            self._update_latency_stats(result.sl_placement_latency_ms)

            # Track active shield
            self.active_shields[symbol] = {
                "entry_order_id": result.entry_order_id,
                "sl_order_id": result.sl_order_id,
                "entry_price": result.entry_price,
                "sl_price": result.sl_price,
                "leverage": leverage,
                "quantity": quantity,
                "side": side,
                "entry_time": result.entry_timestamp,
                "highest_profit": 0.0,
                "status": ShieldStatus.ACTIVE,
            }

            logger.info(
                f"🛡️ Shield activated: {symbol} | SL @ {sl_price:.4f} | "
                f"Latency: {result.sl_placement_latency_ms:.1f}ms"
            )

            # Build reasoning
            result.reasoning = (
                f"Shield trade executed: {symbol} {side} {quantity} @ {result.entry_price:.4f} | "
                f"Leverage: {leverage:.1f}x | SL: {sl_price:.4f} ({abs(result.entry_price - sl_price) / result.entry_price:.2%}) | "
                f"SL latency: {result.sl_placement_latency_ms:.1f}ms"
            )

            return result

        except Exception as e:
            logger.error(f"❌ Shield trade failed: {symbol} | Error: {e}")
            result.status = ShieldStatus.FAILED
            result.error = str(e)
            result.reasoning = f"Shield execution failed: {e}"
            return result

    async def update_trailing_stop(
        self,
        symbol: str,
        current_price: float,
        trailing_distance_pct: float = 0.02
    ) -> bool:
        """
        Update trailing stop for active shield position

        Args:
            symbol: Trading symbol
            current_price: Current market price
            trailing_distance_pct: Trailing stop distance (default 2%)

        Returns:
            True if trailing stop updated, False otherwise
        """
        if symbol not in self.active_shields:
            return False

        shield = self.active_shields[symbol]
        side = shield["side"]
        current_sl = shield["sl_price"]
        entry_price = shield["entry_price"]

        # Calculate unrealized P&L
        if side == "LONG":
            unrealized_pnl_pct = (current_price - entry_price) / entry_price
            new_sl = current_price * (1 - trailing_distance_pct)

            # Only trail up for longs
            if new_sl > current_sl and unrealized_pnl_pct > 0.02:  # In profit > 2%
                try:
                    # Cancel old SL
                    await self.aster_client.cancel_order(shield["sl_order_id"])

                    # Place new trailing SL
                    new_sl_order = await self.aster_client.place_order(
                        symbol=symbol,
                        side="SELL",
                        quantity=shield["quantity"],
                        price=new_sl,
                        order_type="STOP_LOSS",
                        reduce_only=True
                    )

                    shield["sl_price"] = new_sl
                    shield["sl_order_id"] = new_sl_order.get("orderId")
                    shield["status"] = ShieldStatus.TRAILING

                    logger.info(
                        f"📈 Trailing SL updated: {symbol} | "
                        f"{current_sl:.4f} → {new_sl:.4f} | P&L: {unrealized_pnl_pct:.2%}"
                    )
                    return True
                except Exception as e:
                    logger.error(f"Failed to update trailing SL: {e}")
                    return False
        else:
            # SHORT position
            unrealized_pnl_pct = (entry_price - current_price) / entry_price
            new_sl = current_price * (1 + trailing_distance_pct)

            # Only trail down for shorts
            if new_sl < current_sl and unrealized_pnl_pct > 0.02:
                try:
                    await self.aster_client.cancel_order(shield["sl_order_id"])

                    new_sl_order = await self.aster_client.place_order(
                        symbol=symbol,
                        side="BUY",
                        quantity=shield["quantity"],
                        price=new_sl,
                        order_type="STOP_LOSS",
                        reduce_only=True
                    )

                    shield["sl_price"] = new_sl
                    shield["sl_order_id"] = new_sl_order.get("orderId")
                    shield["status"] = ShieldStatus.TRAILING

                    logger.info(
                        f"📉 Trailing SL updated: {symbol} | "
                        f"{current_sl:.4f} → {new_sl:.4f} | P&L: {unrealized_pnl_pct:.2%}"
                    )
                    return True
                except Exception as e:
                    logger.error(f"Failed to update trailing SL: {e}")
                    return False

        return False

    def close_shield(self, symbol: str):
        """Mark shield as closed and remove from active tracking"""
        if symbol in self.active_shields:
            self.active_shields[symbol]["status"] = ShieldStatus.CLOSED
            del self.active_shields[symbol]
            logger.info(f"Shield closed: {symbol}")

    def _update_latency_stats(self, latency_ms: float):
        """Update shield latency statistics"""
        n = self.shield_stats["successful_shields"]
        current_avg = self.shield_stats["avg_sl_latency_ms"]

        # Update average
        new_avg = (current_avg * (n - 1) + latency_ms) / n
        self.shield_stats["avg_sl_latency_ms"] = new_avg

        # Update min/max
        self.shield_stats["fastest_sl_ms"] = min(
            self.shield_stats["fastest_sl_ms"], latency_ms
        )
        self.shield_stats["slowest_sl_ms"] = max(
            self.shield_stats["slowest_sl_ms"], latency_ms
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get shield strategy statistics"""
        return {
            **self.shield_stats,
            "active_shields": len(self.active_shields),
            "success_rate": (
                self.shield_stats["successful_shields"] / max(1, self.shield_stats["total_shields"])
            ),
        }

    def get_active_shields(self) -> Dict[str, Dict[str, Any]]:
        """Get all active shield positions"""
        return self.active_shields.copy()
