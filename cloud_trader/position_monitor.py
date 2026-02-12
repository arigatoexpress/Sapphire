"""
Position Monitor for Perpetual Futures.
Tracks open positions, calculates P&L, monitors liquidation risk.
"""

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from .logger import get_logger
from .definitions import PlatformType

logger = get_logger(__name__)


@dataclass
class Position:
    """Represents an open perpetual position."""

    platform: PlatformType
    symbol: str
    side: str  # "long" or "short"
    size: float
    entry_price: float
    current_price: float
    leverage: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    liquidation_price: float
    collateral: float
    timestamp: datetime
    market_index: Optional[int] = None

    @property
    def is_profitable(self) -> bool:
        """Check if position is in profit."""
        return self.unrealized_pnl > 0

    @property
    def liquidation_distance_pct(self) -> float:
        """Calculate % distance to liquidation price."""
        if self.liquidation_price == 0:
            return 100.0
        distance = abs(self.current_price - self.liquidation_price) / self.current_price
        return distance * 100

    @property
    def risk_level(self) -> str:
        """Assess risk level based on liquidation distance."""
        distance = self.liquidation_distance_pct
        if distance < 5:
            return "CRITICAL"
        elif distance < 10:
            return "HIGH"
        elif distance < 20:
            return "MEDIUM"
        else:
            return "LOW"


class PositionMonitor:
    """
    Monitor perpetual positions across multiple platforms.
    Tracks P&L, liquidation risk, and sends alerts.
    """

    def __init__(self, sapphire_service):
        self.service = sapphire_service
        self.positions: Dict[str, Position] = {}  # Key: f"{platform}:{symbol}"
        self.monitoring = False
        self.monitor_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start position monitoring loop."""
        if self.monitoring:
            logger.warning("Position monitor already running")
            return

        self.monitoring = True
        self.monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("📊 Position Monitor started")

    async def stop(self):
        """Stop position monitoring."""
        self.monitoring = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Position Monitor stopped")

    async def _monitoring_loop(self):
        """Main monitoring loop - runs every 30 seconds."""
        while self.monitoring:
            try:
                await self._sync_all_positions()
                await self._check_liquidation_risk()
                await asyncio.sleep(30)  # Update every 30 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Position monitor error: {e}")
                await asyncio.sleep(30)

    async def _sync_all_positions(self):
        """Sync positions from all platforms."""
        # Sync Aster positions
        if self.service.aster and self.service.aster.is_initialized:
            await self._sync_aster_positions()

        # Sync Lighter positions (if perpetuals are used there)
        # Add additional platforms as needed

    async def _sync_aster_positions(self):
        """Sync perpetual positions from Aster Protocol."""
        try:
            positions = await self.service.aster.get_all_perp_positions()

            for pos_data in positions:
                symbol = pos_data["market"]
                key = f"aster:{symbol}"

                # Calculate P&L percentage
                entry_price = pos_data["entry_price"]
                current_price = pos_data["current_price"]
                pnl_pct = 0.0

                if entry_price > 0:
                    if pos_data["side"] == "long":
                        pnl_pct = ((current_price - entry_price) / entry_price) * 100
                    else:  # short
                        pnl_pct = ((entry_price - current_price) / entry_price) * 100

                # Create Position object
                position = Position(
                    platform=PlatformType.ASTER,
                    symbol=symbol,
                    side=pos_data["side"],
                    size=pos_data["size"],
                    entry_price=entry_price,
                    current_price=current_price,
                    leverage=2.0,  # Default leverage (could be calculated from collateral)
                    unrealized_pnl=pos_data["unrealized_pnl"],
                    unrealized_pnl_pct=pnl_pct,
                    liquidation_price=pos_data.get("liquidation_price", 0),
                    collateral=0.0,  # Would need to fetch from account
                    timestamp=datetime.now(),
                    market_index=pos_data.get("market_index"),
                )

                self.positions[key] = position

                logger.debug(
                    f"📊 Position synced: {symbol} {pos_data['side']} {pos_data['size']} "
                    f"@ ${current_price:.2f} | P&L: ${pos_data['unrealized_pnl']:.2f} ({pnl_pct:.2f}%)"
                )

            # Remove closed positions
            aster_symbols = {pos["market"] for pos in positions}
            for key in list(self.positions.keys()):
                if key.startswith("aster:"):
                    symbol = key.split(":")[1]
                    if symbol not in aster_symbols:
                        logger.info(f"🔒 Position closed: {symbol}")
                        del self.positions[key]

        except Exception as e:
            logger.error(f"❌ Failed to sync Aster positions: {e}")

    async def _check_liquidation_risk(self):
        """Check all positions for liquidation risk and send alerts."""
        for key, position in self.positions.items():
            risk = position.risk_level

            if risk == "CRITICAL":
                await self._send_liquidation_alert(position, "CRITICAL")
            elif risk == "HIGH":
                await self._send_liquidation_alert(position, "HIGH")

    async def _send_liquidation_alert(self, position: Position, risk_level: str):
        """Send liquidation risk alert via Telegram."""
        try:
            from .telegram_enhanced import get_telegram_enhanced

            tg = get_telegram_enhanced()

            risk_emoji = "🚨" if risk_level == "CRITICAL" else "⚠️"
            side_emoji = "🟢" if position.side == "long" else "🔴"

            message = f"""
{risk_emoji} *LIQUIDATION RISK ALERT*

*Position:* {side_emoji} {position.side.upper()} {position.symbol}
*Platform:* {position.platform.value}
*Size:* {position.size:.4f}
*Entry:* ${position.entry_price:.4f}
*Current:* ${position.current_price:.4f}
*Liquidation:* ${position.liquidation_price:.4f}

*P&L:* ${position.unrealized_pnl:.2f} ({position.unrealized_pnl_pct:+.2f}%)
*Risk Level:* *{risk_level}*
*Distance to Liq:* {position.liquidation_distance_pct:.2f}%

{"🚨 *ACTION REQUIRED: Consider closing or adding collateral!*" if risk_level == "CRITICAL" else "⚠️ Monitor closely"}
"""

            await tg.send(message)
            logger.warning(
                f"{risk_emoji} Liquidation risk alert sent: {position.symbol} ({risk_level})"
            )

        except Exception as e:
            logger.error(f"Failed to send liquidation alert: {e}")

    def get_position(self, platform: PlatformType, symbol: str) -> Optional[Position]:
        """Get a specific position."""
        key = f"{platform.value}:{symbol}"
        return self.positions.get(key)

    def get_all_positions(self) -> List[Position]:
        """Get all open positions."""
        return list(self.positions.values())

    def get_total_pnl(self) -> float:
        """Get total unrealized P&L across all positions."""
        return sum(pos.unrealized_pnl for pos in self.positions.values())

    def get_total_pnl_pct(self) -> float:
        """Get average P&L percentage across all positions."""
        if not self.positions:
            return 0.0
        return sum(pos.unrealized_pnl_pct for pos in self.positions.values()) / len(
            self.positions
        )

    async def send_daily_summary(self):
        """Send daily summary of all positions and P&L."""
        try:
            from .telegram_enhanced import get_telegram_enhanced

            tg = get_telegram_enhanced()

            positions = self.get_all_positions()
            total_pnl = self.get_total_pnl()
            avg_pnl_pct = self.get_total_pnl_pct()

            if not positions:
                message = "📊 *Daily Position Summary*\n\nNo open perpetual positions."
                await tg.send(message)
                return

            # Build summary
            message = f"""
📊 *Daily Position Summary*

*Total Positions:* {len(positions)}
*Total P&L:* ${total_pnl:.2f} ({avg_pnl_pct:+.2f}% avg)

"""

            for pos in positions:
                side_emoji = "🟢" if pos.side == "long" else "🔴"
                pnl_emoji = "✅" if pos.is_profitable else "❌"

                message += f"""
{side_emoji} *{pos.symbol}* ({pos.platform.value})
├ Side: {pos.side.upper()} {pos.size:.4f}
├ Entry: ${pos.entry_price:.4f}
├ Current: ${pos.current_price:.4f}
├ P&L: {pnl_emoji} ${pos.unrealized_pnl:.2f} ({pos.unrealized_pnl_pct:+.2f}%)
└ Risk: {pos.risk_level}

"""

            await tg.send(message)
            logger.info("📧 Daily position summary sent")

        except Exception as e:
            logger.error(f"Failed to send daily summary: {e}")


# Singleton
_position_monitor: Optional[PositionMonitor] = None


def get_position_monitor(sapphire_service) -> PositionMonitor:
    """Get or create PositionMonitor singleton."""
    global _position_monitor
    if not _position_monitor:
        _position_monitor = PositionMonitor(sapphire_service)
    return _position_monitor
