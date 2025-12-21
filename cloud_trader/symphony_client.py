"""
Symphony API Client for Monad Implementation Treasury (MIT)
Autonomous AI agent trading on Symphony's execution network.
"""

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# Symphony API Configuration
SYMPHONY_BASE_URL = "https://api.symphony.finance"  # Update with actual Symphony API endpoint
SYMPHONY_API_VERSION = "v1"


class SymphonyClient:
    """
    Client for Symphony API - Monad blockchain trading platform.
    
    Features:
    - Perpetual futures trading
    - Spot trading
    - Full custody smart account
    - Delegated signing for AI agents
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Symphony client.
        
        Args:
            api_key: Symphony API key (sk_live_...). If not provided, reads from env.
        """
        self.api_key = api_key or os.getenv("SYMPHONY_API_KEY")
        if not self.api_key:
            raise ValueError("Symphony API key required. Set SYMPHONY_API_KEY env var or pass api_key param.")
        
        self.base_url = f"{SYMPHONY_BASE_URL}/{SYMPHONY_API_VERSION}"
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "MIT-Agent/1.0"
            }
        )
        
        # Track activation status
        self._activation_trades = 0
        self._activated = False

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    # ==================== ACCOUNT MANAGEMENT ====================

    async def get_account_info(self) -> Dict[str, Any]:
        """
        Get Symphony smart account information.
        
        Returns:
            {
                "address": "0x...",
                "balance": {"USDC": 1000.0},
                "is_activated": false,
                "trades_count": 3,
                "activation_threshold": 5
            }
        """
        try:
            response = await self.client.get(f"{self.base_url}/account")
            response.raise_for_status()
            data = response.json()
            
            # Update activation status
            self._activation_trades = data.get("trades_count", 0)
            self._activated = data.get("is_activated", False)
            
            return data
        except Exception as e:
            logger.error(f"Failed to get Symphony account info: {e}")
            raise

    async def get_balance(self) -> Dict[str, float]:
        """Get account balance (USDC only currently supported)."""
        account = await self.get_account_info()
        return account.get("balance", {"USDC": 0.0})

    # ==================== AGENTIC FUND MANAGEMENT ====================

    async def create_agentic_fund(
        self,
        name: str,
        description: str,
        fund_type: str = "perpetuals",
        autosubscribe: bool = True,
        profile_image: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Register a new Agentic Fund on Symphony.
        
        Args:
            name: Fund name
            description: Fund description
            fund_type: "perpetuals", "swaps", or "yields"
            autosubscribe: Auto-execute trades on creator's wallet
            profile_image: Base64 encoded image or URL
            
        Returns:
            {
                "fund_id": "...",
                "name": "...",
                "status": "pending_activation",
                "trades_required": 5
            }
        """
        payload = {
            "name": name,
            "description": description,
            "fund_type": fund_type,
            "autosubscribe": autosubscribe,
        }
        
        if profile_image:
            payload["profile_image"] = profile_image
        
        try:
            response = await self.client.post(f"{self.base_url}/funds", json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to create agentic fund: {e}")
            raise

    async def get_my_funds(self) -> List[Dict[str, Any]]:
        """Get all agentic funds created by this user."""
        try:
            response = await self.client.get(f"{self.base_url}/funds/my")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get agentic funds: {e}")
            raise

    # ==================== PERPETUAL TRADING ====================

    async def open_perpetual_position(
        self,
        symbol: str,
        side: str,
        size: float,
        leverage: int = 1,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Open a perpetual futures position.
        
        Args:
            symbol: Trading pair (e.g., "BTC-USDC")
            side: "LONG" or "SHORT"
            size: Position size in USDC
            leverage: Leverage multiplier (1-20)
            stop_loss: Optional SL price
            take_profit: Optional TP price
            
        Returns:
            {
                "position_id": "...",
                "symbol": "BTC-USDC",
                "side": "LONG",
                "entry_price": 42000.0,
                "size": 100.0,
                "leverage": 5,
                "status": "open"
            }
        """
        payload = {
            "symbol": symbol,
            "side": side.upper(),
            "size": size,
            "leverage": leverage,
        }
        
        if stop_loss:
            payload["stop_loss"] = stop_loss
        if take_profit:
            payload["take_profit"] = take_profit
        
        try:
            response = await self.client.post(f"{self.base_url}/perpetuals/positions", json=payload)
            response.raise_for_status()
            data = response.json()
            
            # Update activation count
            account = await self.get_account_info()
            logger.info(f"Activation progress: {account.get('trades_count', 0)}/5 trades")
            
            return data
        except Exception as e:
            logger.error(f"Failed to open perpetual position: {e}")
            raise

    async def close_perpetual_position(self, position_id: str) -> Dict[str, Any]:
        """Close a perpetual position by ID."""
        try:
            response = await self.client.delete(f"{self.base_url}/perpetuals/positions/{position_id}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to close perpetual position: {e}")
            raise

    async def get_perpetual_positions(self) -> List[Dict[str, Any]]:
        """Get all open perpetual positions."""
        try:
            response = await self.client.get(f"{self.base_url}/perpetuals/positions")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get perpetual positions: {e}")
            raise

    # ==================== SPOT TRADING ====================

    async def execute_spot_trade(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "market"
    ) -> Dict[str, Any]:
        """
        Execute a spot trade.
        
        Args:
            symbol: Trading pair (e.g., "BTC-USDC")
            side: "BUY" or "SELL"
            quantity: Amount to trade
            order_type: "market" or "limit"
            
        Returns:
            {
                "order_id": "...",
                "symbol": "BTC-USDC",
                "side": "BUY",
                "executed_price": 42000.0,
                "quantity": 0.5,
                "status": "filled"
            }
        """
        payload = {
            "symbol": symbol,
            "side": side.upper(),
            "quantity": quantity,
            "order_type": order_type,
        }
        
        try:
            response = await self.client.post(f"{self.base_url}/spot/orders", json=payload)
            response.raise_for_status()
            data = response.json()
            
            # Update activation count
            account = await self.get_account_info()
            logger.info(f"✨ Activation progress: {account.get('trades_count', 0)}/5 trades")
            
            return data
        except Exception as e:
            logger.error(f"Failed to execute spot trade: {e}")
            raise

    # ==================== MARKET DATA ====================

    async def get_market_price(self, symbol: str) -> float:
        """Get current market price for a symbol."""
        try:
            response = await self.client.get(f"{self.base_url}/market/price/{symbol}")
            response.raise_for_status()
            data = response.json()
            return float(data.get("price", 0))
        except Exception as e:
            logger.error(f"Failed to get market price: {e}")
            raise

    async def get_available_symbols(self) -> List[str]:
        """Get list of available trading symbols."""
        try:
            response = await self.client.get(f"{self.base_url}/market/symbols")
            response.raise_for_status()
            data = response.json()
            return data.get("symbols", [])
        except Exception as e:
            logger.error(f"Failed to get available symbols: {e}")
            return []

    # ==================== HELPERS ====================

    @property
    def is_activated(self) -> bool:
        """Check if the agentic fund is activated (5+ trades completed)."""
        return self._activated or self._activation_trades >= 5

    @property
    def activation_progress(self) -> Dict[str, Any]:
        """Get activation progress."""
        return {
            "current": min(self._activation_trades, 5),
            "required": 5,
            "percentage": min(self._activation_trades / 5.0 * 100, 100),
            "activated": self.is_activated
        }


# Singleton instance
_symphony_client: Optional[SymphonyClient] = None


def get_symphony_client(api_key: Optional[str] = None) -> SymphonyClient:
    """Get or create Symphony client singleton."""
    global _symphony_client
    if _symphony_client is None:
        _symphony_client = SymphonyClient(api_key=api_key)
    return _symphony_client
