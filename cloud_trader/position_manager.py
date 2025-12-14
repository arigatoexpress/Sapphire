import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from .definitions import SYMBOL_CONFIG, MinimalAgentState
from .exchange import OrderType

logger = logging.getLogger(__name__)


class PositionManager:
    """
    Manages open positions, including syncing with exchange,
    monitoring for TP/SL, and tracking state.
    """

    def __init__(self, exchange_client, agent_states: Dict[str, MinimalAgentState]):
        self.exchange_client = exchange_client
        self.agent_states = agent_states
        self.open_positions: Dict[str, Dict[str, Any]] = {}

    async def sync_from_exchange(self):
        """Sync positions from exchange to inherit existing positions on startup."""
        try:
            print("🔍 Scanning exchange for existing positions to takeover...")
            # Try to get open positions from the exchange
            response = await self.exchange_client.get_position_risk()

            if not response:
                print("✅ No existing positions found on exchange")
                return

            # Parse and load positions
            for pos in response:
                symbol = pos.get("symbol")
                if not symbol:
                    continue

                # Skip empty positions (Ghost positions)
                amt = float(pos.get("positionAmt", 0))
                if amt == 0:
                    continue

                # Store position in our tracking
                # Assign to default agent if not tracked
                # Use Strategy Optimization Agent or first available
                agent = (
                    self.agent_states.get("strategy-optimization-agent")
                    or list(self.agent_states.values())[0]
                )

                # Store position in our tracking
                self.open_positions[symbol] = {
                    "symbol": symbol,
                    "side": pos.get("positionSide", "LONG"),
                    "quantity": float(pos.get("positionAmt", 0)),
                    "entry_price": float(pos.get("entryPrice", 0)),
                    "unrealized_pnl": float(pos.get("unrealizedProfit", 0)),
                    "leverage": int(pos.get("leverage", 1)),
                    "agent": agent,
                    "agent_id": agent.id,
                    "tp_price": float(pos.get("entryPrice", 0)) * 1.05,  # Default TP
                    "sl_price": float(pos.get("entryPrice", 0)) * 0.95,  # Default SL
                }
                print(
                    f"   ✅ Inherited position: {symbol} {self.open_positions[symbol]['side']} x{self.open_positions[symbol]['quantity']}"
                )

            print(f"✅ Sync complete: Inherited {len(self.open_positions)} positions")

            # NATIVE TP/SL: Place orders for ALL inherited positions
            # This ensures risk is managed even if bot goes offline
            if self.open_positions:
                print(f"🛡️ Placing native TP/SL for {len(self.open_positions)} inherited positions...")
                for symbol, pos in self.open_positions.items():
                    try:
                        entry_price = pos["entry_price"]
                        side = pos["side"]
                        quantity = abs(pos["quantity"])
                        
                        # Determine side from quantity sign if side is ambiguous
                        if side == "BOTH":
                            side = "BUY" if pos["quantity"] > 0 else "SELL"
                        
                        if entry_price > 0 and quantity > 0:
                            await self.place_tpsl_orders(
                                symbol=symbol,
                                entry_price=entry_price,
                                side=side,
                                quantity=quantity,
                                tp_pct=0.05,  # 5% TP
                                sl_pct=0.03,  # 3% SL
                            )
                    except Exception as tpsl_err:
                        print(f"⚠️ Failed to place native TP/SL for inherited {symbol}: {tpsl_err}")
                
                print(f"✅ Native TP/SL setup complete for inherited positions")

        except Exception as e:
            print(f"⚠️ Failed to sync open positions from exchange: {e}")

    async def monitor_positions(self) -> Dict[str, Any]:
        """Monitor open positions for TP/SL hits and return current ticker map."""
        ticker_map = {}
        try:
            # Always fetch all tickers in SYMBOL_CONFIG to support both monitoring AND new trade analysis
            # This acts as a cache for this tick
            symbols_to_fetch = list(SYMBOL_CONFIG.keys())
            tasks = [self.exchange_client.get_ticker(sym) for sym in symbols_to_fetch]
            tickers = await asyncio.gather(*tasks, return_exceptions=True)

            for sym, res in zip(symbols_to_fetch, tickers):
                if isinstance(res, dict):
                    ticker_map[sym] = res
                else:
                    # print(f"⚠️ Failed to fetch ticker for {sym}: {res}")
                    pass

        except Exception as e:
            print(f"⚠️ Error fetching batched tickers: {e}")
            return {}

        if not self.open_positions:
            return ticker_map

        symbols_to_check = list(self.open_positions.keys())
        for symbol in symbols_to_check:
            if symbol not in ticker_map:
                continue

            pos = self.open_positions[symbol]
            agent = pos["agent"]
            ticker = ticker_map[symbol]

            try:
                current_price = float(ticker.get("lastPrice", 0))

                if current_price <= 0:
                    continue

                # Update current price in position for dashboard
                pos["current_price"] = current_price

                # Check TP/SL logic is handled by the caller or we can return signals here
                # For now, we just return the ticker map and let the service handle the actual closing logic
                # using check_profit_taking helper.

                # Ideally, we should move the trailing stop logic here too.
                self._update_trailing_stop(symbol, pos, current_price, agent)

            except Exception as e:
                print(f"⚠️ Error monitoring position {symbol}: {e}")

        return ticker_map

    def _update_trailing_stop(
        self, symbol: str, pos: Dict[str, Any], current_price: float, agent: MinimalAgentState
    ):
        """Internal helper to update trailing stops."""
        try:
            if pos["side"] == "BUY":
                pnl_pct = (current_price - pos["entry_price"]) / pos["entry_price"]

                # 1. Move to Break Even if > 1.5% profit
                if pnl_pct > 0.015 and pos["sl_price"] < pos["entry_price"]:
                    pos["sl_price"] = pos["entry_price"] * 1.002  # BE + small profit
                    print(f"🛡️ Trailing Stop Updated for {symbol} (Long): Moved to Break Even")

                # 2. Lock in Profit if > 3% profit
                elif pnl_pct > 0.03 and pos["sl_price"] < (pos["entry_price"] * 1.015):
                    pos["sl_price"] = pos["entry_price"] * 1.015  # Lock 1.5%
                    print(f"🔒 Trailing Stop Updated for {symbol} (Long): Locked 1.5% Profit")

            elif pos["side"] == "SELL":
                pnl_pct = (pos["entry_price"] - current_price) / pos["entry_price"]

                # 1. Move to Break Even if > 1.5% profit
                if pnl_pct > 0.015 and pos["sl_price"] > pos["entry_price"]:
                    pos["sl_price"] = pos["entry_price"] * 0.998  # BE + small profit
                    print(f"🛡️ Trailing Stop Updated for {symbol} (Short): Moved to Break Even")

                # 2. Lock in Profit if > 3% profit
                elif pnl_pct > 0.03 and pos["sl_price"] > (pos["entry_price"] * 0.985):
                    pos["sl_price"] = pos["entry_price"] * 0.985  # Lock 1.5%
                    print(f"🔒 Trailing Stop Updated for {symbol} (Short): Locked 1.5% Profit")
        except Exception as e:
            print(f"⚠️ Error updating trailing stop for {symbol}: {e}")

    async def update_sl_on_exchange(self, symbol: str, sl_price: float, side: str, quantity: float):
        """
        Syncs the internal Stop Loss price with the exchange by placing/updating a STOP_MARKET order.
        This ensures risk is managed even if the bot goes offline.
        """
        try:
            # Determine order side (Closing logic)
            order_side = "SELL" if side == "BUY" else "BUY"

            # 1. Cancel existing open orders for this symbol to avoid duplicates
            await self.exchange_client.cancel_all_orders(symbol)

            # 2. Place new STOP_MARKET order
            # Note: exact params depend on Aster API specifics, assuming standard params
            order_params = {
                "symbol": symbol,
                "side": order_side,
                "type": "STOP_MARKET",
                "quantity": quantity,
                "stopPrice": sl_price,
                "reduceOnly": True,
            }

            # Execute via exchange client
            print(f"🛡️ Syncing Hard Stop for {symbol}: {order_side} {quantity} @ {sl_price}")
            await self.exchange_client.place_order(
                symbol=symbol,
                side=order_side,
                order_type=OrderType.STOP_MARKET,
                quantity=abs(quantity),
                stop_price=sl_price,
                reduce_only=True,
            )
            print(f"✅ NATIVE SL ORDER PLACED: {symbol} @ {sl_price}")

        except Exception as e:
            print(f"⚠️ Failed to sync SL to exchange for {symbol}: {e}")

    async def update_tp_on_exchange(self, symbol: str, tp_price: float, side: str, quantity: float):
        """
        Places a TAKE_PROFIT_MARKET order on the exchange.
        This ensures profits are captured even if the bot goes offline.
        """
        try:
            # Determine order side (Closing logic)
            order_side = "SELL" if side == "BUY" else "BUY"

            # Place TAKE_PROFIT_MARKET order
            print(f"💰 Syncing Take Profit for {symbol}: {order_side} {quantity} @ {tp_price}")
            await self.exchange_client.place_order(
                symbol=symbol,
                side=order_side,
                order_type=OrderType.TAKE_PROFIT_MARKET,
                quantity=abs(quantity),
                stop_price=tp_price,
                reduce_only=True,
            )
            print(f"✅ NATIVE TP ORDER PLACED: {symbol} @ {tp_price}")

        except Exception as e:
            print(f"⚠️ Failed to sync TP to exchange for {symbol}: {e}")

    async def place_tpsl_orders(
        self, 
        symbol: str, 
        entry_price: float, 
        side: str, 
        quantity: float,
        tp_pct: float = 0.05,  # Default 5% TP
        sl_pct: float = 0.03   # Default 3% SL
    ):
        """
        Place both TP and SL orders on the exchange after position entry.
        This is the main method to call after opening a new position.
        """
        try:
            # Cancel any existing orders for this symbol first
            await self.exchange_client.cancel_all_orders(symbol)

            # Calculate TP/SL prices based on side
            if side == "BUY":  # Long position
                tp_price = entry_price * (1 + tp_pct)
                sl_price = entry_price * (1 - sl_pct)
            else:  # Short position
                tp_price = entry_price * (1 - tp_pct)
                sl_price = entry_price * (1 + sl_pct)

            print(f"📊 Placing native TP/SL for {symbol}: Entry={entry_price:.6f}, TP={tp_price:.6f} ({tp_pct*100}%), SL={sl_price:.6f} ({sl_pct*100}%)")

            # Place both orders concurrently
            await asyncio.gather(
                self.update_tp_on_exchange(symbol, tp_price, side, quantity),
                self.update_sl_on_exchange(symbol, sl_price, side, quantity),
                return_exceptions=True
            )

            # Update internal tracking
            if symbol in self.open_positions:
                self.open_positions[symbol]["tp_price"] = tp_price
                self.open_positions[symbol]["sl_price"] = sl_price

            print(f"✅ NATIVE TP/SL ACTIVE for {symbol}")
            return True

        except Exception as e:
            print(f"❌ Failed to place TP/SL orders for {symbol}: {e}")
            return False

    async def check_profit_taking(
        self, symbol: str, position: Dict[str, Any], current_price: float
    ) -> Tuple[bool, str]:
        """Check if a position should be closed for profit or stop loss."""
        try:
            entry_price = position["entry_price"]
            side = position["side"]

            if side == "BUY":
                pnl_pct = (current_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - current_price) / entry_price

            # Dynamic TP/SL based on agent settings if available
            agent = position.get("agent")

            # Defaults
            tp_target = 0.02
            sl_target = -0.05

            if hasattr(agent, "profit_target"):
                tp_target = agent.profit_target

            # Hard Profit Target
            if pnl_pct > tp_target:
                return True, f"Hard Profit Target Hit (+{pnl_pct*100:.2f}%)"

            # Hard Stop Loss (Internal check, backup to exchange SL)
            # We use a slightly tighter internal stop to trigger before liquidation
            if pnl_pct < sl_target:
                return True, f"Hard Stop Loss Hit ({pnl_pct*100:.2f}%)"

            # Trailing Stop Logic
            # If we are up > 1%, ensure we don't lose it all
            if pnl_pct > 0.012 and pnl_pct < 0.005:
                return True, f"Trailing Stop Hit (Locked in {pnl_pct*100:.2f}%)"

            # "Panic Button" / Volatility check (Future expansion)
            # If price moves against us > 2% in 1 minute -> Close

            return False, ""
        except Exception as e:
            print(f"⚠️ Error in profit taking check: {e}")
            return False, ""
