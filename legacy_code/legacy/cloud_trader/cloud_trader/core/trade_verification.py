"""
Trade Verification Service
Ensures trades are actually executed before notifications are sent
"""

import logging
from typing import Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class VerifiedTrade:
    """A trade that has been verified on the platform"""
    symbol: str
    side: str
    quantity: float
    fill_price: float
    platform: str
    tx_sig: Optional[str]
    timestamp: datetime

    # Account info
    account_balance: Optional[float] = None
    account_equity: Optional[float] = None
    account_margin: Optional[float] = None

    # Position info
    position_size: Optional[float] = None
    position_entry_price: Optional[float] = None
    position_unrealized_pnl: Optional[float] = None
    position_leverage: Optional[float] = None
    liquidation_price: Optional[float] = None

    # Value info
    notional_value: Optional[float] = None  # quantity * price
    actual_usd_value: Optional[float] = None  # actual position value (notional / leverage)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "fill_price": self.fill_price,
            "platform": self.platform,
            "tx_sig": self.tx_sig,
            "timestamp": self.timestamp.isoformat(),
            "account_balance": self.account_balance,
            "account_equity": self.account_equity,
            "account_margin": self.account_margin,
            "position_size": self.position_size,
            "position_entry_price": self.position_entry_price,
            "position_unrealized_pnl": self.position_unrealized_pnl,
            "position_leverage": self.position_leverage,
            "liquidation_price": self.liquidation_price,
            "notional_value": self.notional_value,
            "actual_usd_value": self.actual_usd_value,
        }


class TradeVerificationService:
    """
    Verifies trades were actually executed and enriches with position data

    CRITICAL: Only verified trades should trigger Telegram notifications
    """

    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        logger.info("✅ TradeVerificationService initialized")

    async def verify_trade(
        self,
        execution_result,
        symbol: str,
        side: str,
        quantity: float,
    ) -> Optional[VerifiedTrade]:
        """
        Verify a trade actually executed and enrich with account/position data

        Returns VerifiedTrade if successful, None if trade failed or can't be verified
        """

        # Step 1: Check if ExecutionResult indicates success
        if not execution_result.success:
            logger.warning(f"❌ Trade verification FAILED: {execution_result.error}")
            return None

        # Step 2: Check if we have a fill price (proof of execution)
        if not execution_result.price or execution_result.price == 0:
            logger.error(
                f"❌ Trade verification FAILED: No fill price returned "
                f"(platform={execution_result.platform.value}, symbol={symbol})"
            )
            return None

        # Step 3: Platform-specific verification
        platform = execution_result.platform.value

        if platform == "lighter":
            verified = await self._verify_lighter_trade(
                execution_result, symbol, side, quantity
            )
        elif platform == "aster":
            verified = await self._verify_aster_trade(
                execution_result, symbol, side, quantity
            )
        elif platform == "aster":
            verified = await self._verify_aster_trade(
                execution_result, symbol, side, quantity
            )
        elif platform == "aster":
            verified = await self._verify_aster_trade(
                execution_result, symbol, side, quantity
            )
        elif platform == "lighter":
            verified = await self._verify_lighter_trade(
                execution_result, symbol, side, quantity
            )
        else:
            logger.warning(f"⚠️ No verification for platform: {platform}")
            verified = None

        if verified:
            logger.info(
                f"✅ Trade VERIFIED: {side} {quantity} {symbol} @ ${verified.fill_price} "
                f"(equity=${verified.account_equity:.2f}, liq=${verified.liquidation_price})"
            )
        else:
            logger.error(f"❌ Trade verification FAILED for {platform}")

        return verified

    async def _verify_lighter_trade(
        self,
        execution_result,
        symbol: str,
        side: str,
        quantity: float,
    ) -> Optional[VerifiedTrade]:
        """Verify Lighter trade and fetch account/position data"""

        # Check if Lighter client is available
        if not hasattr(self.orchestrator, 'hl_client') or not self.orchestrator.hl_client:
            logger.error("❌ Lighter client not available for verification")
            return None

        hl_client = self.orchestrator.hl_client

        try:
            # Get account state
            account_state = await hl_client.get_user_state()
            if not account_state:
                logger.error("❌ Could not fetch Lighter account state")
                return None

            # Extract account info
            account_value = account_state.get("marginSummary", {}).get("accountValue", 0)
            total_margin_used = account_state.get("marginSummary", {}).get("totalMarginUsed", 0)

            # Get position for this symbol
            coin = symbol.upper().replace("-USDC", "").replace("-USD", "").replace("-PERP", "")
            positions = account_state.get("assetPositions", [])

            position = None
            for pos in positions:
                if pos.get("position", {}).get("coin") == coin:
                    position = pos.get("position", {})
                    break

            if not position:
                logger.warning(f"⚠️ No position found for {coin} after trade")
                # Trade might have been too small or immediately closed
                return None

            # Extract position data
            position_data = position.get("position", position)  # Handle nested structure
            position_szi = float(position_data.get("szi", 0))
            entry_price = float(position_data.get("entryPx", 0))
            unrealized_pnl = float(position_data.get("unrealizedPnl", 0))
            liquidation_px = float(position_data.get("liquidationPx", 0))
            leverage_str = position_data.get("leverage", {}).get("value", "1")
            leverage = float(leverage_str) if leverage_str else 1.0

            # Calculate values
            notional_value = abs(position_szi) * entry_price
            actual_usd_value = notional_value / leverage if leverage > 0 else notional_value

            return VerifiedTrade(
                symbol=symbol,
                side=side,
                quantity=quantity,
                fill_price=execution_result.price,
                platform="lighter",
                tx_sig=execution_result.tx_sig,
                timestamp=datetime.now(),
                account_balance=float(account_value),
                account_equity=float(account_value),
                account_margin=float(total_margin_used),
                position_size=position_szi,
                position_entry_price=entry_price,
                position_unrealized_pnl=unrealized_pnl,
                position_leverage=leverage,
                liquidation_price=liquidation_px,
                notional_value=notional_value,
                actual_usd_value=actual_usd_value,
            )

        except Exception as e:
            logger.error(f"❌ Lighter verification error: {e}", exc_info=True)
            return None

    async def _verify_aster_trade(
        self,
        execution_result,
        symbol: str,
        side: str,
        quantity: float,
    ) -> Optional[VerifiedTrade]:
        """Verify Aster trade and fetch account/position data"""

        if not hasattr(self.orchestrator, 'aster') or not self.orchestrator.aster:
            logger.error("❌ Aster client not available for verification")
            return None

        # TODO: Implement Aster verification when client is connected
        logger.warning("⚠️ Aster verification not yet implemented")
        return None

    async def _verify_aster_trade(
        self,
        execution_result,
        symbol: str,
        side: str,
        quantity: float,
    ) -> Optional[VerifiedTrade]:
        """Verify Aster trade and fetch account/position data"""

        if not hasattr(self.orchestrator, '_exchange_client') or not self.orchestrator._exchange_client:
            logger.error("❌ Aster client not available for verification")
            return None

        # TODO: Implement Aster verification
        logger.warning("⚠️ Aster verification not yet implemented")
        return None

    async def _verify_aster_trade(
        self,
        execution_result,
        symbol: str,
        side: str,
        quantity: float,
    ) -> Optional[VerifiedTrade]:
        """Verify Aster trade and fetch account/position data"""

        if not hasattr(self.orchestrator, 'aster') or not self.orchestrator.aster:
            logger.error("❌ Aster client not available for verification")
            return None

        # TODO: Implement Aster verification
        logger.warning("⚠️ Aster verification not yet implemented")
        return None

    async def _verify_lighter_trade(
        self,
        execution_result,
        symbol: str,
        side: str,
        quantity: float,
    ) -> Optional[VerifiedTrade]:
        """Verify Lighter trade and fetch account/position data"""

        if not hasattr(self.orchestrator, 'lighter_client') or not self.orchestrator.lighter_client:
            logger.error("❌ Lighter client not available for verification")
            return None

        # TODO: Implement Lighter verification
        logger.warning("⚠️ Lighter verification not yet implemented")
        return None
