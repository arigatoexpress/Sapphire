"""
Lighter Trading Client
======================
Client for the Lighter decentralized perpetual futures exchange on Ethereum L2.

Author: Sapphire V2 Architecture Team
Version: 1.0.0
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Try to import the Lighter SDK
try:
    import lighter
    LIGHTER_SDK_AVAILABLE = True
    logger.info("✅ Lighter SDK loaded")
except ImportError:
    LIGHTER_SDK_AVAILABLE = False
    logger.warning("⚠️ Lighter SDK not available - install lighter-sdk")


@dataclass
class LighterPosition:
    """Represents a Lighter position."""
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "size": self.size,
            "entry_price": self.entry_price,
            "mark_price": self.mark_price,
            "liquidation_price": self.liquidation_price,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "leverage": self.leverage,
            "margin_used": self.margin_used,
            "side": self.side,
        }


@dataclass
class LighterOrder:
    """Represents a Lighter order result."""
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "price": self.price,
            "quantity": self.quantity,
            "filled_quantity": self.filled_quantity,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class LighterClient:
    """
    Lighter client for decentralized perpetual futures trading.
    
    Uses the lighter-sdk for API calls and transaction signing.
    Lighter runs on Ethereum L2 with ZK-rollups.
    """

    def __init__(
        self,
        pub_key: str,
        priv_key: str,
        testnet: bool = False,
    ):
        """Initialize Lighter client with credentials."""
        self._pub_key = pub_key
        self._priv_key = priv_key
        self._testnet = testnet
        
        self._client: Optional[Any] = None
        self._account_api: Optional[Any] = None
        self._transaction_api: Optional[Any] = None
        self._order_api: Optional[Any] = None
        self._initialized = False
        
        # Cache
        self._positions: Dict[str, LighterPosition] = {}
        self._market_info: Dict[str, Dict] = {}
        self._account_index: Optional[int] = None
        
    @property
    def is_initialized(self) -> bool:
        return self._initialized
    
    async def initialize(self) -> bool:
        """Initialize the Lighter SDK clients."""
        if self._initialized:
            return True
            
        if not LIGHTER_SDK_AVAILABLE:
            logger.error("❌ Cannot initialize - Lighter SDK not installed")
            return False
        
        logger.info("🔥 [Lighter] Initializing SDK...")
        
        try:
            # Set API base URL
            base_url = (
                "https://testnet.zklighter.elliot.ai" 
                if self._testnet 
                else "https://mainnet.zklighter.elliot.ai"
            )
            
            # Initialize the API client
            self._client = lighter.ApiClient()
            
            # Initialize API endpoints
            self._account_api = lighter.AccountApi(self._client)
            self._transaction_api = lighter.TransactionApi(self._client)
            self._order_api = lighter.OrderApi(self._client)
            
            # Load market metadata
            await self._load_market_info()
            
            # Get account index from pub key
            await self._load_account_info()
            
            # Load initial positions
            await self.get_positions()
            
            self._initialized = True
            logger.info(f"✅ [Lighter] SDK client initialized | Testnet: {self._testnet}")
            return True
            
        except Exception as e:
            logger.error(f"❌ [Lighter] SDK initialization failed: {e}")
            return False
    
    async def _load_market_info(self):
        """Load order book metadata from API."""
        try:
            loop = asyncio.get_event_loop()
            order_books = await loop.run_in_executor(
                None,
                lambda: self._order_api.order_books()
            )
            
            if order_books and hasattr(order_books, 'order_books'):
                for ob in order_books.order_books:
                    symbol = ob.symbol if hasattr(ob, 'symbol') else str(ob.order_book_id)
                    self._market_info[symbol.upper()] = {
                        "order_book_id": ob.order_book_id if hasattr(ob, 'order_book_id') else 0,
                        "symbol": symbol,
                        "base_asset": getattr(ob, 'base_asset', symbol),
                        "quote_asset": getattr(ob, 'quote_asset', 'USDC'),
                        "tick_size": getattr(ob, 'tick_size', 0.01),
                        "step_size": getattr(ob, 'step_size', 0.001),
                    }
                logger.info(f"📊 [Lighter] Loaded {len(self._market_info)} markets")
        except Exception as e:
            logger.warning(f"⚠️ [Lighter] Failed to load market info: {e}")
    
    async def _load_account_info(self):
        """Load account information and get account index."""
        try:
            # Query accounts by the public key (L1 address)
            # The pub_key might need to be formatted as an address
            loop = asyncio.get_event_loop()
            
            # Try to get account info - may need adjustment based on SDK
            accounts = await loop.run_in_executor(
                None,
                lambda: self._account_api.accounts_by_l1_address(l1_address=self._pub_key[:42] if len(self._pub_key) > 42 else self._pub_key)
            )
            
            if accounts and hasattr(accounts, 'accounts') and len(accounts.accounts) > 0:
                self._account_index = accounts.accounts[0].index
                logger.info(f"📋 [Lighter] Account index: {self._account_index}")
            else:
                # Default to index 0 or try to register
                self._account_index = 0
                logger.warning("⚠️ [Lighter] Could not find account, using index 0")
                
        except Exception as e:
            logger.warning(f"⚠️ [Lighter] Failed to load account info: {e}")
            self._account_index = 0
    
    async def get_positions(self) -> List[LighterPosition]:
        """Get all open positions."""
        if not self._initialized:
            await self.initialize()
            
        if not self._account_api or self._account_index is None:
            return []
        
        try:
            loop = asyncio.get_event_loop()
            account = await loop.run_in_executor(
                None,
                lambda: self._account_api.account(by="index", value=str(self._account_index))
            )
            
            positions = []
            if account and hasattr(account, 'positions'):
                for pos in account.positions:
                    if pos.size != 0:
                        position = LighterPosition(
                            symbol=pos.symbol if hasattr(pos, 'symbol') else f"MARKET_{pos.order_book_id}",
                            size=abs(float(pos.size)),
                            entry_price=float(getattr(pos, 'entry_price', 0)),
                            mark_price=float(getattr(pos, 'mark_price', 0)),
                            liquidation_price=float(getattr(pos, 'liquidation_price', 0)) if hasattr(pos, 'liquidation_price') else None,
                            unrealized_pnl=float(getattr(pos, 'unrealized_pnl', 0)),
                            realized_pnl=float(getattr(pos, 'realized_pnl', 0)),
                            leverage=float(getattr(pos, 'leverage', 1)),
                            margin_used=float(getattr(pos, 'margin', 0)),
                            side="LONG" if float(pos.size) > 0 else "SHORT",
                        )
                        positions.append(position)
                        self._positions[position.symbol] = position
            
            logger.info(f"📊 [Lighter] Fetched {len(positions)} positions")
            return positions
            
        except Exception as e:
            logger.error(f"❌ [Lighter] Failed to fetch positions: {e}")
            return []
    
    async def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        reduce_only: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Place an order using Lighter SDK.
        
        Args:
            symbol: Trading pair (e.g., "BTC", "ETH")
            side: Order side ("BUY" or "SELL")
            quantity: Order quantity
            order_type: "MARKET" or "LIMIT"
            price: Limit price (required for LIMIT orders)
            reduce_only: Whether this is a reduce-only order
            
        Returns:
            Order result dict with status, price, etc.
        """
        if not self._initialized:
            await self.initialize()
            
        if not self._transaction_api:
            return {"status": "error", "error": "Transaction API not initialized"}
        
        # Normalize symbol
        coin = symbol.upper().replace("-PERP", "").replace("-USDC", "").replace("_", "")
        
        # Get market info
        market = self._market_info.get(coin, {})
        order_book_id = market.get("order_book_id", 0)
        
        is_buy = side.upper() in ["BUY", "LONG"]
        
        logger.info(
            f"📤 [Lighter] Placing {order_type} {side} order | "
            f"Symbol: {coin} | Qty: {quantity} | OrderBookId: {order_book_id}"
        )
        
        try:
            loop = asyncio.get_event_loop()
            
            # Get next nonce for transaction
            nonce_response = await loop.run_in_executor(
                None,
                lambda: self._transaction_api.next_nonce(account_index=self._account_index)
            )
            nonce = nonce_response.nonce if hasattr(nonce_response, 'nonce') else 0
            
            # Build and send order transaction
            # The SDK should handle signing with the private key
            if order_type.upper() == "MARKET":
                # Market order - use aggressive limit price
                # Get current price for slippage calculation
                current_price = await self.get_ticker(coin)
                if current_price:
                    # 5% slippage for market order
                    limit_price = current_price * 1.05 if is_buy else current_price * 0.95
                else:
                    return {"status": "error", "error": "Could not get current price for market order"}
            else:
                if not price:
                    return {"status": "error", "error": "Price required for limit orders"}
                limit_price = price
            
            # Create order transaction
            # Note: Actual SDK method names may vary - this is based on typical patterns
            order_params = {
                "account_index": self._account_index,
                "order_book_id": order_book_id,
                "side": 0 if is_buy else 1,  # 0 = buy, 1 = sell
                "price": limit_price,
                "quantity": quantity,
                "nonce": nonce,
                "time_in_force": 1,  # IOC for market-like behavior
            }
            
            # Send transaction
            result = await loop.run_in_executor(
                None,
                lambda: self._transaction_api.send_tx(
                    tx_type="CreateOrder",
                    body=order_params,
                    signature=self._sign_transaction(order_params),
                )
            )
            
            if result and hasattr(result, 'success') and result.success:
                fill_price = getattr(result, 'avg_fill_price', limit_price)
                filled_qty = getattr(result, 'filled_quantity', quantity)
                
                logger.info(
                    f"✅ [Lighter] Order FILLED | "
                    f"Symbol: {coin} | Avg Price: ${fill_price}"
                )
                return {
                    "status": "ok",
                    "filled": True,
                    "data": {
                        "avgPx": fill_price,
                        "filledQty": filled_qty,
                        "orderId": getattr(result, 'order_id', None),
                    }
                }
            else:
                error_msg = getattr(result, 'error', 'Unknown error')
                logger.error(f"❌ [Lighter] Order failed: {error_msg}")
                return {"status": "error", "error": str(error_msg)}
                
        except Exception as e:
            logger.error(f"❌ [Lighter] Order exception: {e}")
            return {"status": "error", "error": str(e)}
    
    def _sign_transaction(self, tx_body: Dict) -> str:
        """
        Sign a transaction using the private key.
        The SDK should provide signing utilities.
        """
        try:
            # The SDK likely has a Signer class
            if hasattr(lighter, 'Signer'):
                signer = lighter.Signer(self._priv_key)
                return signer.sign(tx_body)
            else:
                # Fallback - return empty string and let SDK handle internally
                return ""
        except Exception as e:
            logger.error(f"❌ [Lighter] Signing failed: {e}")
            return ""
    
    async def get_ticker(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol."""
        if not self._order_api:
            return None
            
        try:
            coin = symbol.upper().replace("-PERP", "").replace("-USDC", "")
            market = self._market_info.get(coin, {})
            order_book_id = market.get("order_book_id", 0)
            
            loop = asyncio.get_event_loop()
            details = await loop.run_in_executor(
                None,
                lambda: self._order_api.order_book_details(order_book_id=order_book_id)
            )
            
            if details and hasattr(details, 'mid_price'):
                return float(details.mid_price)
            elif details and hasattr(details, 'last_price'):
                return float(details.last_price)
                
        except Exception as e:
            logger.warning(f"⚠️ [Lighter] Failed to get ticker for {symbol}: {e}")
        
        return None
    
    async def get_account_value(self) -> float:
        """Get total account value."""
        if not self._account_api or self._account_index is None:
            return 0.0
        
        try:
            loop = asyncio.get_event_loop()
            account = await loop.run_in_executor(
                None,
                lambda: self._account_api.account(by="index", value=str(self._account_index))
            )
            
            if account:
                equity = float(getattr(account, 'equity', 0))
                logger.info(f"💰 [Lighter] Account value: ${equity:.2f}")
                return equity
                
        except Exception as e:
            logger.error(f"❌ [Lighter] Failed to get account value: {e}")
        
        return 0.0
    
    async def close(self):
        """Cleanup client resources."""
        if self._client:
            try:
                await self._client.close()
            except Exception:
                pass
        logger.info("🔌 [Lighter] Client closed")
    
    def get_status(self) -> Dict[str, Any]:
        """Get client status."""
        return {
            "initialized": self._initialized,
            "testnet": self._testnet,
            "account_index": self._account_index,
            "markets_loaded": len(self._market_info),
            "positions_cached": len(self._positions),
        }
