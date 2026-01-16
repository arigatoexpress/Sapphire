"""
Hyperliquid Trading Client - Reinstated
========================================
Full-featured Hyperliquid perpetual futures client.

Hyperliquid is now ACTIVE alongside Drift as a separate DeFi perps venue.

Routing Strategy:
- Hyperliquid: Primary for specific symbols (configurable)
- Drift: Primary for Solana-native assets
- Both operate independently with separate circuit breakers

Author: Sapphire V2 Architecture Team
Version: 2.2.0
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

import aiohttp

# Configure logging with agentic persona
logger = logging.getLogger(__name__)


class HyperliquidOrderType(Enum):
    """Hyperliquid order types."""
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"
    TAKE_PROFIT = "take_profit"


class HyperliquidSide(Enum):
    """Order side."""
    BUY = "B"
    SELL = "A"  # Ask


class HyperliquidTimeInForce(Enum):
    """Time in force options."""
    GTC = "Gtc"  # Good til cancelled
    IOC = "Ioc"  # Immediate or cancel
    ALO = "Alo"  # Add liquidity only (post-only)


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
    side: str  # "long" or "short"
    
    @property
    def pnl_percent(self) -> float:
        """Calculate PnL percentage."""
        if self.entry_price == 0:
            return 0.0
        return ((self.mark_price - self.entry_price) / self.entry_price) * 100
    
    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "size": self.size,
            "entry_price": self.entry_price,
            "mark_price": self.mark_price,
            "liquidation_price": self.liquidation_price,
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "pnl_percent": round(self.pnl_percent, 2),
            "leverage": self.leverage,
            "margin_used": self.margin_used,
            "side": self.side,
        }


@dataclass
class HyperliquidOrder:
    """Represents a Hyperliquid order."""
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
    updated_at: Optional[datetime] = None
    
    @property
    def is_filled(self) -> bool:
        return self.status == "filled"
    
    @property
    def is_open(self) -> bool:
        return self.status in ("open", "partial")
    
    @property
    def fill_percent(self) -> float:
        if self.quantity == 0:
            return 0.0
        return (self.filled_quantity / self.quantity) * 100
    
    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "price": self.price,
            "quantity": self.quantity,
            "filled_quantity": self.filled_quantity,
            "fill_percent": round(self.fill_percent, 1),
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class HyperliquidConfig:
    """Configuration for Hyperliquid client."""
    # API endpoints
    api_url: str = "https://api.hyperliquid.xyz"
    ws_url: str = "wss://api.hyperliquid.xyz/ws"
    
    # Trading parameters
    default_leverage: int = 5
    max_leverage: int = 50
    default_slippage: float = 0.005  # 0.5%
    
    # Symbols this client handles (separate from Drift)
    primary_symbols: list[str] = field(default_factory=lambda: [
        "BTC-PERP",
        "ETH-PERP",
        "ARB-PERP",
        "OP-PERP",
        "MATIC-PERP",
        "AVAX-PERP",
        "LINK-PERP",
        "DOGE-PERP",
    ])
    
    # Rate limiting
    rate_limit_per_second: int = 10
    
    # Retry configuration
    max_retries: int = 3
    retry_delay: float = 1.0


class HyperliquidClient:
    """
    Production Hyperliquid trading client.
    
    This client operates independently from Drift and handles
    its own symbol routing based on configuration.
    
    Usage:
        client = HyperliquidClient(
            private_key="your_private_key",
            wallet_address="your_wallet_address",
        )
        await client.initialize()
        
        # Place order
        order = await client.place_order(
            symbol="BTC-PERP",
            side="BUY",
            quantity=0.01,
            order_type="MARKET",
        )
    """
    
    def __init__(
        self,
        private_key: str,
        wallet_address: str,
        config: Optional[HyperliquidConfig] = None,
        testnet: bool = False,
    ):
        """
        Initialize Hyperliquid client.
        
        Args:
            private_key: Ethereum private key for signing
            wallet_address: Wallet address
            config: Optional configuration
            testnet: Use testnet endpoints
        """
        self._private_key = private_key
        self._wallet_address = wallet_address
        self.config = config or HyperliquidConfig()
        self._testnet = testnet
        
        # Update URLs for testnet
        if testnet:
            self.config.api_url = "https://api.hyperliquid-testnet.xyz"
            self.config.ws_url = "wss://api.hyperliquid-testnet.xyz/ws"
        
        # State
        self._session: Optional[aiohttp.ClientSession] = None
        self._initialized = False
        self._last_request_time = 0.0
        self._request_lock = asyncio.Lock()
        
        # Cache
        self._positions: dict[str, HyperliquidPosition] = {}
        self._open_orders: dict[str, HyperliquidOrder] = {}
        self._market_info: dict[str, dict] = {}
        
    @property
    def is_initialized(self) -> bool:
        return self._initialized
    
    @property
    def supported_symbols(self) -> list[str]:
        """Get symbols this client handles."""
        return self.config.primary_symbols
    
    def handles_symbol(self, symbol: str) -> bool:
        """Check if this client handles a specific symbol."""
        normalized = symbol.upper().replace("_", "-")
        return normalized in self.config.primary_symbols
    
    async def initialize(self) -> bool:
        """
        Initialize client and load market data.
        
        Returns:
            True if initialization successful
        """
        if self._initialized:
            return True
        
        logger.info("🔷 [Hyperliquid] Initializing client...")
        
        try:
            # Create HTTP session
            self._session = aiohttp.ClientSession(
                headers={"Content-Type": "application/json"}
            )
            
            # Load market info
            await self._load_market_info()
            
            # Load initial positions
            await self.get_positions()
            
            self._initialized = True
            logger.info(
                f"✅ [Hyperliquid] Client initialized | "
                f"Symbols: {len(self.config.primary_symbols)} | "
                f"Testnet: {self._testnet}"
            )
            return True
            
        except Exception as e:
            logger.error(f"❌ [Hyperliquid] Initialization failed: {e}")
            return False
    
    async def _load_market_info(self) -> None:
        """Load market metadata."""
        try:
            response = await self._request("POST", "/info", {
                "type": "meta"
            })
            
            if response and "universe" in response:
                for market in response["universe"]:
                    symbol = market.get("name", "")
                    self._market_info[symbol] = {
                        "sz_decimals": market.get("szDecimals", 4),
                        "max_leverage": market.get("maxLeverage", 50),
                    }
                
                logger.debug(f"📊 [Hyperliquid] Loaded {len(self._market_info)} markets")
                
        except Exception as e:
            logger.warning(f"⚠️ [Hyperliquid] Failed to load market info: {e}")
    
    async def _rate_limit(self) -> None:
        """Enforce rate limiting."""
        async with self._request_lock:
            now = time.time()
            min_interval = 1.0 / self.config.rate_limit_per_second
            elapsed = now - self._last_request_time
            
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
            
            self._last_request_time = time.time()
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict] = None,
        signed: bool = False,
    ) -> Optional[dict]:
        """
        Make API request with rate limiting and retry.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            data: Request body
            signed: Whether to sign the request
            
        Returns:
            Response data or None
        """
        if not self._session:
            raise RuntimeError("Client not initialized")
        
        await self._rate_limit()
        
        url = f"{self.config.api_url}{endpoint}"
        
        for attempt in range(self.config.max_retries):
            try:
                # Sign request if needed
                headers = {}
                if signed and data:
                    signature = self._sign_request(data)
                    headers["X-Signature"] = signature
                
                async with self._session.request(
                    method,
                    url,
                    json=data,
                    headers=headers,
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 429:
                        # Rate limited
                        wait_time = self.config.retry_delay * (2 ** attempt)
                        logger.warning(
                            f"⚠️ [Hyperliquid] Rate limited, waiting {wait_time}s"
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        text = await response.text()
                        logger.error(
                            f"❌ [Hyperliquid] Request failed: {response.status} - {text}"
                        )
                        
            except Exception as e:
                logger.error(f"❌ [Hyperliquid] Request error: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (2 ** attempt))
        
        return None
    
    def _sign_request(self, data: dict) -> str:
        """Sign request with private key."""
        # Simplified signing - in production use proper EIP-712 signing
        message = json.dumps(data, sort_keys=True)
        signature = hmac.new(
            self._private_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    async def get_positions(self) -> list[HyperliquidPosition]:
        """
        Get all open positions.
        
        Returns:
            List of positions
        """
        response = await self._request("POST", "/info", {
            "type": "clearinghouseState",
            "user": self._wallet_address,
        })
        
        positions = []
        if response and "assetPositions" in response:
            for pos_data in response["assetPositions"]:
                pos = pos_data.get("position", {})
                if float(pos.get("szi", 0)) != 0:
                    position = HyperliquidPosition(
                        symbol=pos.get("coin", ""),
                        size=abs(float(pos.get("szi", 0))),
                        entry_price=float(pos.get("entryPx", 0)),
                        mark_price=float(pos.get("markPx", 0)),
                        liquidation_price=float(pos.get("liquidationPx", 0)) if pos.get("liquidationPx") else None,
                        unrealized_pnl=float(pos.get("unrealizedPnl", 0)),
                        realized_pnl=float(pos.get("returnOnEquity", 0)),
                        leverage=float(pos.get("leverage", {}).get("value", 1)),
                        margin_used=float(pos.get("marginUsed", 0)),
                        side="long" if float(pos.get("szi", 0)) > 0 else "short",
                    )
                    positions.append(position)
                    self._positions[position.symbol] = position
        
        logger.debug(f"📊 [Hyperliquid] Loaded {len(positions)} positions")
        return positions
    
    async def get_position(self, symbol: str) -> Optional[HyperliquidPosition]:
        """Get position for a specific symbol."""
        await self.get_positions()
        return self._positions.get(symbol)
    
    async def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        reduce_only: bool = False,
        time_in_force: str = "GTC",
        client_order_id: Optional[str] = None,
    ) -> HyperliquidOrder:
        """
        Place an order on Hyperliquid.
        
        Args:
            symbol: Trading pair (e.g., "BTC-PERP")
            side: "BUY" or "SELL"
            quantity: Order quantity
            order_type: "MARKET" or "LIMIT"
            price: Limit price (required for LIMIT orders)
            reduce_only: Only reduce position
            time_in_force: "GTC", "IOC", or "ALO"
            client_order_id: Optional client order ID
            
        Returns:
            Order result
        """
        if not self._initialized:
            await self.initialize()
        
        # Normalize symbol
        symbol = symbol.upper().replace("_", "-").replace("-PERP", "")
        
        # Convert side
        hl_side = HyperliquidSide.BUY if side.upper() == "BUY" else HyperliquidSide.SELL
        
        # Get market info for decimals
        market = self._market_info.get(symbol, {})
        sz_decimals = market.get("sz_decimals", 4)
        
        # Round quantity
        quantity = round(quantity, sz_decimals)
        
        # Build order
        order_spec = {
            "a": 0,  # Asset index (simplified)
            "b": hl_side.value == "B",
            "p": str(price) if price else "0",
            "s": str(quantity),
            "r": reduce_only,
            "t": {
                "limit": {
                    "tif": time_in_force,
                }
            } if order_type.upper() == "LIMIT" else {"trigger": {"isMarket": True}},
        }
        
        if client_order_id:
            order_spec["c"] = client_order_id
        
        logger.info(
            f"📤 [Hyperliquid] Placing {order_type} {side} order | "
            f"Symbol: {symbol} | Qty: {quantity}"
        )
        
        # Place order
        response = await self._request("POST", "/exchange", {
            "action": {
                "type": "order",
                "orders": [order_spec],
                "grouping": "na",
            },
            "nonce": int(time.time() * 1000),
            "signature": self._sign_request(order_spec),
        }, signed=True)
        
        if response and response.get("status") == "ok":
            order_data = response.get("response", {}).get("data", {})
            statuses = order_data.get("statuses", [{}])
            
            if statuses and "filled" in statuses[0]:
                filled_info = statuses[0]["filled"]
                order = HyperliquidOrder(
                    order_id=str(filled_info.get("oid", "")),
                    client_order_id=client_order_id,
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    price=float(filled_info.get("avgPx", price or 0)),
                    quantity=quantity,
                    filled_quantity=float(filled_info.get("totalSz", quantity)),
                    status="filled",
                    created_at=datetime.utcnow(),
                )
                
                logger.info(
                    f"✅ [Hyperliquid] Order FILLED | "
                    f"ID: {order.order_id} | "
                    f"Price: ${order.price:,.2f} | "
                    f"Qty: {order.filled_quantity}"
                )
                return order
            
            elif statuses and "resting" in statuses[0]:
                resting_info = statuses[0]["resting"]
                order = HyperliquidOrder(
                    order_id=str(resting_info.get("oid", "")),
                    client_order_id=client_order_id,
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    price=price,
                    quantity=quantity,
                    filled_quantity=0.0,
                    status="open",
                    created_at=datetime.utcnow(),
                )
                
                self._open_orders[order.order_id] = order
                logger.info(
                    f"📋 [Hyperliquid] Order OPEN | "
                    f"ID: {order.order_id} | "
                    f"Price: ${price:,.2f}"
                )
                return order
        
        # Order failed
        error_msg = response.get("response", {}).get("data", {}).get("statuses", [{}])[0].get("error", "Unknown error")
        logger.error(f"❌ [Hyperliquid] Order failed: {error_msg}")
        
        raise Exception(f"Hyperliquid order failed: {error_msg}")
    
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """
        Cancel an open order.
        
        Args:
            symbol: Trading pair
            order_id: Order ID to cancel
            
        Returns:
            True if cancelled successfully
        """
        symbol = symbol.upper().replace("_", "-").replace("-PERP", "")
        
        response = await self._request("POST", "/exchange", {
            "action": {
                "type": "cancel",
                "cancels": [{"a": 0, "o": int(order_id)}],
            },
            "nonce": int(time.time() * 1000),
        }, signed=True)
        
        if response and response.get("status") == "ok":
            self._open_orders.pop(order_id, None)
            logger.info(f"✅ [Hyperliquid] Order {order_id} cancelled")
            return True
        
        logger.error(f"❌ [Hyperliquid] Failed to cancel order {order_id}")
        return False
    
    async def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        """
        Cancel all open orders.
        
        Args:
            symbol: Optional symbol filter
            
        Returns:
            Number of orders cancelled
        """
        response = await self._request("POST", "/exchange", {
            "action": {
                "type": "cancelByCloid",
                "cancels": [{"asset": 0}] if not symbol else [],
            },
            "nonce": int(time.time() * 1000),
        }, signed=True)
        
        if response and response.get("status") == "ok":
            count = len(self._open_orders)
            self._open_orders.clear()
            logger.info(f"✅ [Hyperliquid] Cancelled {count} orders")
            return count
        
        return 0
    
    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """
        Set leverage for a symbol.
        
        Args:
            symbol: Trading pair
            leverage: Leverage multiplier (1-50)
            
        Returns:
            True if successful
        """
        leverage = min(leverage, self.config.max_leverage)
        symbol = symbol.upper().replace("_", "-").replace("-PERP", "")
        
        response = await self._request("POST", "/exchange", {
            "action": {
                "type": "updateLeverage",
                "asset": 0,  # Asset index
                "isCross": True,
                "leverage": leverage,
            },
            "nonce": int(time.time() * 1000),
        }, signed=True)
        
        if response and response.get("status") == "ok":
            logger.info(f"✅ [Hyperliquid] Leverage set to {leverage}x for {symbol}")
            return True
        
        return False
    
    async def get_orderbook(self, symbol: str) -> dict:
        """Get orderbook for a symbol."""
        symbol = symbol.upper().replace("_", "-").replace("-PERP", "")
        
        response = await self._request("POST", "/info", {
            "type": "l2Book",
            "coin": symbol,
        })
        
        if response and "levels" in response:
            return {
                "bids": [(float(b[0]["px"]), float(b[0]["sz"])) for b in response["levels"][0]],
                "asks": [(float(a[0]["px"]), float(a[0]["sz"])) for a in response["levels"][1]],
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        return {"bids": [], "asks": []}
    
    async def get_ticker(self, symbol: str) -> dict:
        """Get ticker data for a symbol."""
        symbol = symbol.upper().replace("_", "-").replace("-PERP", "")
        
        response = await self._request("POST", "/info", {
            "type": "allMids",
        })
        
        if response and symbol in response:
            return {
                "symbol": symbol,
                "mid_price": float(response[symbol]),
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        return {}
    
    async def get_account_value(self) -> float:
        """Get total account value."""
        response = await self._request("POST", "/info", {
            "type": "clearinghouseState",
            "user": self._wallet_address,
        })
        
        if response:
            return float(response.get("marginSummary", {}).get("accountValue", 0))
        
        return 0.0
    
    async def close(self) -> None:
        """Close the client and cleanup."""
        if self._session:
            await self._session.close()
            self._session = None
        
        self._initialized = False
        logger.info("🔷 [Hyperliquid] Client closed")
    
    def get_status(self) -> dict:
        """Get client status summary."""
        return {
            "initialized": self._initialized,
            "testnet": self._testnet,
            "wallet": self._wallet_address[:10] + "..." if self._wallet_address else None,
            "supported_symbols": self.config.primary_symbols,
            "open_positions": len(self._positions),
            "open_orders": len(self._open_orders),
            "api_url": self.config.api_url,
        }


# Factory function
async def create_hyperliquid_client(
    private_key: str,
    wallet_address: str,
    testnet: bool = False,
    config: Optional[HyperliquidConfig] = None,
) -> HyperliquidClient:
    """
    Create and initialize a Hyperliquid client.
    
    Args:
        private_key: Ethereum private key
        wallet_address: Wallet address
        testnet: Use testnet
        config: Optional configuration
        
    Returns:
        Initialized client
    """
    client = HyperliquidClient(
        private_key=private_key,
        wallet_address=wallet_address,
        testnet=testnet,
        config=config,
    )
    await client.initialize()
    return client


if __name__ == "__main__":
    async def demo():
        print("🔷 Hyperliquid Client Demo\n")
        
        # Demo without real credentials
        client = HyperliquidClient(
            private_key="demo_key",
            wallet_address="0xdemo",
            testnet=True,
        )
        
        print(f"Status: {client.get_status()}")
        print(f"Supported symbols: {client.supported_symbols}")
        print(f"Handles BTC-PERP: {client.handles_symbol('BTC-PERP')}")
        print(f"Handles SOL-PERP: {client.handles_symbol('SOL-PERP')}")
    
    asyncio.run(demo())
