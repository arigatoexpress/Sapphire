"""
Drift Protocol v2 Client.
Handles Solana Perpetual Futures trading via Drift.
"""

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from .logger import get_logger

logger = get_logger(__name__)


class DriftClient:
    """
    Client for Drift Protocol (Solana Perps).
    Wraps driftpy SDK for high-level trading operations.
    """

    def __init__(self, rpc_url: Optional[str] = None):
        from .config import get_settings

        settings = get_settings()
        self.rpc_url = rpc_url or settings.solana_rpc_url

        # Use Drift-specific private key if available, fallback to general SOLANA_PRIVATE_KEY
        self.private_key = (
            os.getenv("DRIFT_PRIVATE_KEY") or
            os.getenv("DRIFT_SOLANA_PRIVATE_KEY") or
            settings.solana_private_key
        )

        # Expected Drift wallet address for verification
        self.expected_wallet = "B1UUWzWr9hWYfUE2xLEDVpyWzWWNWcTPv7Ea2j6guEZD"

        self.subaccount_id = int(os.getenv("DRIFT_SUBACCOUNT_ID", "0"))

        self.drift_user = None
        self.connection = None
        self.kp = None
        self.is_initialized = False

        # Check for optional dependency
        try:
            import driftpy

            self.has_driftpy = True
        except ImportError:
            self.has_driftpy = False
            logger.warning("DriftPy not installed. Drift client will be in mock mode.")

        if self.private_key:
            logger.info("Drift Client: Drift wallet private key loaded (redacted).")
        else:
            logger.warning("Drift Client: DRIFT_PRIVATE_KEY missing. Read-only mode.")

    async def initialize(self):
        """Async init of Drift SDK/User."""
        logger.info(f"🔍 [DRIFT INIT] Starting initialization... has_driftpy={self.has_driftpy}, has_private_key={bool(self.private_key)}")

        if not self.has_driftpy:
            logger.warning("❌ DriftClient: Skipping init - driftpy not installed")
            self.is_initialized = False
            return

        if not self.private_key:
            logger.warning("❌ DriftClient: Skipping init - SOLANA_PRIVATE_KEY missing")
            self.is_initialized = False
            return

        try:
            logger.info(f"Initializing Drift Protocol Client (RPC: {self.rpc_url})...")

            # Imports inside method to avoid crash if missing
            import base58
            from driftpy.account_subscription_config import AccountSubscriptionConfig
            from driftpy.drift_client import DriftClient as SDKDriftClient
            from solana.rpc.async_api import AsyncClient
            from solders.keypair import Keypair
            from solders.pubkey import Pubkey

            # Setup Connection
            self.connection = AsyncClient(self.rpc_url)

            # Setup Keypair
            # Handle both base58 string and raw bytes (list of ints)
            try:
                clean_key = self.private_key.strip()
                if "[" in clean_key:
                    import json

                    raw_key = json.loads(clean_key)
                    if len(raw_key) != 64:
                        raise ValueError(f"Invalid key length: {len(raw_key)} (expected 64)")
                    self.kp = Keypair.from_bytes(bytes(raw_key))
                else:
                    self.kp = Keypair.from_base58_string(clean_key)
            except Exception as k_err:
                logger.error(f"Failed to load keypair: {k_err}")
                raise k_err

            # Initialize SDK Client
            self.sdk_client = SDKDriftClient(
                self.connection,
                self.kp,
                env="mainnet",
                account_subscription=AccountSubscriptionConfig("websocket"),
            )

            logger.info("🔄 [DRIFT INIT] Subscribing to Drift SDK...")
            await self.sdk_client.subscribe()
            logger.info("🔄 [DRIFT INIT] Getting user...")
            self.drift_user = self.sdk_client.get_user(self.subaccount_id)
            # User subscription handling might vary by SDK version,
            # simplified here assuming client subscription covers it or it's fetched on demand

            self.is_initialized = True

            # Verify wallet address
            actual_wallet = str(self.kp.pubkey())
            logger.info(f"✅ [DRIFT INIT] Drift Client Initialized Successfully!")
            logger.info(f"🔑 Drift Wallet Address: {actual_wallet}")

            if actual_wallet == self.expected_wallet:
                logger.info(f"✅ Wallet verification PASSED - Using correct Drift account")
            else:
                logger.warning(f"⚠️ Wallet mismatch detected!")
                logger.warning(f"   Expected: {self.expected_wallet}")
                logger.warning(f"   Actual:   {actual_wallet}")
                logger.warning(f"   This may indicate wrong private key is being used")

        except Exception as e:
            logger.error(f"❌ Failed to initialize Drift Client: {e}")
            self.is_initialized = False

    async def get_perp_market(self, symbol: str = "SOL-PERP"):
        """Get market info, funding rates, open interest."""
        # Simple implementation for now - extend with SDK calls if needed
        price = 0.0
        try:
            # Fetch Real Price from CoinGecko (Backup source) with timeout
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.coingecko.com/api/v3/simple/price",
                    params={"ids": "solana", "vs_currencies": "usd"},
                )
                data = resp.json()
                price = float(data.get("solana", {}).get("usd", 0))
        except Exception as e:
            logger.debug(f"CoinGecko price fetch failed: {e}. Using fallback.")
            price = 0.0

        return {
            "symbol": symbol,
            "oracle_price": price,
            "funding_rate_24h": 0.0012,  # Mocked
            "open_interest": 1000000,
        }

    async def get_total_equity(self) -> float:
        """Get total equity in USD (SOL Balance + Perp PnL Stubs)."""

        # 1. Try fetching real SOL balance from RPC
        real_sol_equity = 0.0
        if self.connection and self.kp:
            try:
                # Use solders/solana to fetch balance
                # Note: raw async client call needed
                from solders.pubkey import Pubkey

                resp = await self.connection.get_balance(self.kp.pubkey())
                lamports = resp.value
                sol_balance = lamports / 1e9

                # Get Price Stub or Real
                # reusing mocked price logic from earlier or fetch fresh
                market_info = await self.get_perp_market("SOL-PERP")
                price = market_info.get("oracle_price", 150.0)

                real_sol_equity = sol_balance * price
                logger.info(
                    f"DriftClient: Real SOL Balance: {sol_balance:.4f} (~${real_sol_equity:.2f})"
                )
            except Exception as e:
                logger.warning(f"DriftClient: Failed to fetch real SOL balance: {e}")

        if not self.is_initialized or not self.drift_user:
            return max(real_sol_equity, 1500.0)  # Return real if found, else stub

        try:
            # Using SDK to get spot + perp value
            # This is pseudo-code for SDK usage, adjusting to likely API
            net_asset_value = self.drift_user.get_net_asset_value()
            return (
                float(net_asset_value) / 1e6
            )  # Convert based on precision (usually 6 decimals for USDC)
        except Exception:
            return max(real_sol_equity, 1500.0)

    async def get_position(self, symbol: str) -> Dict[str, Any]:
        """Get current position for symbol."""
        if not self.is_initialized or not self.drift_user:
            return {}

        try:
            # Map symbol string to market index (e.g. SOL-PERP -> 0)
            # Need market map, for now stubbed or assuming checking all positions
            positions = await self.drift_user.get_perp_positions()
            for p in positions:
                # Logic to match p.market_index to symbol would go here
                pass
            return {"symbol": symbol, "amount": 0.0, "entry_price": 0.0, "unrealized_pnl": 0.0}
        except Exception as e:
            logger.error(f"Drift get_position error: {e}")
            return {}

    async def place_perp_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        order_type: str = "market",
        price: Optional[float] = None,
    ):
        """Place a perp order on Drift using Real SDK."""
        if not self.is_initialized:
            logger.warning("Drift not initialized. Simulating order.")
            return {
                "tx_sig": "sim_drift_tx_uninit",
                "status": "simulated",
                "error": "Not initialized",
            }

        try:
            from driftpy.math.conversion import to_precision
            from driftpy.types import OrderParams, OrderType, PositionDirection

            # Map side to PositionDirection
            direction = (
                PositionDirection.Long() if side.upper() == "BUY" else PositionDirection.Short()
            )

            # Map symbol to Market Index
            # TODO: Robust market lookup. For now, hardcoding common pairs or defaulting to SOL-PERP (0)
            market_index = 0  # Default SOL-PERP
            if "SOL" in symbol:
                market_index = 0
            elif "BTC" in symbol:
                market_index = 1
            elif "ETH" in symbol:
                market_index = 2

            # Convert amount to Drift precision (base precision usually 1e9 for SOL)
            # This requires knowing the base scale for each market.
            # For Safety in this v2.2.10 update, we will wrap this in a try/catch specifically for SDK call

            # Standard params
            params = OrderParams(
                order_type=OrderType.Market(),
                market_type=None,  # Defaults to Perp in some versions, check SDK
                direction=direction,
                base_asset_amount=int(
                    amount * 1e9
                ),  # Assuming 9 decimals for safety on SOL, logic needs verification per market
                market_index=market_index,
            )

            logger.info(f"🌊 Drift Sending Order: {side} {amount} {symbol} (Idx: {market_index})")

            # Execute
            tx_sig = await self.sdk_client.place_perp_order(params)

            logger.info(f"✅ Drift Order Sent! Sig: {tx_sig}")

            return {
                "tx_sig": str(tx_sig),
                "status": "filled",  # Market orders are instant typically
                "market_index": market_index,
            }

        except Exception as e:
            logger.error(f"❌ Drift place_order failed: {e}")
            # Fallback to simulated response if real fails, to prevent crash loop, but mark error
            return {"tx_sig": None, "status": "failed", "error": str(e)}

    async def open_perp_position(
        self,
        market: str,
        direction: str,
        size: float,
        leverage: float = 2.0,
        limit_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Open a perpetual position on Drift.

        Args:
            market: Market symbol (e.g., "SOL-PERP", "BTC-PERP", "ETH-PERP")
            direction: "long" or "short"
            size: Position size in base asset (e.g., 1.5 SOL)
            leverage: Leverage multiplier (1x-10x recommended, max 20x)
            limit_price: Optional limit price for entry (None = market order)
            stop_loss: Optional stop-loss price
            take_profit: Optional take-profit price

        Returns:
            Dict with transaction signature, status, and position details
        """
        if not self.is_initialized:
            logger.warning("Drift not initialized. Cannot open position.")
            return {
                "success": False,
                "error": "Drift client not initialized",
            }

        try:
            from driftpy.types import OrderParams, OrderType, PositionDirection, MarketType

            # Map market to index
            market_index = self._get_market_index(market)
            if market_index is None:
                return {"success": False, "error": f"Unknown market: {market}"}

            # Map direction
            pos_direction = (
                PositionDirection.Long()
                if direction.lower() == "long"
                else PositionDirection.Short()
            )

            # Convert size to Drift precision (9 decimals for most markets)
            base_asset_amount = int(size * 1e9)

            # Determine order type
            order_type_enum = (
                OrderType.Limit() if limit_price else OrderType.Market()
            )

            # Convert limit price to Drift precision (6 decimals for USDC quote)
            price_param = int(limit_price * 1e6) if limit_price else 0

            # Create order params
            params = OrderParams(
                order_type=order_type_enum,
                market_type=MarketType.Perp(),
                direction=pos_direction,
                base_asset_amount=base_asset_amount,
                market_index=market_index,
                price=price_param if limit_price else 0,
            )

            logger.info(
                f"🚀 Opening {direction.upper()} position: {size} {market} @ {leverage}x leverage"
            )

            # Place order
            tx_sig = await self.sdk_client.place_perp_order(params)

            logger.info(f"✅ Position opened! Tx: {tx_sig}")

            result = {
                "success": True,
                "tx_sig": str(tx_sig),
                "market": market,
                "direction": direction,
                "size": size,
                "leverage": leverage,
                "entry_price": limit_price or "market",
            }

            # Place stop-loss if specified
            if stop_loss:
                await self._place_stop_loss(market, direction, size, stop_loss)
                result["stop_loss"] = stop_loss

            # Place take-profit if specified
            if take_profit:
                await self._place_take_profit(market, direction, size, take_profit)
                result["take_profit"] = take_profit

            return result

        except Exception as e:
            logger.error(f"❌ Failed to open position: {e}")
            return {"success": False, "error": str(e)}

    async def close_perp_position(
        self,
        market: str,
        size: Optional[float] = None,
        limit_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Close a perpetual position on Drift.

        Args:
            market: Market symbol (e.g., "SOL-PERP")
            size: Size to close (None = close entire position)
            limit_price: Optional limit price for exit (None = market order)

        Returns:
            Dict with transaction signature and P&L
        """
        if not self.is_initialized:
            logger.warning("Drift not initialized. Cannot close position.")
            return {"success": False, "error": "Drift client not initialized"}

        try:
            from driftpy.types import OrderParams, OrderType, PositionDirection, MarketType

            # Get current position
            current_position = await self.get_position(market)
            if not current_position or current_position.get("amount", 0) == 0:
                return {
                    "success": False,
                    "error": f"No open position in {market}",
                }

            # Determine size to close
            position_size = abs(current_position["amount"])
            close_size = size if size else position_size

            # Determine direction (opposite of current position)
            current_side = current_position.get("side", "long")
            close_direction = (
                PositionDirection.Short()
                if current_side == "long"
                else PositionDirection.Long()
            )

            # Market index
            market_index = self._get_market_index(market)

            # Order params
            order_type_enum = (
                OrderType.Limit() if limit_price else OrderType.Market()
            )
            price_param = int(limit_price * 1e6) if limit_price else 0

            params = OrderParams(
                order_type=order_type_enum,
                market_type=MarketType.Perp(),
                direction=close_direction,
                base_asset_amount=int(close_size * 1e9),
                market_index=market_index,
                price=price_param if limit_price else 0,
                reduce_only=True,  # Important: only reduce existing position
            )

            logger.info(f"🔒 Closing position: {close_size} {market}")

            # Place closing order
            tx_sig = await self.sdk_client.place_perp_order(params)

            logger.info(f"✅ Position closed! Tx: {tx_sig}")

            # Calculate P&L
            entry_price = current_position.get("entry_price", 0)
            unrealized_pnl = current_position.get("unrealized_pnl", 0)

            return {
                "success": True,
                "tx_sig": str(tx_sig),
                "market": market,
                "closed_size": close_size,
                "entry_price": entry_price,
                "pnl": unrealized_pnl,
            }

        except Exception as e:
            logger.error(f"❌ Failed to close position: {e}")
            return {"success": False, "error": str(e)}

    async def get_all_perp_positions(self) -> List[Dict[str, Any]]:
        """
        Get all open perpetual positions.

        Returns:
            List of position dicts with market, size, entry_price, pnl, etc.
        """
        if not self.is_initialized or not self.drift_user:
            return []

        try:
            positions = []

            # Get all perp positions from Drift user
            user_positions = self.drift_user.get_perp_positions()

            for pos in user_positions:
                # Skip empty positions
                if pos.base_asset_amount == 0:
                    continue

                # Get market info
                market_account = self.sdk_client.get_perp_market_account(pos.market_index)
                symbol = self._get_market_symbol(pos.market_index)

                # Calculate position details
                base_amount = pos.base_asset_amount / 1e9
                entry_price = pos.quote_entry_amount / pos.base_asset_amount if pos.base_asset_amount != 0 else 0

                # Get current price from oracle
                oracle_price = self.sdk_client.get_oracle_price_data_and_slot(market_account.amm.oracle).data.price / 1e6

                # Calculate unrealized P&L
                if base_amount > 0:  # Long position
                    unrealized_pnl = (oracle_price - entry_price) * abs(base_amount)
                else:  # Short position
                    unrealized_pnl = (entry_price - oracle_price) * abs(base_amount)

                positions.append({
                    "market": symbol,
                    "market_index": pos.market_index,
                    "side": "long" if base_amount > 0 else "short",
                    "size": abs(base_amount),
                    "entry_price": entry_price,
                    "current_price": oracle_price,
                    "unrealized_pnl": unrealized_pnl,
                    "liquidation_price": self._calculate_liquidation_price(pos, market_account),
                })

            return positions

        except Exception as e:
            logger.error(f"❌ Error getting positions: {e}")
            return []

    async def modify_position_leverage(
        self,
        market: str,
        new_leverage: float,
    ) -> Dict[str, Any]:
        """
        Modify leverage for a position (by adjusting collateral).

        Args:
            market: Market symbol
            new_leverage: New leverage multiplier (1x-10x recommended)

        Returns:
            Dict with success status
        """
        if not self.is_initialized:
            return {"success": False, "error": "Not initialized"}

        try:
            # Note: Drift doesn't have direct leverage adjustment
            # Leverage is adjusted by adding/removing collateral
            # This would require deposit/withdraw operations

            logger.warning(
                f"Leverage modification not directly supported. "
                f"Use deposit/withdraw collateral for {market}"
            )

            return {
                "success": False,
                "error": "Direct leverage modification not supported. Adjust collateral instead.",
            }

        except Exception as e:
            logger.error(f"❌ Leverage modification error: {e}")
            return {"success": False, "error": str(e)}

    def _get_market_index(self, symbol: str) -> Optional[int]:
        """Map market symbol to Drift market index."""
        market_map = {
            "SOL-PERP": 0,
            "BTC-PERP": 1,
            "ETH-PERP": 2,
            "APT-PERP": 3,
            "ARB-PERP": 4,
            "AVAX-PERP": 5,
            "BNB-PERP": 6,
            "DOGE-PERP": 7,
            "JTO-PERP": 8,
            "MATIC-PERP": 9,
            "OP-PERP": 10,
            "PYTH-PERP": 11,
            "SUI-PERP": 12,
            "WIF-PERP": 13,
            "JUP-PERP": 14,
        }
        return market_map.get(symbol.upper())

    def _get_market_symbol(self, market_index: int) -> str:
        """Map Drift market index to symbol."""
        symbol_map = {
            0: "SOL-PERP",
            1: "BTC-PERP",
            2: "ETH-PERP",
            3: "APT-PERP",
            4: "ARB-PERP",
            5: "AVAX-PERP",
            6: "BNB-PERP",
            7: "DOGE-PERP",
            8: "JTO-PERP",
            9: "MATIC-PERP",
            10: "OP-PERP",
            11: "PYTH-PERP",
            12: "SUI-PERP",
            13: "WIF-PERP",
            14: "JUP-PERP",
        }
        return symbol_map.get(market_index, f"UNKNOWN-{market_index}")

    def _calculate_liquidation_price(self, position, market_account) -> float:
        """Calculate approximate liquidation price for a position."""
        try:
            # Simplified liquidation calculation
            # Actual calculation is more complex and depends on collateral
            maintenance_margin_ratio = market_account.margin_ratio_maintenance / 10000
            entry_price = position.quote_entry_amount / position.base_asset_amount if position.base_asset_amount != 0 else 0

            if position.base_asset_amount > 0:  # Long
                liq_price = entry_price * (1 - maintenance_margin_ratio)
            else:  # Short
                liq_price = entry_price * (1 + maintenance_margin_ratio)

            return liq_price / 1e6
        except Exception:
            return 0.0

    async def _place_stop_loss(
        self,
        market: str,
        direction: str,
        size: float,
        stop_price: float,
    ):
        """Place a stop-loss order."""
        try:
            from driftpy.types import OrderParams, OrderType, PositionDirection, MarketType, OrderTriggerCondition

            market_index = self._get_market_index(market)

            # Stop-loss direction is opposite of position
            sl_direction = (
                PositionDirection.Short()
                if direction.lower() == "long"
                else PositionDirection.Long()
            )

            params = OrderParams(
                order_type=OrderType.TriggerMarket(),
                market_type=MarketType.Perp(),
                direction=sl_direction,
                base_asset_amount=int(size * 1e9),
                market_index=market_index,
                trigger_price=int(stop_price * 1e6),
                trigger_condition=(
                    OrderTriggerCondition.Below()
                    if direction.lower() == "long"
                    else OrderTriggerCondition.Above()
                ),
                reduce_only=True,
            )

            tx_sig = await self.sdk_client.place_perp_order(params)
            logger.info(f"🛡️ Stop-loss placed @ ${stop_price:.4f} | Tx: {tx_sig}")

        except Exception as e:
            logger.error(f"❌ Failed to place stop-loss: {e}")

    async def _place_take_profit(
        self,
        market: str,
        direction: str,
        size: float,
        tp_price: float,
    ):
        """Place a take-profit order."""
        try:
            from driftpy.types import OrderParams, OrderType, PositionDirection, MarketType, OrderTriggerCondition

            market_index = self._get_market_index(market)

            # Take-profit direction is opposite of position
            tp_direction = (
                PositionDirection.Short()
                if direction.lower() == "long"
                else PositionDirection.Long()
            )

            params = OrderParams(
                order_type=OrderType.TriggerMarket(),
                market_type=MarketType.Perp(),
                direction=tp_direction,
                base_asset_amount=int(size * 1e9),
                market_index=market_index,
                trigger_price=int(tp_price * 1e6),
                trigger_condition=(
                    OrderTriggerCondition.Above()
                    if direction.lower() == "long"
                    else OrderTriggerCondition.Below()
                ),
                reduce_only=True,
            )

            tx_sig = await self.sdk_client.place_perp_order(params)
            logger.info(f"🎯 Take-profit placed @ ${tp_price:.4f} | Tx: {tx_sig}")

        except Exception as e:
            logger.error(f"❌ Failed to place take-profit: {e}")

    async def close(self):
        if self.sdk_client:
            await self.sdk_client.unsubscribe()
        if self.connection:
            await self.connection.close()

    async def get_token_price(self, symbol: str) -> float:
        """
        Get current price for a token.
        Used by ArbitrageScanner for cross-platform price comparison.

        Args:
            symbol: Symbol string (e.g. 'SOL-USD', 'SOL-PERP')

        Returns:
            Current price in USD or 0.0 on error
        """
        try:
            # Extract base asset from symbol
            base = symbol.split("-")[0].upper()

            # Map to CoinGecko IDs
            coingecko_map = {
                "SOL": "solana",
                "BTC": "bitcoin",
                "ETH": "ethereum",
            }

            cg_id = coingecko_map.get(base)
            if not cg_id:
                logger.debug(f"No CoinGecko mapping for {base}")
                return 0.0

            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    "https://api.coingecko.com/api/v3/simple/price",
                    params={"ids": cg_id, "vs_currencies": "usd"},
                )
                data = resp.json()
                price = float(data.get(cg_id, {}).get("usd", 0))
                return price
        except Exception as e:
            logger.debug(f"Drift get_token_price error for {symbol}: {e}")
            return 0.0


# Singleton
_drift_client = None


def get_drift_client() -> DriftClient:
    global _drift_client
    if not _drift_client:
        _drift_client = DriftClient()
    return _drift_client
