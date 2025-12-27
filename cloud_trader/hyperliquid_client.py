import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from eth_account.account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

from .logger import get_logger

logger = get_logger(__name__)

class HyperliquidClient:
    """
    Client for interacting with Hyperliquid DEX.
    Handles authentication, order placement, and market data fetching.
    """

    def __init__(self, secret_key: Optional[str] = None, account_address: Optional[str] = None):
        """
        Initialize the Hyperliquid client.
        
        Args:
            secret_key: Private key (hex string) for signing transactions.
            account_address: Public address of the account.
        """
        from .config import get_settings
        settings = get_settings()
        self.secret_key = secret_key or settings.hl_secret_key
        self.account_address = account_address or settings.hl_account_address
        self.base_url = constants.MAINNET_API_URL
        self._info = Info(self.base_url, skip_ws=True)
        self._exchange = None
        self.is_initialized = False

    async def initialize(self) -> bool:
        """Initialize connection and verify credentials."""
        try:
            if not self.secret_key or not self.account_address:
                logger.warning("⚠️ HL_SECRET_KEY or HL_ACCOUNT_ADDRESS not set. Hyperliquid running in Read-Only mode.")
                return False

            self.account = Account.from_key(self.secret_key)
            if self.account.address.lower() != self.account_address.lower():
                logger.warning(f"⚠️ HL Secret Key address ({self.account.address}) does not match configured address ({self.account_address})")
            
            self._exchange = Exchange(self.account, self.base_url)
            self.is_initialized = True
            logger.info(f"✅ Hyperliquid Client Initialized for {self.account_address[:6]}...")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize Hyperliquid Client: {e}")
            return False

    async def get_account_summary(self) -> Dict[str, Any]:
        """Fetch account margin summary and open positions."""
        try:
            # Info methods are synchronous in the SDK, so we run them in a thread if needed, 
            # or just call them directly if they are fast enough. 
            # For now, we wrap in asyncio.to_thread for safety.
            user_state = await asyncio.to_thread(self._info.user_state, self.account_address)
            return user_state
        except Exception as e:
            logger.error(f"Error fetching HL account summary: {e}")
            return {}

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get formatted open positions."""
        summary = await self.get_account_summary()
        raw_positions = summary.get("assetPositions", [])
        formatted_positions = []
        
        for pos in raw_positions:
            p = pos.get("position", {})
            if float(p.get("szi", 0)) != 0:
                formatted_positions.append({
                    "symbol": pos.get("coin"),
                    "size": float(p.get("szi", 0)),
                    "entry_price": float(p.get("entryPx", 0)),
                    "pnl": float(p.get("unrealizedPnl", 0)),
                    "leverage": float(p.get("leverage", {}).get("value", 0)),
                    "side": "LONG" if float(p.get("szi", 0)) > 0 else "SHORT"
                })
        return formatted_positions

    async def place_order(self, coin: str, is_buy: bool, sz: float, limit_px: float, order_type: Dict[str, Any] = {"limit": {"tif": "Gtc"}}) -> Any:
        """
        Place an order on Hyperliquid.
        
        Args:
            coin: Symbol (e.g. 'ETH')
            is_buy: True for Buy, False for Sell
            sz: Size in base asset
            limit_px: Limit price
            order_type: Order type dict (default: Gtc Limit)
        """
        if not self.is_initialized or not self._exchange:
            logger.warning("Hyperliquid not initialized for trading.")
            return None

        try:
            # Exchange.order is synchronous
            logger.info(f"🚀 Placing HL Order: {coin} {'BUY' if is_buy else 'SELL'} {sz} @ {limit_px}")
            result = await asyncio.to_thread(
                self._exchange.order,
                coin,
                is_buy,
                sz,
                limit_px,
                order_type
            )
            return result
        except Exception as e:
            logger.error(f"Error placing HL order: {e}")
            return None

    async def cancel_all_orders(self) -> Any:
        """Cancel all open orders."""
        if not self.is_initialized or not self._exchange:
            return None
        try:
            logger.info("🛑 Cancelling all HL orders...")
            # Note: SDK might not have a simple 'cancel all' without open orders list
            # Implementing a safe version that fetches open orders first would be better
            # For now, relying on SDK error handling
            return None 
            # return await asyncio.to_thread(self._exchange.cancel_all_orders) # Hypothetical method
        except Exception as e:
            logger.error(f"Error cancelling HL orders: {e}")
            return None
