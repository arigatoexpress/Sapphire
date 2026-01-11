"""
Hyperliquid Client - DEPRECATED

This module has been deprecated as part of the Pivot to Drift initiative.
The hyperliquid-python-sdk has been removed from requirements.

All Hyperliquid functionality has been replaced with Drift Protocol integration.
See drift_client.py for the active Solana DEX integration.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class HyperliquidClient:
    """
    Deprecated Hyperliquid client stub.

    This class exists only to prevent import errors from legacy code paths.
    All methods return safe defaults or raise deprecation warnings.
    """

    def __init__(self, secret_key: Optional[str] = None, account_address: Optional[str] = None):
        """Initialize the stub client."""
        logger.warning("⚠️ HyperliquidClient is DEPRECATED. Use DriftClient instead.")
        self.is_initialized = False
        self.secret_key = None
        self.account_address = None

    async def initialize(self) -> bool:
        """No-op initialization."""
        logger.warning("⚠️ HyperliquidClient.initialize() called but Hyperliquid is disabled.")
        return False

    async def get_balance(self) -> Dict[str, float]:
        """Return empty balance."""
        return {"USD": 0.0}

    async def get_positions(self) -> list:
        """Return empty positions."""
        return []

    async def get_account_summary(self) -> Dict[str, Any]:
        """Return empty account summary."""
        return {"marginSummary": {"accountValue": 0.0}}

    async def place_order(self, *args, **kwargs) -> Dict[str, Any]:
        """Return failed order result."""
        logger.error("❌ HyperliquidClient.place_order() called but Hyperliquid is disabled.")
        return {"status": "error", "message": "Hyperliquid is disabled"}

    async def close_position(self, *args, **kwargs) -> Dict[str, Any]:
        """Return failed close result."""
        return {"status": "error", "message": "Hyperliquid is disabled"}
