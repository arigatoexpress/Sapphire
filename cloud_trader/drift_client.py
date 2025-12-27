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
    Note: Full functionality requires Drift SDK (driftpy).
    This adapter acts as a high-level wrapper/interface.
    """

    def __init__(self, rpc_url: Optional[str] = None):
        from .config import get_settings
        settings = get_settings()
        self.rpc_url = rpc_url or settings.solana_rpc_url
        self.private_key = settings.solana_private_key
        self.subaccount_id = int(os.getenv("DRIFT_SUBACCOUNT_ID", "0"))

        self.api_base = "https://mainnet-beta.api.drift.trade"

        if self.private_key:
            logger.info("Drift Client: SOLANA_PRIVATE_KEY loaded (redacted).")
        else:
            logger.warning("Drift Client: SOLANA_PRIVATE_KEY missing. Read-only mode.")

        # In a real implementation, we would init the DriftPy user here.
        self.is_initialized = False

    async def initialize(self):
        """Async init of Drift SDK/User."""
        logger.info("Initializing Drift Protocol Client...")
        # Simulate SDK init
        self.is_initialized = True

    async def get_perp_market(self, symbol: str = "SOL-PERP"):
        """Get market info, funding rates, open interest."""
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
            "funding_rate_24h": 0.0012,  # Still mocked until driftpy
            "open_interest": 1000000,
        }

    async def get_total_equity(self) -> float:
        """Get total equity in USD."""
        if not self.is_initialized:
            return 0.0
        # Stub for now
        return 1500.0  # Simulated $1500 balance for demo

    async def get_position(self, symbol: str) -> Dict[str, Any]:
        """Get current position for symbol."""
        if not self.is_initialized:
            logger.warning("Drift client not initialized.")
            return {}

        # Stub
        return {"symbol": symbol, "amount": 0.0, "entry_price": 0.0, "unrealized_pnl": 0.0}

    async def place_perp_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        order_type: str = "market",
        price: Optional[float] = None,
    ):
        """Place a perp order on Drift."""
        logger.info(f"Drift Order: {side.upper()} {amount} {symbol} ({order_type})")
        # In real code: construct Transaction using Drift SDK, sign, and send.
        return {"tx_sig": "sim_drift_tx_123", "status": "confirmed"}


# Singleton
_drift_client = None


def get_drift_client() -> DriftClient:
    global _drift_client
    if not _drift_client:
        _drift_client = DriftClient()
    return _drift_client
