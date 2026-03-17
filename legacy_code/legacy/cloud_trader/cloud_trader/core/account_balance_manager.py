"""
Account Balance Manager
Fetches real account balances from all trading platforms
"""

import logging
from typing import Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class AccountBalanceManager:
    """
    Manages real-time account balances across all platforms

    CRITICAL: Position sizing MUST use real account balances, not hardcoded values
    """

    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self._balance_cache: Dict[str, Dict] = {}
        self._cache_ttl = 30  # seconds

        logger.info("✅ AccountBalanceManager initialized")

    async def get_platform_balance(self, platform: str) -> Optional[float]:
        """
        Get current account balance for a specific platform in USD

        Returns:
            float: Account balance in USD, or None if unavailable
        """

        # Check cache first
        if platform in self._balance_cache:
            cached = self._balance_cache[platform]
            age = (datetime.now() - cached['timestamp']).total_seconds()
            if age < self._cache_ttl:
                logger.debug(f"💰 Using cached balance for {platform}: ${cached['balance']:.2f}")
                return cached['balance']

        # Fetch fresh balance based on platform
        try:
            if platform == "lighter":
                balance = await self._get_lighter_balance()
            elif platform == "aster":
                balance = await self._get_aster_balance()
            elif platform == "aster":
                balance = await self._get_aster_balance()
            elif platform == "aster":
                balance = await self._get_aster_balance()
            elif platform == "lighter":
                balance = await self._get_lighter_balance()
            else:
                logger.warning(f"⚠️ Unknown platform: {platform}")
                return None

            # Cache the result
            if balance is not None:
                self._balance_cache[platform] = {
                    'balance': balance,
                    'timestamp': datetime.now()
                }
                logger.info(f"💰 {platform.title()} balance: ${balance:.2f}")

            return balance

        except Exception as e:
            logger.error(f"❌ Error fetching {platform} balance: {e}")
            return None

    async def _get_lighter_balance(self) -> Optional[float]:
        """Get Lighter account equity"""
        if not hasattr(self.orchestrator, 'hl_client') or not self.orchestrator.hl_client:
            logger.warning("⚠️ Lighter client not available")
            return None

        try:
            hl_client = self.orchestrator.hl_client

            # Get user state
            account_state = await hl_client.get_user_state()
            if not account_state:
                logger.warning("⚠️ Could not fetch Lighter account state")
                return None

            # Extract account value
            account_value = account_state.get("marginSummary", {}).get("accountValue", 0)
            return float(account_value)

        except Exception as e:
            logger.error(f"❌ Lighter balance error: {e}")
            return None

    async def _get_aster_balance(self) -> Optional[float]:
        """Get Aster account equity"""
        if not hasattr(self.orchestrator, 'aster') or not self.orchestrator.aster:
            logger.warning("⚠️ Aster client not available")
            return None

        try:
            if not self.orchestrator.aster.is_initialized:
                logger.warning("⚠️ Aster client not initialized")
                return None

            # Get total equity (includes SOL balance + unrealized PnL)
            equity = await self.orchestrator.aster.get_total_equity()
            return float(equity) if equity else None

        except Exception as e:
            logger.error(f"❌ Aster balance error: {e}")
            return None

    async def _get_aster_balance(self) -> Optional[float]:
        """Get Aster account balance"""
        if not hasattr(self.orchestrator, '_exchange_client') or not self.orchestrator._exchange_client:
            logger.warning("⚠️ Aster client not available")
            return None

        try:
            aster_client = self.orchestrator._exchange_client

            # Get account balance
            account_info = await aster_client.get_account()
            if not account_info:
                logger.warning("⚠️ Could not fetch Aster account info")
                return None

            # Sum up all balances (usually USDC)
            total_balance = 0.0
            balances = account_info.get("balances", [])

            for balance in balances:
                asset = balance.get("asset", "")
                free = float(balance.get("free", 0))
                locked = float(balance.get("locked", 0))

                # For USDC/USDT, add directly
                if asset in ["USDC", "USDT"]:
                    total_balance += (free + locked)
                # For other assets, would need to convert to USD
                # Skipping for now, can add price conversion later

            return total_balance

        except Exception as e:
            logger.error(f"❌ Aster balance error: {e}")
            return None

    async def _get_aster_balance(self) -> Optional[float]:
        """Get Aster account balance"""
        if not hasattr(self.orchestrator, 'aster') or not self.orchestrator.aster:
            logger.warning("⚠️ Aster client not available")
            return None

        try:
            aster_client = self.orchestrator.aster

            # Aster has multiple agents, need to sum them
            # For now, return a conservative estimate
            # TODO: Implement proper Aster balance fetching
            logger.warning("⚠️ Aster balance fetching not yet implemented")
            return None

        except Exception as e:
            logger.error(f"❌ Aster balance error: {e}")
            return None

    async def _get_lighter_balance(self) -> Optional[float]:
        """Get Lighter account balance"""
        if not hasattr(self.orchestrator, 'lighter_client') or not self.orchestrator.lighter_client:
            logger.warning("⚠️ Lighter client not available")
            return None

        try:
            # TODO: Implement Lighter balance fetching
            logger.warning("⚠️ Lighter balance fetching not yet implemented")
            return None

        except Exception as e:
            logger.error(f"❌ Lighter balance error: {e}")
            return None

    async def get_total_balance(self) -> float:
        """Get total balance across all platforms"""
        total = 0.0

        for platform in ["lighter", "aster", "aster", "aster", "lighter"]:
            balance = await self.get_platform_balance(platform)
            if balance:
                total += balance

        return total

    def clear_cache(self, platform: Optional[str] = None):
        """Clear balance cache for a platform or all platforms"""
        if platform:
            self._balance_cache.pop(platform, None)
            logger.debug(f"🗑️ Cleared balance cache for {platform}")
        else:
            self._balance_cache.clear()
            logger.debug("🗑️ Cleared all balance caches")
