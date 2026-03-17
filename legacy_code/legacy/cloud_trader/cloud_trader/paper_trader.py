"""
Paper Trading Module
Simulates live trading using testnet APIs for validation.
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class PaperTradeStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class PaperTrade:
    """Represents a simulated trade."""
    id: str
    symbol: str
    side: str
    quantity: float
    price: float
    timestamp: datetime
    status: PaperTradeStatus = PaperTradeStatus.PENDING
    fill_price: float = 0.0
    pnl: float = 0.0


@dataclass
class PaperPortfolio:
    """Tracks paper trading portfolio state."""
    initial_balance: float = 10000.0
    cash: float = 10000.0
    positions: Dict[str, float] = field(default_factory=dict)
    trades: List[PaperTrade] = field(default_factory=list)
    equity_history: List[float] = field(default_factory=list)
    
    def get_total_value(self, prices: Dict[str, float]) -> float:
        """Calculate total portfolio value."""
        position_value = sum(
            qty * prices.get(sym, 0) for sym, qty in self.positions.items()
        )
        return self.cash + position_value
    
    def get_pnl(self, prices: Dict[str, float]) -> float:
        """Calculate total PnL."""
        return self.get_total_value(prices) - self.initial_balance


class PaperTrader:
    """
    Paper trading simulator using testnet APIs.
    
    Supports:
    - Binance Testnet
    - Simulated order execution with realistic fills
    - Portfolio tracking and performance metrics
    """

    def __init__(
        self,
        exchange_id: str = "binance",
        testnet: bool = True,
        initial_balance: float = 10000.0,
        slippage_pct: float = 0.0005,
        fee_pct: float = 0.001,
    ):
        self.exchange_id = exchange_id
        self.testnet = testnet
        self.slippage_pct = slippage_pct
        self.fee_pct = fee_pct
        
        self.portfolio = PaperPortfolio(
            initial_balance=initial_balance,
            cash=initial_balance
        )
        
        self.exchange = None
        self._running = False
        self._price_cache: Dict[str, float] = {}
        self._callbacks: List[Callable] = []

    async def connect(self):
        """Connect to exchange (testnet if enabled)."""
        try:
            import ccxt.async_support as ccxt
            
            options = {
                "enableRateLimit": True,
            }
            
            if self.testnet:
                # Binance testnet URLs
                if self.exchange_id == "binance":
                    options["urls"] = {
                        "api": {
                            "public": "https://testnet.binance.vision/api/v3",
                            "private": "https://testnet.binance.vision/api/v3",
                        }
                    }
                    # Use test API keys from env
                    options["apiKey"] = os.getenv("BINANCE_TESTNET_API_KEY", "")
                    options["secret"] = os.getenv("BINANCE_TESTNET_SECRET", "")
            
            exchange_class = getattr(ccxt, self.exchange_id)
            self.exchange = exchange_class(options)
            
            logger.info(f"📊 Paper trader connected to {self.exchange_id} ({'testnet' if self.testnet else 'mainnet'})")
            
        except Exception as e:
            logger.warning(f"Exchange connection failed, using simulation mode: {e}")
            self.exchange = None

    async def disconnect(self):
        """Disconnect from exchange."""
        if self.exchange:
            await self.exchange.close()
            self.exchange = None

    async def get_price(self, symbol: str) -> float:
        """Get current price for symbol."""
        if self.exchange:
            try:
                ticker = await self.exchange.fetch_ticker(symbol)
                price = ticker.get("last", 0)
                self._price_cache[symbol] = price
                return price
            except Exception as e:
                logger.warning(f"Price fetch failed: {e}")
        
        # Fallback to cached or simulated
        return self._price_cache.get(symbol, 100.0)

    async def execute_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "market",
    ) -> PaperTrade:
        """
        Execute a paper order.
        
        Args:
            symbol: Trading pair (e.g., BTC/USDT)
            side: BUY or SELL
            quantity: Order quantity
            order_type: market or limit
            
        Returns:
            PaperTrade with execution details
        """
        trade_id = f"paper_{int(time.time() * 1000)}"
        
        # Get current price
        price = await self.get_price(symbol)
        
        # Apply slippage
        if side == "BUY":
            fill_price = price * (1 + self.slippage_pct)
        else:
            fill_price = price * (1 - self.slippage_pct)
        
        # Calculate costs
        notional = fill_price * quantity
        fee = notional * self.fee_pct
        
        # Create trade
        trade = PaperTrade(
            id=trade_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            timestamp=datetime.now(),
            status=PaperTradeStatus.FILLED,
            fill_price=fill_price,
        )
        
        # Update portfolio
        if side == "BUY":
            if self.portfolio.cash >= notional + fee:
                self.portfolio.cash -= (notional + fee)
                self.portfolio.positions[symbol] = self.portfolio.positions.get(symbol, 0) + quantity
                logger.info(f"📈 Paper BUY: {quantity:.4f} {symbol} @ {fill_price:.2f}")
            else:
                trade.status = PaperTradeStatus.REJECTED
                logger.warning(f"❌ Insufficient cash for {notional + fee:.2f}")
        else:  # SELL
            current_qty = self.portfolio.positions.get(symbol, 0)
            if current_qty >= quantity:
                self.portfolio.cash += (notional - fee)
                self.portfolio.positions[symbol] = current_qty - quantity
                logger.info(f"📉 Paper SELL: {quantity:.4f} {symbol} @ {fill_price:.2f}")
            else:
                trade.status = PaperTradeStatus.REJECTED
                logger.warning(f"❌ Insufficient position: {current_qty} < {quantity}")
        
        self.portfolio.trades.append(trade)
        
        # Track equity
        prices = self._price_cache.copy()
        self.portfolio.equity_history.append(self.portfolio.get_total_value(prices))
        
        # Notify callbacks
        for cb in self._callbacks:
            try:
                cb(trade)
            except Exception as e:
                logger.warning(f"Callback error: {e}")
        
        return trade

    async def run_simulation(
        self,
        signals: List[Dict[str, Any]],
        interval_seconds: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Run paper trading simulation from signals.
        
        Args:
            signals: List of {symbol, signal, price?, quantity?}
            interval_seconds: Delay between trades
            
        Returns:
            Simulation results
        """
        self._running = True
        logger.info(f"🚀 Starting paper trading simulation with {len(signals)} signals")
        
        await self.connect()
        
        for signal in signals:
            if not self._running:
                break
            
            symbol = signal.get("symbol", "BTC/USDT")
            sig = signal.get("signal", "HOLD")
            quantity = signal.get("quantity", 0.01)
            
            if sig in ["BUY", "LONG"]:
                await self.execute_order(symbol, "BUY", quantity)
            elif sig in ["SELL", "SHORT", "CLOSE"]:
                # Close existing position
                pos_qty = self.portfolio.positions.get(symbol, 0)
                if pos_qty > 0:
                    await self.execute_order(symbol, "SELL", pos_qty)
            
            await asyncio.sleep(interval_seconds)
        
        await self.disconnect()
        self._running = False
        
        # Calculate final metrics
        final_value = self.portfolio.cash + sum(
            qty * self._price_cache.get(sym, 0) 
            for sym, qty in self.portfolio.positions.items()
        )
        
        return {
            "initial_balance": self.portfolio.initial_balance,
            "final_value": final_value,
            "pnl": final_value - self.portfolio.initial_balance,
            "pnl_pct": (final_value - self.portfolio.initial_balance) / self.portfolio.initial_balance,
            "total_trades": len(self.portfolio.trades),
            "filled_trades": sum(1 for t in self.portfolio.trades if t.status == PaperTradeStatus.FILLED),
            "equity_history": self.portfolio.equity_history,
        }

    def stop(self):
        """Stop running simulation."""
        self._running = False

    def on_trade(self, callback: Callable[[PaperTrade], None]):
        """Register trade callback."""
        self._callbacks.append(callback)

    def get_stats(self) -> Dict[str, Any]:
        """Get current portfolio statistics."""
        prices = self._price_cache.copy()
        total_value = self.portfolio.get_total_value(prices)
        
        filled_trades = [t for t in self.portfolio.trades if t.status == PaperTradeStatus.FILLED]
        wins = sum(1 for t in filled_trades if t.pnl > 0)
        
        return {
            "total_value": total_value,
            "cash": self.portfolio.cash,
            "positions": dict(self.portfolio.positions),
            "pnl": total_value - self.portfolio.initial_balance,
            "trade_count": len(filled_trades),
            "win_rate": wins / len(filled_trades) if filled_trades else 0,
        }
