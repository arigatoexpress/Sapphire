import asyncio
import logging
import os
from datetime import datetime

import google.generativeai as genai

logger = logging.getLogger(__name__)


class GeminiGuard:
    """
    AI Sentinel using Gemini 1.5 Flash to validate market conditions.
    """

    def __init__(self, telegram_bot=None):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.telegram = telegram_bot
        self.model = None
        self.running = False

        if self.api_key:
            try:
                genai.configure(api_key=self.api_key)
                # Initialize Models
                self.pro_model = genai.GenerativeModel("gemini-3-pro-preview")
                self.flash_model = genai.GenerativeModel("gemini-3-flash-preview")
                logger.info("✅ Gemini 3.0 (Pro & Flash) Initialized")
            except Exception as e:
                logger.error(f"❌ Failed to init Gemini: {e}")
        else:
            logger.warning("⚠️ GEMINI_API_KEY not found. AI features disabled.")

    async def force_analyze(self, analysis_type: str = "recap"):
        """Force an immediate AI analysis (public method)."""
        logger.info(f"🧠 Forced AI Analysis: {analysis_type}")
        if analysis_type == "recap":
            await self._generate_hourly_recap()
        elif analysis_type == "full":
            await self._generate_daily_recap()
        else:
            insight = await self._quick_check()
            if insight and self.telegram:
                await self.telegram.send_message(
                    f"⚡ **Instant Flash Insight**: {insight}", priority="medium"
                )

    async def start(self):
        """Start the periodic AI analysis loop."""
        if not self.flash_model:
            return

        self.running = True
        logger.info("🧠 Gemini Guard Active - Monitoring Market with Gemini 3.0...")

        self.trade_history = []
        self.last_hourly_recap = datetime.now()
        self.last_daily_recap = datetime.now()

        while self.running:
            try:
                now = datetime.now()

                # 1. Quick Market Check (Flash)
                flash_insight = await self._quick_check()
                if flash_insight and self.telegram:
                    await self.telegram.send_message(
                        f"⚡ **Gemini Flash**: {flash_insight}", priority="low"
                    )

                # 2. Hourly Recap
                if (now - self.last_hourly_recap).total_seconds() > 3600:
                    await self._generate_hourly_recap()
                    self.last_hourly_recap = now

                # 3. Daily Recap
                if (now - self.last_daily_recap).total_seconds() > 86400:
                    await self._generate_daily_recap()
                    self.last_daily_recap = now

                # Run every 5 minutes
                await asyncio.sleep(300)
            except Exception as e:
                logger.error(f"Gemini Guard Error: {e}")
                await asyncio.sleep(60)

    def log_trade(self, trade_data):
        """Log a trade for AI analysis."""
        self.trade_history.append({"timestamp": datetime.now().isoformat(), **trade_data})
        # Keep last 1000 trades to save memory
        if len(self.trade_history) > 1000:
            self.trade_history = self.trade_history[-1000:]

    async def _generate_hourly_recap(self):
        """Generate hourly recap using Gemini Pro."""
        if not self.pro_model or not self.trade_history:
            return

        recent_trades = [
            t
            for t in self.trade_history
            if (datetime.now() - datetime.fromisoformat(t["timestamp"])).total_seconds() < 3600
        ]
        if not recent_trades:
            return

        prompt = (
            f"You are a professional trading systems analyst. Analyze these {len(recent_trades)} recent trades:\n"
            f"{str(recent_trades[-20:])}\n"  # Send last 20 for context
            "Provide a concise, professional Hourly Performance Recap. "
            "Focus on execution efficiency, win rate (if deducible), and strategy alignment. "
            "Format clearly with Markdown."
        )

        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None, lambda: self.pro_model.generate_content(prompt)
            )
            if response and self.telegram:
                await self.telegram.send_message(
                    f"📊 **Hourly AI Recap**\n\n{response.text}", priority="medium"
                )
        except Exception as e:
            logger.error(f"Hourly Recap Failed: {e}")

    async def _generate_daily_recap(self):
        """Generate daily recap using Gemini Pro."""
        if not self.pro_model:
            return

        prompt = (
            "You are a Chief Investment Officer AI. Provide a Daily System Status Report. "
            "Summarize the day's trading activity, system stability, and risk outlook. "
            "Maintain a highly professional, executive tone. Use Markdown."
        )

        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None, lambda: self.pro_model.generate_content(prompt)
            )
            if response and self.telegram:
                await self.telegram.send_message(
                    f"📑 **Daily Executive Brief**\n\n{response.text}", priority="high"
                )
        except Exception as e:
            logger.error(f"Daily Recap Failed: {e}")

    async def _quick_check(self):
        """Quick market sentiment check using Flash."""
        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, self._generate_flash)
            return response.text if response else None
        except Exception as e:
            logger.error(f"Flash generation failed: {e}")
            return None

    async def _deep_analysis(self):
        """Deep strategic analysis using Pro."""
        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, self._generate_pro)
            return response.text if response else None
        except Exception as e:
            logger.error(f"Pro generation failed: {e}")
            return None

    def _generate_flash(self):
        prompt = "You are a high-frequency trading sentinel. Briefly confirm if market conditions (volatility, volume) appear safe for arbitrage. One sentence."
        return self.flash_model.generate_content(prompt)

    def _generate_pro(self):
        prompt = "You are a strategic trading orchestrator. Analyze the concept of cross-exchange arbitrage in current crypto markets and provide one strategic recommendation for risk management. One sentence."
        return self.pro_model.generate_content(prompt)

    async def stop(self):
        self.running = False
