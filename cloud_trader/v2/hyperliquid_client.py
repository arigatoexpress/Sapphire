"""
Hyperliquid Trading Client - Using Official SDK
================================================
Wraps the official hyperliquid-python-sdk for proper EIP-712 signing.

Author: Sapphire V2 Architecture Team
Version: 2.3.0
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Try to import official SDK, fallback gracefully if not available
try:
    from hyperliquid.exchange import Exchange
    from hyperliquid.info import Info
    from hyperliquid.utils.signing import get_timestamp_ms
    HYPERLIQUID_SDK_AVAILABLE = True
    logger.info("✅ Hyperliquid official SDK loaded")
except ImportError:
    HYPERLIQUID_SDK_AVAILABLE = False
    logger.warning("⚠️ Hyperliquid SDK not available - install hyperliquid-python-sdk")


@dataclass
class HyperliquidPosition:
    """Represents a Hyperliquid position."""
    symbol: str
    size: float
    entry_price: float
    mark_price: float
    liquidation_price: Optional[float]
    unrealized_pnl: float
    realized_pnl: float
    leverage: float
    margin_used: float
    side: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "size": self.size,
            "entry_price": self.entry_price,
            "mark_price": self.mark_price,
            "liquidation_price": self.liquidation_price,
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "leverage": self.leverage,
            "margin_used": self.margin_used,
            "side": self.side,
        }


@dataclass 
class HyperliquidOrder:
    """Represents a Hyperliquid order result."""
    order_id: str
    client_order_id: Optional[str]
    symbol: str
    side: str
    order_type: str
    price: Optional[float]
    quantity: float
    filled_quantity: float
    status: str
    created_at: datetime

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "price": self.price,
            "quantity": self.quantity,
            "filled_quantity": self.filled_quantity,
            "status": self.status,
        }


class HyperliquidClient:
    """
    Hyperliquid client using official SDK for proper EIP-712 signing.
    
    The SDK handles all the complex signature generation internally,
    ensuring trades execute correctly on Hyperliquid L1.
    """
    
    def __init__(
        self,
        private_key: str,
        wallet_address: str,
        testnet: bool = False,
    ):
        """Initialize Hyperliquid client with official SDK."""
        self._private_key = private_key
        self._wallet_address = wallet_address
        self._testnet = testnet
        
        self._exchange: Optional[Exchange] = None
        self._info: Optional[Info] = None
        self._initialized = False
        
        # Cache
        self._positions: dict[str, HyperliquidPosition] = {}
        self._market_info: dict[str, dict] = {}
        
    @property
    def is_initialized(self) -> bool:
        return self._initialized
    
    async def initialize(self) -> bool:
        """Initialize the Hyperliquid SDK clients."""
        if self._initialized:
            return True
            
        if not HYPERLIQUID_SDK_AVAILABLE:
            logger.error("❌ Cannot initialize - Hyperliquid SDK not installed")
            return False
        
        logger.info("🔷 [Hyperliquid] Initializing with official SDK...")
        
        try:
            # Initialize SDK components
            base_url = "https://api.hyperliquid-testnet.xyz" if self._testnet else "https://api.hyperliquid.xyz"
            
            # Info client for readonly operations
            self._info = Info(base_url, skip_ws=True)
            
            # Create wallet Account object from private key
            # The SDK expects an eth_account.Account object, not a raw key string
            from eth_account import Account
            wallet = Account.from_key(self._private_key)
            
            # Exchange client for trading (handles EIP-712 signing)
            self._exchange = Exchange(
                wallet=wallet,
                base_url=base_url,
                account_address=self._wallet_address,
            )
            
            # Load market metadata
            await self._load_market_info()
            
            # Load initial positions
            await self.get_positions()
            
            self._initialized = True
            logger.info(f"✅ [Hyperliquid] SDK client initialized | Testnet: {self._testnet}")
            return True
            
        except Exception as e:
            logger.error(f"❌ [Hyperliquid] SDK initialization failed: {e}")
            return False
    
    async def _load_market_info(self) -> None:
        """Load market metadata from API."""
        try:
            if not self._info:
                return
                
            # Run in executor since SDK is sync
            loop = asyncio.get_event_loop()
            meta = await loop.run_in_executor(None, self._info.meta)
            
            if meta and "universe" in meta:
                for idx, market in enumerate(meta["universe"]):
                    symbol = market.get("name", "")
                    self._market_info[symbol] = {
                        "asset_id": idx,
                        "sz_decimals": market.get("szDecimals", 4),
                        "max_leverage": market.get("maxLeverage", 50),
                    }
                    
                logger.debug(f"📊 [Hyperliquid] Loaded {len(self._market_info)} markets")
                
        except Exception as e:
            logger.warning(f"⚠️ [Hyperliquid] Failed to load market info: {e}")
    
    async def get_positions(self) -> list[HyperliquidPosition]:
        """Get all open positions."""
        positions = []
        
        if not self._info:
            return positions
            
        try:
            loop = asyncio.get_event_loop()
            user_state = await loop.run_in_executor(
                None, 
                self._info.user_state, 
                self._wallet_address
            )
            
            if user_state and "assetPositions" in user_state:
                for pos_data in user_state["assetPositions"]:
                    pos = pos_data.get("position", {})
                    size = float(pos.get("szi", 0))
                    if size != 0:
                        position = HyperliquidPosition(
                            symbol=pos.get("coin", ""),
                            size=abs(size),
                            entry_price=float(pos.get("entryPx", 0)),
                            mark_price=float(pos.get("positionValue", 0)) / abs(size) if size else 0,
                            liquidation_price=float(pos.get("liquidationPx")) if pos.get("liquidationPx") else None,
                            unrealized_pnl=float(pos.get("unrealizedPnl", 0)),
                            realized_pnl=float(pos.get("returnOnEquity", 0)),
                            leverage=float(pos.get("leverage", {}).get("value", 1)),
                            margin_used=float(pos.get("marginUsed", 0)),
                            side="long" if size > 0 else "short",
                        )
                        positions.append(position)
                        self._positions[position.symbol] = position
                        
            logger.debug(f"📊 [Hyperliquid] Loaded {len(positions)} positions")
            
        except Exception as e:
            logger.error(f"❌ [Hyperliquid] Failed to get positions: {e}")
            
        return positions
    
    async def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        reduce_only: bool = False,
        **kwargs,
    ) -> dict:
        """
        Place an order using official SDK.
        
        The SDK handles EIP-712 signing internally.
        """
        if not self._initialized:
            await self.initialize()
            
        if not self._exchange:
            return {"status": "error", "error": "Exchange not initialized"}
        
        # Normalize symbol (e.g., "BTC-USDC" -> "BTC")
        coin = symbol.upper().replace("_", "-").replace("-PERP", "").replace("-USDC", "").replace("-USD", "")
        
        # Get market info
        market = self._market_info.get(coin, {})
        sz_decimals = market.get("sz_decimals", 4)
        
        # Round quantity
        quantity = round(quantity, sz_decimals)
        
        is_buy = side.upper() == "BUY"
        
        logger.info(
            f"📤 [Hyperliquid] Placing {order_type} {side} order | "
            f"Coin: {coin} | Qty: {quantity}"
        )
        
        try:
            loop = asyncio.get_event_loop()
            
            if order_type.upper() == "MARKET":
                # Market order - SDK handles slippage internally
                # SDK docs: market_open(name, is_buy, sz, px=None, slippage=0.05, cloid=None)
                result = await loop.run_in_executor(
                    None,
                    lambda: self._exchange.market_open(
                        name=coin,  # SDK uses 'name' not 'coin'
                        is_buy=is_buy,
                        sz=quantity,
                        slippage=0.05,  # 5% slippage
                    )
                )
            else:
                # Limit order
                if not price:
                    return {"status": "error", "error": "Price required for limit orders"}
                    
                result = await loop.run_in_executor(
                    None,
                    lambda: self._exchange.order(
                        name=coin,  # SDK uses 'name' not 'coin'
                        is_buy=is_buy,
                        sz=quantity,
                        limit_px=price,
                        order_type={"limit": {"tif": "Gtc"}},
                        reduce_only=reduce_only,
                    )
                )
            
            if result and result.get("status") == "ok":
                statuses = result.get("response", {}).get("data", {}).get("statuses", [])
                if statuses:
                    status = statuses[0]
                    if "filled" in status:
                        filled = status["filled"]
                        logger.info(
                            f"✅ [Hyperliquid] Order FILLED | "
                            f"Coin: {coin} | Avg Price: ${filled.get('avgPx', 'N/A')}"
                        )
                        return {"status": "ok", "filled": True, "data": filled}
                    elif "resting" in status:
                        logger.info(f"📋 [Hyperliquid] Order RESTING | Coin: {coin}")
                        return {"status": "ok", "resting": True, "data": status["resting"]}
                    elif "error" in status:
                        logger.error(f"❌ [Hyperliquid] Order error: {status['error']}")
                        return {"status": "error", "error": status["error"]}
                        
                return {"status": "ok", "response": result}
            else:
                error = result.get("response", {}).get("data", {}).get("statuses", [{}])[0].get("error", "Unknown")
                logger.error(f"❌ [Hyperliquid] Order failed: {error}")
                return {"status": "error", "error": error}
                
        except Exception as e:
            logger.error(f"❌ [Hyperliquid] Order exception: {e}")
            return {"status": "error", "error": str(e)}

    async def place_trigger_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        trigger_price: float,
        is_tp: bool = True,
        reduce_only: bool = True,
    ) -> dict:
        """
        Place a trigger order (Take Profit or Stop Loss).
        
        Args:
            symbol: Trading pair
            side: Order side ("BUY" or "SELL")
            quantity: Order size
            trigger_price: Trigger price
            is_tp: True for Take Profit, False for Stop Loss
            reduce_only: Should be True for TP/SL closing orders
        """
        if not self._initialized:
            await self.initialize()

        if not self._exchange:
            return {"status": "error", "error": "Exchange not initialized"}
            
        # Normalize symbol
        coin = symbol.upper().replace("_", "-").replace("-PERP", "").replace("-USDC", "").replace("-USD", "")
        
        # Get market info for precision
        market = self._market_info.get(coin, {})
        sz_decimals = market.get("sz_decimals", 4)
        quantity = round(quantity, sz_decimals)
        
        is_buy = side.upper() == "BUY"
        trigger_type = "tp" if is_tp else "sl"
        
        logger.info(
            f"📤 [Hyperliquid] Placing {trigger_type.upper()} {side} trigger | "
            f"Coin: {coin} | Qty: {quantity} | Price: ${trigger_price}"
        )
        
        try:
            loop = asyncio.get_event_loop()
            
            # Use SDK's order method with trigger configuration
            result = await loop.run_in_executor(
                None,
                lambda: self._exchange.order(
                    name=coin,
                    is_buy=is_buy,
                    sz=quantity,
                    limit_px=trigger_price,  # Trigger orders use limit_px as the price
                    order_type={
                        "trigger": {
                            "triggerPx": trigger_price,
                            "isMarket": True,  # Usually market order when triggered
                            "tpsl": trigger_type
                        }
                    },
                    reduce_only=reduce_only,
                )
            )
            
            if result and result.get("status") == "ok":
                statuses = result.get("response", {}).get("data", {}).get("statuses", [])
                if statuses:
                    status = statuses[0]
                    if "resting" in status:
                        logger.info(f"✅ [Hyperliquid] {trigger_type.upper()} Set | Coin: {coin}")
                        return {"status": "ok", "resting": True, "data": status["resting"]}
                    elif "error" in status:
                        logger.error(f"❌ [Hyperliquid] {trigger_type.upper()} error: {status['error']}")
                        return {"status": "error", "error": status["error"]}
                        
                return {"status": "ok", "response": result}
            else:
                error = result.get("response", {}).get("data", {}).get("statuses", [{}])[0].get("error", "Unknown")
                logger.error(f"❌ [Hyperliquid] {trigger_type.upper()} failed: {error}")
                return {"status": "error", "error": error}
                
        except Exception as e:
            logger.error(f"❌ [Hyperliquid] {trigger_type.upper()} exception: {e}")
            return {"status": "error", "error": str(e)}
    
    async def get_ticker(self, symbol: str) -> dict:
        """Get current price for a symbol."""
        if not self._info:
            return {}
            
        coin = symbol.upper().replace("_", "-").replace("-PERP", "").replace("-USDC", "")
        
        try:
            loop = asyncio.get_event_loop()
            all_mids = await loop.run_in_executor(None, self._info.all_mids)
            
            if all_mids and coin in all_mids:
                return {
                    "symbol": coin,
                    "mid_price": float(all_mids[coin]),
                    "timestamp": datetime.utcnow().isoformat(),
                }
                
        except Exception as e:
            logger.error(f"❌ [Hyperliquid] Failed to get ticker: {e}")
            
        return {}
    
    async def get_account_value(self) -> float:
        """Get total account value."""
        if not self._info:
            return 0.0
            
        try:
            loop = asyncio.get_event_loop()
            user_state = await loop.run_in_executor(
                None, 
                self._info.user_state, 
                self._wallet_address
            )
            
            if user_state:
                return float(user_state.get("marginSummary", {}).get("accountValue", 0))
                
        except Exception as e:
            logger.error(f"❌ [Hyperliquid] Failed to get account value: {e}")
            
        return 0.0
    
    async def close(self) -> None:
        """Cleanup client resources."""
        self._initialized = False
        self._exchange = None
        self._info = None
        logger.info("🔷 [Hyperliquid] Client closed")
    
    def get_status(self) -> dict:
        """Get client status."""
        return {
            "initialized": self._initialized,
            "sdk_available": HYPERLIQUID_SDK_AVAILABLE,
            "testnet": self._testnet,
            "wallet": self._wallet_address[:10] + "..." if self._wallet_address else None,
            "markets_loaded": len(self._market_info),
            "positions": len(self._positions),
        }
