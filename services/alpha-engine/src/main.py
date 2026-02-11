import asyncio
import os
import signal
import sys
import time
from collections import defaultdict
from typing import Any, Dict, List, Set

import uvloop
from src.ai.gemini_guard import GeminiGuard
from src.execution.dispatcher import dispatcher
from src.feeds.market_data import MarketDataAggregator
from src.strategy.engine import AlphaStrategyEngine

# Add shared library to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from error_classifier import ErrorSeverity, classify_error
from health import start_health_server
from smart_notifications import notification_manager

# Install uvloop as the default event loop policy
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

# Configure high-performance logging
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO")


class AlphaEngine:
    def __init__(self):
        self.running = False
        self.market_data = MarketDataAggregator()
        self.strategy = AlphaStrategyEngine(self.market_data)

        # Telegram Bot for Notifications & Commands
        from telegram_bot import TelegramPlatformBot

        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        logger.info(f"Alpha Hub: TELEGRAM_BOT_TOKEN is {'set' if token else 'NOT SET'}")
        self.telegram = TelegramPlatformBot(
            bot_token=token, chat_id=chat_id, command_callback=self._handle_telegram_command
        )
        # Initialize Gemini Guard
        self.ai = GeminiGuard(telegram_bot=self.telegram)
        self._heartbeat_task = None
        self._kill_switch_active = False
        self._heartbeat_interval_seconds = int(os.getenv("TELEGRAM_HEARTBEAT_INTERVAL_SECONDS", "900"))
        self._deallocation_failure_threshold = int(os.getenv("DEALLOCATION_FAILURE_THRESHOLD", "3"))
        self._deallocation_cooldown_seconds = int(os.getenv("DEALLOCATION_COOLDOWN_SECONDS", "900"))
        self._default_venue_allocation = max(
            0.0, min(1.0, float(os.getenv("DEFAULT_VENUE_ALLOCATION", "1.0")))
        )
        self._failure_counts: Dict[str, int] = defaultdict(int)
        self._auto_deallocated: Set[str] = set()

    def _normalize_platform(self, platform: str) -> str:
        value = str(platform or "").strip().upper()
        aliases = {
            "HL": "HYPERLIQUID",
            "HYPER": "HYPERLIQUID",
            "LIGHT": "LIGHTER",
            "L2": "LIGHTER",
            "ALL": "ALL",
        }
        return aliases.get(value, value)

    async def _publish_risk_alert(
        self,
        action: str,
        message: str,
        severity: str = "warning",
        alert_type: str = "manual_control",
        platforms: List[str] | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        from models import RiskAlert
        from pubsub.client import publish

        affected = []
        for platform in platforms or []:
            normalized = self._normalize_platform(platform)
            if normalized != "ALL":
                affected.append(normalized.lower())

        alert = RiskAlert(
            alert_id=f"{alert_type}-{int(time.time() * 1000)}",
            severity=severity,
            alert_type=alert_type,
            message=message,
            action=action,
            affected_platforms=affected,
            metadata=metadata or {},
        )
        await publish("risk-alerts", alert)

    async def _activate_kill_switch(self, reason: str) -> None:
        self._kill_switch_active = True
        reason = reason.strip() or "Manual kill switch requested via Telegram"

        for venue in dispatcher.bot_urls:
            dispatcher.set_venue_allocation(venue, 0.0)
            dispatcher.pause_venue(
                venue,
                reason=reason,
                cooldown_seconds=max(self._deallocation_cooldown_seconds, 3600),
            )

        await self._publish_risk_alert(
            action="close_all",
            severity="emergency",
            alert_type="kill_switch",
            message=f"Emergency close requested: {reason}",
            platforms=list(dispatcher.bot_urls.keys()),
            metadata={"source": "telegram", "kill_switch": True},
        )
        await self._publish_risk_alert(
            action="halt_trading",
            severity="emergency",
            alert_type="kill_switch",
            message=f"Trading halted by kill switch: {reason}",
            platforms=list(dispatcher.bot_urls.keys()),
            metadata={"source": "telegram", "kill_switch": True},
        )

        await self.telegram.send_message(
            f"🛑 **KILL SWITCH ACTIVE**\nReason: `{reason}`\nAll venues are halted and deallocated.",
            priority="high",
        )

    async def _resume_from_kill_switch(self, reason: str) -> None:
        self._kill_switch_active = False
        reason = reason.strip() or "Manual resume requested via Telegram"

        for venue in dispatcher.bot_urls:
            dispatcher.resume_venue(venue)
            dispatcher.set_venue_allocation(venue, self._default_venue_allocation)
            self._failure_counts[venue] = 0
            self._auto_deallocated.discard(venue)

        await self._publish_risk_alert(
            action="resume_trading",
            severity="warning",
            alert_type="resume_trading",
            message=f"Trading resumed: {reason}",
            platforms=list(dispatcher.bot_urls.keys()),
            metadata={"source": "telegram", "kill_switch": False},
        )

        await self.telegram.send_message(
            f"✅ **TRADING RESUMED**\nReason: `{reason}`\nDefault allocations restored across all venues.",
            priority="high",
        )

    async def _send_control_status(self) -> None:
        state = dispatcher.get_control_state()
        lines = [
            "📊 **CONTROL STATUS**",
            f"Kill switch: `{'ACTIVE' if self._kill_switch_active else 'INACTIVE'}`",
            "",
        ]
        for venue in sorted(state.keys()):
            item = state[venue]
            status = "PAUSED" if item["paused"] else "LIVE"
            fail_count = self._failure_counts.get(venue, 0)
            lines.append(
                f"- `{venue}` | {status} | alloc `{item['allocation']*100:.0f}%` | failures `{fail_count}`"
            )

        await self.telegram.send_message("\n".join(lines), priority="medium")

    async def _send_heartbeat(self, reason: str) -> None:
        state = dispatcher.get_control_state()
        live = [venue for venue, item in state.items() if not item["paused"] and item["allocation"] > 0]
        paused = [venue for venue, item in state.items() if item["paused"] or item["allocation"] <= 0]
        total_failures = sum(self._failure_counts.values())

        msg = (
            f"💓 **SAPPHIRE HEARTBEAT** (`{reason}`)\n"
            f"Active venues: `{', '.join(live) if live else 'none'}`\n"
            f"Paused/deallocated: `{', '.join(paused) if paused else 'none'}`\n"
            f"Kill switch: `{'ACTIVE' if self._kill_switch_active else 'OFF'}`\n"
            f"Failure pressure: `{total_failures}`\n\n"
            "Reply with `/status`, `/heartbeat`, `/kill`, `/resume`, or `@alpha deallocate <venue>`."
        )
        await self.telegram.send_message(msg, priority="medium")

    async def _handle_control_command(self, target: str, action: str, value: float) -> None:
        normalized_target = self._normalize_platform(target or "ALL")
        normalized_action = action.upper()

        if normalized_action in {"KILL", "HALT", "HALT_TRADING"}:
            await self._activate_kill_switch("Manual command from Telegram")
            return

        if normalized_action in {"RESUME", "RESUME_TRADING"}:
            await self._resume_from_kill_switch("Manual command from Telegram")
            return

        if normalized_action in {"HEARTBEAT", "PING"}:
            await self._send_heartbeat("manual")
            return

        if normalized_action in {"STATUS", "CONTROL_STATUS"}:
            await self._send_control_status()
            return

        if normalized_action == "SET_ALLOCATION":
            allocation = max(0.0, min(1.0, float(value)))
            targets = (
                list(dispatcher.bot_urls.keys())
                if normalized_target == "ALL"
                else [self._normalize_platform(normalized_target)]
            )

            unknown = [venue for venue in targets if venue not in dispatcher.bot_urls]
            if unknown:
                await self.telegram.send_message(
                    f"❌ Unknown venue(s): `{', '.join(unknown)}`", priority="high"
                )
                return

            for venue in targets:
                dispatcher.set_venue_allocation(venue, allocation)
                if allocation <= 0:
                    dispatcher.pause_venue(
                        venue,
                        reason="Manual deallocation via Telegram",
                        cooldown_seconds=max(self._deallocation_cooldown_seconds, 3600),
                    )
                else:
                    dispatcher.resume_venue(venue)
                    self._failure_counts[venue] = 0
                    self._auto_deallocated.discard(venue)

            if allocation <= 0:
                await self._publish_risk_alert(
                    action="halt_trading",
                    severity="warning",
                    alert_type="manual_deallocation",
                    message=f"Manual deallocation: {', '.join(targets)} set to 0%",
                    platforms=targets,
                    metadata={"source": "telegram", "allocation": allocation},
                )
                await self.telegram.send_message(
                    f"🧯 Deallocated `{', '.join(targets)}` to `0%` and halted trading on those venues.",
                    priority="high",
                )
            else:
                await self._publish_risk_alert(
                    action="resume_trading",
                    severity="warning",
                    alert_type="manual_allocation",
                    message=f"Manual allocation update: {', '.join(targets)} set to {allocation*100:.0f}%",
                    platforms=targets,
                    metadata={"source": "telegram", "allocation": allocation},
                )
                await self.telegram.send_message(
                    f"✅ Allocation for `{', '.join(targets)}` set to `{allocation*100:.0f}%`.",
                    priority="high",
                )
            return

        await self.telegram.send_message(
            f"❌ Unknown control action `{normalized_action}`", priority="high"
        )

    async def _record_trade_outcome(self, platform: str, success: bool, error_message: str = "") -> None:
        venue = self._normalize_platform(platform)
        if venue not in dispatcher.bot_urls:
            return

        if success:
            self._failure_counts[venue] = 0
            return

        self._failure_counts[venue] += 1
        failures = self._failure_counts[venue]

        if failures < self._deallocation_failure_threshold:
            return
        if venue in self._auto_deallocated:
            return

        dispatcher.set_venue_allocation(venue, 0.0)
        dispatcher.pause_venue(
            venue,
            reason=f"auto-deallocated after {failures} failures",
            cooldown_seconds=self._deallocation_cooldown_seconds,
        )
        self._auto_deallocated.add(venue)

        await self._publish_risk_alert(
            action="halt_trading",
            severity="critical",
            alert_type="auto_deallocation",
            message=(
                f"{venue} auto-deallocated after {failures} consecutive failures. "
                f"Cooldown {self._deallocation_cooldown_seconds}s."
            ),
            platforms=[venue],
            metadata={
                "source": "alpha-engine",
                "failure_count": failures,
                "last_error": error_message[:200],
            },
        )

        await self.telegram.send_message(
            f"🛑 **AUTO DEALLOCATION**\nVenue: `{venue}`\nFailures: `{failures}`\nCooldown: `{self._deallocation_cooldown_seconds}s`",
            priority="high",
        )

    async def _heartbeat_loop(self) -> None:
        while self.running:
            try:
                await asyncio.sleep(max(60, self._heartbeat_interval_seconds))
                await self._send_heartbeat("scheduled")

                resumed = dispatcher.resume_expired_venues()
                for venue in resumed:
                    if venue in self._auto_deallocated:
                        dispatcher.set_venue_allocation(venue, self._default_venue_allocation)
                        self._auto_deallocated.discard(venue)
                        self._failure_counts[venue] = 0
                        await self._publish_risk_alert(
                            action="resume_trading",
                            severity="warning",
                            alert_type="auto_resume",
                            message=f"{venue} cooldown complete; trading resumed automatically.",
                            platforms=[venue],
                            metadata={"source": "alpha-engine"},
                        )
                        await self.telegram.send_message(
                            f"✅ `{venue}` cooldown complete. Allocation restored to `{self._default_venue_allocation*100:.0f}%`.",
                            priority="medium",
                        )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Heartbeat loop error: {exc}")

    async def _handle_telegram_command(
        self, platform: str, symbol: str, action: str, quantity: float
    ):
        """Callback for Telegram @mentions to trigger manual overrides."""
        logger.warning(f"🚨 TELEGRAM OVERRIDE: {platform} {action} {quantity} {symbol}")
        normalized_platform = self._normalize_platform(platform)

        if normalized_platform == "CONTROL":
            await self._handle_control_command(symbol, action, quantity)
            return

        # intercept AI commands
        if platform.lower() == "alpha" and action.lower() in ("recap", "analyze", "report"):
            await self.telegram.send_message("🧠 **Processing AI Request...**", priority="medium")
            analysis_type = "full" if action.lower() == "report" else "recap"
            await self.ai.force_analyze(analysis_type)
            return

        if self._kill_switch_active:
            await self.telegram.send_message(
                "🛑 Kill switch is active. Use `/resume` before dispatching manual trades.",
                priority="high",
            )
            return

        # Dispatch command via ExecutionDispatcher
        await dispatcher.send_command(
            platform,
            {
                "action": action,
                "symbol": symbol,
                "quantity": quantity,
                "source": "telegram_override",
            },
        )

    async def start(self):
        logger.info("🚀 Sapphire Alpha Engine Starting (uvloop enabled)")
        self.running = True

        # Start Health Server (Cloud Run)
        await start_health_server()

        # 1. Start Telegram FIRST for immediate status
        logger.info("📡 Initializing Telegram Notification Task...")
        asyncio.create_task(
            self.telegram.send_message("💎 Sapphire Alpha Hub Online & Listening", priority="high")
        )
        asyncio.create_task(self.telegram.start_listener())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # 2. Start Pub/Sub Listener for Trade Results
        asyncio.create_task(self._listen_for_trades())

        # 3. Start Gemini Guard
        asyncio.create_task(self.ai.start())

        # 4. Start Feeds, Strategy, Dispatcher
        await dispatcher.start()
        await self.market_data.start()
        await self.strategy.start()

        # Keep-alive loop
        while self.running:
            await asyncio.sleep(1)

    async def _listen_for_trades(self):
        """Listen for trade execution results from all bots."""
        from pubsub.client import subscribe

        logger.info("👂 Initializing Pub/Sub 'trade-executed' listener...")

        async def handle_trade(message_data: dict):
            try:
                # Log to AI for Recaps
                self.ai.log_trade(message_data)

                # Format notification
                platform = message_data.get("platform", "Unknown")
                symbol = message_data.get("symbol", "N/A")
                success = message_data.get("success", False)
                side = message_data.get("side", "N/A")
                qty = message_data.get("filled_quantity", 0)

                if success:
                    msg = f"✅ TRADE EXECUTED: {platform} | {side} {qty} {symbol}"
                    # Use LOW priority to batch execution updates
                    await self.telegram.send_message(msg, priority="low")
                    await self._record_trade_outcome(platform, success=True)
                else:
                    err = message_data.get("error_message", "Unknown")
                    await self._record_trade_outcome(platform, success=False, error_message=err)

                    # Classify the error
                    category, severity = classify_error(err)

                    # Check if we should notify
                    should_notify = notification_manager.should_notify(err, category, severity)

                    if should_notify:
                        msg = f"❌ TRADE FAILED: {platform} | {side} {symbol} | Error: {err}"

                        # Use appropriate priority based on severity
                        priority = "high" if severity >= ErrorSeverity.ERROR else "medium"
                        await self.telegram.send_message(msg, priority=priority)
                        logger.warning(msg)
                    else:
                        # Log but don't spam Telegram
                        logger.info(
                            f"⚠️ Expected/deduplicated failure: {platform} | {side} {symbol} | {err}"
                        )
            except Exception as e:
                logger.error(f"Error in trade result handler: {e}")

        await subscribe("trade-executed", handle_trade)

    async def stop(self):
        logger.info("🛑 Stopping Alpha Engine...")
        self.running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        await self.market_data.stop()
        await self.strategy.stop()
        await dispatcher.stop()
        await self.ai.stop()  # Stop AI loop


async def main():
    engine = AlphaEngine()

    def handle_sig(sig, frame):
        asyncio.create_task(engine.stop())

    signal.signal(signal.SIGTERM, handle_sig)
    signal.signal(signal.SIGINT, handle_sig)

    await engine.start()


if __name__ == "__main__":
    asyncio.run(main())
