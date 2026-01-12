"""
Symphony API Client for Monad Implementation Treasury (MIT)
Autonomous AI agent trading on Symphony's execution network.
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx
from logger import get_logger

logger = get_logger(__name__)

# Symphony API Configuration
# Symphony API Configuration
from symphony_config import (
    AGENTS_CONFIG,
    MIT_ACTIVATION_THRESHOLD,
    SYMPHONY_AGENT_ID,
    SYMPHONY_API_KEY,
    SYMPHONY_BASE_URL,
)


class SymphonyClient:
    """
    Client for Symphony API - Monad blockchain trading platform.
    Official API Documentation: https://docs.symphony.io

    Features:
    - Perpetual futures trading
    - Spot trading
    - Full custody smart account
    - Delegated signing for AI agents
    """

    def __init__(self, api_key: Optional[str] = None, agent_id: Optional[str] = None):
        """
        Initialize Symphony client with multi-agent support.
        """
        # Default credentials (usually MILF based on local.env)
        self.default_api_key = api_key or SYMPHONY_API_KEY
        self.default_agent_id = agent_id or SYMPHONY_AGENT_ID

        if not self.default_api_key:
            logger.warning("Symphony API key missing. Using mock key.")
            self.default_api_key = "mock_sk_live_demo123"

        self.base_url = SYMPHONY_BASE_URL

        # Initialize clients for all configured agents
        self.clients: Dict[str, httpx.AsyncClient] = {}
        self.agent_map: Dict[str, Dict[str, Any]] = {}  # Map agent_name -> {id, type, chain}

        # 1. Initialize default client
        self.clients["default"] = self._create_client(self.default_api_key)

        # 2. Initialize specific agent clients from config
        for name, config in AGENTS_CONFIG.items():
            if config["key"] and config["id"]:
                self.clients[name] = self._create_client(config["key"])
                self.agent_map[name] = config
                logger.info(
                    f"🔹 Initialized client for {name} ({config['type']} on {config['chain']})"
                )

        # Track activation status (per agent if needed, simplistic for now)
        self._activation_trades = 0
        self._activated = False

    @property
    def client(self) -> httpx.AsyncClient:
        """Backward compatibility: return default client."""
        return self.clients["default"]

    def _create_client(self, key: str) -> httpx.AsyncClient:
        """Create an HTTP client with specific API key."""
        return httpx.AsyncClient(
            timeout=30.0,
            headers={
                "x-api-key": key,
                "Content-Type": "application/json",
                "User-Agent": "Sapphire-Agent/1.0",
            },
        )

    def _get_client_for_request(
        self, agent_id: Optional[str] = None
    ) -> tuple[httpx.AsyncClient, str]:
        """
        Get the correct client and agent_id for a request.
        Returns (client, effective_agent_id).
        """
        if not agent_id:
            return self.clients["default"], self.default_agent_id

        # Check if agent_id matches a known named config
        for name, config in self.agent_map.items():
            if config["id"] == agent_id:
                return self.clients[name], agent_id

        # If passed an unknown ID, maybe user manually instantiated with a key?
        # Fallback to default client but warn if ID mismatch likely implies key mismatch
        return self.clients["default"], agent_id

    async def close(self):
        """Close all HTTP clients."""
        for client in self.clients.values():
            await client.aclose()

    async def notify(self, message: str):
        """Send notification via Symphony (Logs for now)."""
        logger.info(f"🔔 SYMPHONY NOTICE: {message}")

    # ==================== ACCOUNT MANAGEMENT ====================

    async def get_account_info(self) -> Dict[str, Any]:
        """
        Get Symphony smart account information.
        """
        try:
            # We use get_perpetual_positions to infer activity since /wallet is 404
            # and we have a valid agent_id
            positions = await self.get_perpetual_positions()

            # Simple structure for now
            return {
                "address": "unknown",  # We can't fetch this yet
                "balance": {
                    "USDC": 250.0
                },  # Mocked based on user input for now or fetch if endpoint found
                "trades_count": self._activation_trades,
                "is_activated": self._activated
                or (self._activation_trades >= MIT_ACTIVATION_THRESHOLD),
                "activation_threshold": MIT_ACTIVATION_THRESHOLD,
                "agent_id": self.default_agent_id,
            }
        except Exception as e:
            logger.error(f"Failed to get Symphony account info: {e}")
            return {
                "address": "unknown",
                "balance": {"USDC": 0.0},
                "trades_count": 0,
                "is_activated": False,
            }

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
        profile_image: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Register a new Agentic Fund on Symphony.
        """
        # ... (Implementation kept simple or skipped if not needed for activation)
        return {"id": "mock_id", "status": "simulated"}

    async def get_my_funds(self) -> List[Dict[str, Any]]:
        """Get all agentic funds created by this user."""
        return []

    # ==================== PERPETUAL TRADING ====================

    async def open_perpetual_position(
        self,
        symbol: str,
        action: str,  # "LONG" or "SHORT"
        weight: float,  # 0-100, % of collateral
        leverage: float = 1.1,  # Minimum 1.1
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        trigger_price: Optional[float] = None,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Open a perpetual futures position via POST /agent/batch-open.
        Per Symphony Docs: https://docs.symphony.io/developers/launch-agentic-fund/perpetual-trading-guide
        """
        # Build payload per docs
        # Use provided agent_id or default
        client, eff_agent_id = self._get_client_for_request(agent_id or self.default_agent_id)

        payload = {
            "agentId": eff_agent_id,
            "symbol": symbol,  # e.g., "SOL", "BTC", "ETH"
            "action": action.upper(),  # "LONG" or "SHORT"
            "weight": weight,  # 0-100
            "leverage": max(leverage, 1.1),  # Min 1.1 per docs
        }

        # Optional orderOptions
        order_options = {}
        if trigger_price:
            order_options["triggerPrice"] = trigger_price
        if stop_loss:
            order_options["stopLossPrice"] = stop_loss
        if take_profit:
            order_options["takeProfitPrice"] = take_profit
        if order_options:
            payload["orderOptions"] = order_options

        logger.info(f"📈 Opening Perp: {action} {symbol} @ {weight}% weight, {leverage}x leverage")

        try:
            # client and eff_agent_id already determined above

            response = await client.post(f"{self.base_url}/agent/batch-open", json=payload)
            response.raise_for_status()
            data = response.json()

            # Update activation count from response
            successful = data.get("successful", 0)
            if successful > 0:
                self._activation_trades += 1
                logger.info(f"✅ Trade successful! Activation: {self._activation_trades}/5")

            return data
        except httpx.HTTPStatusError as e:
            error_text = e.response.text
            logger.error(f"❌ Batch open failed ({e.response.status_code}): {error_text}")
            # Return structured error for handling
            return {
                "status": "error",
                "code": e.response.status_code,
                "message": error_text,
                "batchId": None,
            }
        except Exception as e:
            logger.error(f"Failed to open perpetual position: {e}")
            raise

    async def close_perpetual_position(self, batch_id: str) -> Dict[str, Any]:
        """
        Close a perpetual position by batchId via POST /agent/batch-close.
        Per Symphony Docs.
        """
        payload = {
            "agentId": self.default_agent_id,
            "batchId": batch_id,
        }

        logger.info(f"📉 Closing batch: {batch_id}")

        try:
            # For closing, we need to know which agent owns the batch.
            # For closing, we need to know which agent owns the batch.
            # Assuming self.agent_id is correct context, or we might need to look it up if batch_id was stored with agent.
            # For now, default to current context.
            client, eff_agent_id = self._get_client_for_request(self.default_agent_id)
            payload["agentId"] = eff_agent_id

            response = await client.post(f"{self.base_url}/agent/batch-close", json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Batch close failed: {e.response.text}")
            return {"status": "error", "code": e.response.status_code, "message": e.response.text}
        except Exception as e:
            logger.error(f"Failed to close perpetual position: {e}")
            raise

    async def get_perpetual_positions(self) -> List[Dict[str, Any]]:
        """Get all open perpetual positions via /agent/positions."""
        try:
            # Docs: GET /agent/positions?agentId=...
            params = {}
            if self.default_agent_id:
                params["agentId"] = self.default_agent_id

            response = await self.client.get(f"{self.base_url}/agent/positions", params=params)
            response.raise_for_status()
            data = response.json()
            # Expecting {"positions": [], ...} or []
            if isinstance(data, dict):
                return data.get("positions", [])
            return data
        except Exception as e:
            logger.error(f"Failed to get perpetual positions: {e}")
            raise

    # ==================== SPOT TRADING ====================

    async def execute_spot_trade(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "market",
        agent_id: Optional[str] = None,
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

    async def execute_swap(
        self,
        token_in: str,
        token_out: str,
        weight: float,
        agent_id: Optional[str] = None,
        desired_protocol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute a Spot Swap on Monad.
        Endpoint: POST /trade/swap
        """
        payload = {
            "agentId": agent_id or self.default_agent_id,
            "tokenIn": token_in,
            "tokenOut": token_out,
            "weight": weight,
        }
        if desired_protocol:
            payload["intentOptions"] = {"desiredProtocol": desired_protocol}

        logger.info(f"🔄 Executing Spot Swap: {weight}% {token_in} -> {token_out}")

        try:
            # Select client based on agent_id
            target_agent = agent_id or self.default_agent_id
            client, eff_agent_id = self._get_client_for_request(target_agent)
            payload["agentId"] = eff_agent_id

            # Try batch-swap based on batch-open pattern
            response = await client.post(f"{self.base_url}/agent/batch-swap", json=payload)
            response.raise_for_status()
            data = response.json()

            # Track activation
            successful = data.get("successful", 0)
            if successful > 0:
                self._activation_trades += 1
                logger.info(f"✅ Swap successful! Activation: {self._activation_trades}/5")

            return data
        except httpx.HTTPStatusError as e:
            error_text = e.response.text
            logger.error(f"❌ Swap failed ({e.response.status_code}): {error_text}")
            return {
                "status": "error",
                "code": e.response.status_code,
                "message": error_text,
                "batchId": None,
            }
        except Exception as e:
            logger.error(f"Failed to execute spot swap: {e}")
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
        """Check if the agentic fund is activated."""
        return self._activated or self._activation_trades >= MIT_ACTIVATION_THRESHOLD

    @property
    def activation_progress(self) -> Dict[str, Any]:
        """Get activation progress."""
        return {
            "current": min(self._activation_trades, MIT_ACTIVATION_THRESHOLD),
            "required": MIT_ACTIVATION_THRESHOLD,
            "percentage": (
                100.0
                if MIT_ACTIVATION_THRESHOLD == 0
                else min(self._activation_trades / MIT_ACTIVATION_THRESHOLD * 100, 100)
            ),
            "activated": self.is_activated,
        }

    async def subscribe_strategy(self, strategy_id: str = "default") -> bool:
        """
        Subscribe to a Symphony strategy for automated trading signals.

        Args:
            strategy_id: The ID of the strategy to subscribe to.

        Returns:
            True if subscription successful.
        """
        try:
            response = await self.client.post(f"{self.base_url}/strategies/{strategy_id}/subscribe")
            if response.status_code == 404:
                logger.warning(f"Strategy {strategy_id} not found, skipping subscription")
                return False
            response.raise_for_status()
            logger.info(f"✅ Subscribed to Symphony strategy: {strategy_id}")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Failed to subscribe to strategy {strategy_id}: {e}")
            return False


# Singleton instance
_symphony_client: Optional[SymphonyClient] = None


def get_symphony_client(
    api_key: Optional[str] = None, agent_id: Optional[str] = None
) -> SymphonyClient:
    """Get or create Symphony client singleton."""
    global _symphony_client
    if _symphony_client is None:
        _symphony_client = SymphonyClient(api_key=api_key, agent_id=agent_id)
    return _symphony_client
