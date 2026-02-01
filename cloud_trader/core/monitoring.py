"""
Sapphire V2 Monitoring Service
Unified engine for metrics, notifications, and agent tracking.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..config import Settings
from ..enhanced_telegram import EnhancedTelegramService, NotificationPriority

logger = logging.getLogger(__name__)


@dataclass
class AgentKPI:
    """Key Performance Indicators for a specific agent."""

    agent_id: str
    name: str
    trades: int = 0
    wins: int = 0
    total_pnl: float = 0.0
    volume: float = 0.0
    last_confidence: float = 0.0
    health: str = "INITIALIZING"

    @property
    def win_rate(self) -> float:
        return (self.wins / self.trades) if self.trades > 0 else 0.0


class MonitoringService:
    """
    Central monitoring and notification engine.

    Responsibilities:
    - Telegram notifications (dispatching)
    - Agent performance tracking (KPIs)
    - System health monitoring (Sentinel)
    - Prometheus metrics gateway
    """

    def __init__(self, settings: Settings, position_tracker=None):
        self.settings = settings
        self._telegram = None
        self._agent_kpis: Dict[str, AgentKPI] = {}
        self._start_time = time.time()
        self._running = False
        self._sentinel_task: Optional[asyncio.Task] = None
        self._position_tracker = position_tracker  # For PnL updates

        # Initialize Telegram if enabled
        if self.settings.telegram_bot_token and self.settings.telegram_chat_id:
            self._telegram = EnhancedTelegramService(
                bot_token=self.settings.telegram_bot_token,
                chat_id=self.settings.telegram_chat_id,
                command_callback=self._handle_telegram_command
            )
            logger.info("📢 Telegram notifications configured with interactive commands")
        else:
            logger.warning("⚠️ Telegram notifications DISABLED (missing credentials)")

    def set_position_tracker(self, tracker):
        """Set the position tracker for PnL updates."""
        self._position_tracker = tracker

    async def start(self):
        """Start monitoring background tasks."""
        if self._running:
            return

        self._running = True
        if self._telegram:
            await self._telegram.start()
            logger.info("✅ Telegram service started with interactive commands")

        # Start the Sentinel (heartbeat and health check)
        self._sentinel_task = asyncio.create_task(self._sentinel_loop())
        logger.info("🛡️ Monitoring Sentinel started")

    async def stop(self):
        """Stop monitoring."""
        self._running = False
        if self._sentinel_task:
            self._sentinel_task.cancel()
        if self._telegram:
            await self._telegram.stop()
        logger.info("🛑 Monitoring Service stopped")

    async def _sentinel_loop(self):
        """Background loop for heartbeats and periodic summaries."""
        last_summary_time = time.time()
        last_pnl_update_time = time.time()
        pnl_update_interval = 1800  # 30 minutes for PnL updates

        while self._running:
            try:
                # Summary interval (default: 1 hour)
                interval = self.settings.telegram_summary_interval_seconds or 3600
                await asyncio.sleep(min(300, interval // 12))  # Check every 5 minutes

                current_time = time.time()
                uptime = current_time - self._start_time

                # Send heartbeat log
                logger.info(f"💓 Sentinel Heartbeat | Uptime: {uptime/3600:.1f}h")

                # Send PnL update every 30 minutes if we have positions
                if (current_time - last_pnl_update_time) >= pnl_update_interval:
                    await self._send_pnl_update()
                    last_pnl_update_time = current_time

                # Send periodic summary if interval elapsed
                if (current_time - last_summary_time) >= interval:
                    await self._send_periodic_summary()
                    last_summary_time = current_time

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Sentinel error: {e}")
                await asyncio.sleep(60)

    async def _send_pnl_update(self):
        """Send real-time PnL update for open positions."""
        if not self._telegram or not self._position_tracker:
            return

        try:
            positions = await self._position_tracker.get_all()
            if not positions:
                return

            # Build position list with PnL info
            pos_list = []
            total_unrealized = 0.0

            for symbol, pos in positions.items():
                entry_price = pos.get("entry_price", 0)
                current_price = pos.get("current_price", 0)
                side = pos.get("side", "BUY")

                if entry_price > 0 and current_price > 0:
                    if side in ["BUY", "LONG"]:
                        pnl_pct = ((current_price - entry_price) / entry_price) * 100
                    else:
                        pnl_pct = ((entry_price - current_price) / entry_price) * 100
                else:
                    pnl_pct = 0

                unrealized = pos.get("unrealized_pnl", 0)
                total_unrealized += unrealized

                pos_list.append({
                    "symbol": symbol,
                    "side": side,
                    "entry_price": entry_price,
                    "current_price": current_price,
                    "pnl_pct": pnl_pct,
                    "trailing_stop_active": pos.get("trailing_stop_active", False),
                })

            # Sort by absolute PnL (most significant first)
            pos_list.sort(key=lambda x: abs(x["pnl_pct"]), reverse=True)

            await self._telegram.send_position_pnl_update(
                positions=pos_list,
                total_unrealized_pnl=total_unrealized,
            )
            logger.info(f"📊 Sent PnL update for {len(pos_list)} positions")

        except Exception as e:
            logger.warning(f"Failed to send PnL update: {e}")

    async def _send_periodic_summary(self):
        """Send hourly/periodic performance summary via Telegram."""
        if not self._telegram:
            return

        # Calculate metrics
        uptime = time.time() - self._start_time
        uptime_str = f"{uptime/3600:.1f}h"

        # Aggregate agent metrics
        total_trades = sum(kpi.trades for kpi in self._agent_kpis.values())
        total_volume = sum(kpi.volume for kpi in self._agent_kpis.values())
        total_pnl = sum(kpi.total_pnl for kpi in self._agent_kpis.values())
        avg_win_rate = sum(kpi.win_rate for kpi in self._agent_kpis.values()) / max(
            len(self._agent_kpis), 1
        )

        metrics = {
            "total_pnl": total_pnl,
            "volume": total_volume,
            "trades": total_trades,
            "win_rate": avg_win_rate,
        }

        # AI Commentary based on performance
        if total_trades == 0:
            commentary = "No trades executed this period. Agents holding positions, waiting for optimal market conditions."
        elif avg_win_rate >= 60:
            commentary = "Exceptional performance! Agents are efficiently capturing alpha in current market regime."
        elif avg_win_rate >= 50:
            commentary = "Solid performance. Strategy alignment is working as expected."
        else:
            commentary = "Below-target win rate detected. Consider reviewing agent parameters or market conditions."

        interval_hours = (self.settings.telegram_summary_interval_seconds or 3600) / 3600
        period_name = (
            f"{interval_hours:.0f}-Hour"
            if interval_hours >= 1
            else f"{interval_hours*60:.0f}-Minute"
        )

        try:
            await self._telegram.send_performance_summary(
                period=period_name, metrics=metrics, ai_commentary=commentary
            )
            logger.info(f"📊 Sent {period_name} performance summary via Telegram")
        except Exception as e:
            logger.error(f"Failed to send periodic summary: {e}")

    # --- Notification Dispatchers ---

    async def notify_trade(self, trade_data: Dict[str, Any]):
        """Dispatch trade notification."""
        # Update agent KPIs
        agent_id = trade_data.get("agent_id", "unknown")
        if agent_id not in self._agent_kpis:
            self._agent_kpis[agent_id] = AgentKPI(agent_id, trade_data.get("agent_name", agent_id))

        kpi = self._agent_kpis[agent_id]
        kpi.trades += 1
        kpi.volume += trade_data.get("quantity", 0) * trade_data.get("price", 0)

        if self._telegram:
            await self._telegram.send_trade_notification(**trade_data)

    async def notify_alert(
        self, title: str, message: str, priority: NotificationPriority = NotificationPriority.HIGH
    ):
        """Dispatch high-priority alert."""
        text = f"🚨 *{title}*\n{message}"
        if self._telegram:
            await self._telegram.send_message(text, priority=priority)
        logger.warning(f"⚠️ ALERT: {title} - {message}")

    async def notify_status(self, status_data: Dict[str, Any]):
        """Dispatch system status update."""
        if self._telegram:
            await self._telegram.send_status_update(status_data)

    # --- Tracking & Metrics ---

    def register_agent(self, agent_id: str, name: str):
        """Register an agent for KPI tracking."""
        if agent_id not in self._agent_kpis:
            self._agent_kpis[agent_id] = AgentKPI(agent_id, name)
            logger.info(f"📈 Registered agent {name} for tracking")

    def get_agent_metrics(self) -> List[Dict[str, Any]]:
        """Return metrics for all tracked agents."""
        return [
            {
                "agent_id": kpi.agent_id,
                "name": kpi.name,
                "trades": kpi.trades,
                "win_rate": kpi.win_rate,
                "volume": kpi.volume,
                "pnl": kpi.total_pnl,
                "health": kpi.health,
            }
            for kpi in self._agent_kpis.values()
        ]

    def report_cycle(self, result: Any):
        """Report results of a trading cycle for metrics."""
        # TODO: Update Prometheus metrics
        pass

    async def _handle_telegram_command(self, platform: str, symbol: str, action: str, quantity: float):
        """
        Handle interactive Telegram commands.

        Args:
            platform: Target platform (drift, jupiter, aster, hyperliquid, symphony, all)
            symbol: Trading symbol (e.g., SOL, BTC)
            action: Action to perform (BUY, SELL, CLOSE, STATUS)
            quantity: Trade quantity (0 for status commands)
        """
        logger.info(f"📲 Telegram command received: @{platform} {action} {quantity} {symbol}")

        # For status commands
        if action == "STATUS":
            await self._handle_status_command(platform, symbol)
            return

        # For trading commands - route to platform trader
        # This will be implemented when platform traders have command endpoints
        try:
            # Placeholder for now - will integrate with platform router
            if self._telegram:
                await self._telegram.send_message(
                    f"⚠️ **Command Received**\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"Platform: `{platform}`\n"
                    f"Action: `{action}`\n"
                    f"Symbol: `{symbol}`\n"
                    f"Quantity: `{quantity}`\n\n"
                    f"Manual trading commands will be enabled in next update.\n"
                    f"For now, please use the platform UIs directly.",
                    priority=NotificationPriority.HIGH
                )
        except Exception as e:
            logger.error(f"Error handling telegram command: {e}")
            if self._telegram:
                await self._telegram.send_message(
                    f"❌ Error processing command: {e}",
                    priority=NotificationPriority.HIGH
                )

    async def _handle_status_command(self, platform: str, symbol: str):
        """Handle status command for a platform."""
        try:
            # Gather status information
            uptime_seconds = time.time() - self._start_time
            uptime_hours = uptime_seconds / 3600

            if platform.lower() == "all":
                # Status for all platforms
                metrics = self.get_agent_metrics()
                total_trades = sum(m["trades"] for m in metrics)
                avg_win_rate = sum(m["win_rate"] for m in metrics) / len(metrics) if metrics else 0

                status_msg = (
                    f"📊 **ALL PLATFORMS STATUS**\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"⏱️ **Uptime**: `{uptime_hours:.1f}h`\n"
                    f"🤖 **Active Agents**: `{len(metrics)}`\n"
                    f"📈 **Total Trades**: `{total_trades}`\n"
                    f"🎯 **Avg Win Rate**: `{avg_win_rate*100:.1f}%`\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                )

                for m in metrics:
                    status_emoji = "🟢" if m["health"] == "HEALTHY" else "🟡" if m["health"] == "DEGRADED" else "🔴"
                    status_msg += f"{status_emoji} `{m['name']}`: {m['trades']} trades, {m['win_rate']*100:.1f}% WR\n"

            else:
                # Status for specific platform
                platform_emoji = {
                    "drift": "🌊",
                    "hyperliquid": "💧",
                    "aster": "⭐",
                    "symphony": "🎵",
                    "lighter": "⚡",
                    "jupiter": "🪐"
                }.get(platform.lower(), "🤖")

                # Find platform-specific metrics
                platform_agents = [
                    kpi for kpi in self._agent_kpis.values()
                    if platform.lower() in kpi.name.lower()
                ]

                if platform_agents:
                    kpi = platform_agents[0]
                    status_msg = (
                        f"{platform_emoji} **{platform.upper()} STATUS**\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"🤖 **Agent**: `{kpi.name}`\n"
                        f"📈 **Trades**: `{kpi.trades}`\n"
                        f"🎯 **Win Rate**: `{kpi.win_rate*100:.1f}%`\n"
                        f"💰 **PnL**: `${kpi.total_pnl:+,.2f}`\n"
                        f"📊 **Volume**: `${kpi.volume:,.0f}`\n"
                        f"🏥 **Health**: `{kpi.health}`\n"
                        f"⏱️ **Uptime**: `{uptime_hours:.1f}h`"
                    )
                else:
                    status_msg = (
                        f"{platform_emoji} **{platform.upper()} STATUS**\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"ℹ️ No active trading agent for this platform.\n"
                        f"Platform may be disabled or initializing."
                    )

            if self._telegram:
                await self._telegram.send_message(status_msg, priority=NotificationPriority.MEDIUM)

        except Exception as e:
            logger.error(f"Error handling status command: {e}")
            if self._telegram:
                await self._telegram.send_message(
                    f"❌ Error getting status: {e}",
                    priority=NotificationPriority.HIGH
                )
