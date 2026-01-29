"""
Jupiter Integration for Sapphire Trading System
Connects Jupiter price feeds with existing traders and Telegram alerts
"""

import asyncio
from decimal import Decimal
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
import sys
from pathlib import Path

# Add cloud_trader to path for Telegram integration
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "cloud_trader"))

from jupiter_client import JupiterClient
from jupiter_trader import JupiterTrader, TradingConfig, RiskLevel
from enhanced_telegram import EnhancedTelegramService, NotificationPriority
from solders.keypair import Keypair
import base58
from loguru import logger


@dataclass
class PriceAlert:
    """Price alert configuration"""
    token: str
    condition: str  # "above", "below", "change_pct"
    threshold: Decimal
    triggered: bool = False
    last_trigger_time: Optional[datetime] = None
    cooldown_minutes: int = 60


class JupiterSapphireIntegration:
    """
    Integrates Jupiter with Sapphire trading system
    - Real-time price feeds to all traders
    - Telegram alerts for price moves
    - Coordinated trading signals
    """

    def __init__(
        self,
        jupiter_api_key: str,
        solana_private_key_b58: str,
        telegram_bot_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        trading_config: Optional[TradingConfig] = None,
    ):
        """
        Initialize Jupiter-Sapphire integration

        Args:
            jupiter_api_key: Jupiter API key
            solana_private_key_b58: Solana private key (base58)
            telegram_bot_token: Telegram bot token (optional)
            telegram_chat_id: Telegram chat ID (optional)
            trading_config: Trading configuration for Jupiter trader
        """
        # Initialize Jupiter client
        private_bytes = base58.b58decode(solana_private_key_b58)
        keypair = Keypair.from_bytes(private_bytes)

        self.jupiter_client = JupiterClient(
            api_key=jupiter_api_key,
            keypair=keypair,
        )

        # Initialize Jupiter trader if config provided
        self.jupiter_trader = None
        if trading_config:
            self.jupiter_trader = JupiterTrader(
                jupiter_api_key=jupiter_api_key,
                private_key_hex=solana_private_key_b58,
                config=trading_config,
            )

        # Initialize Telegram if credentials provided
        self.telegram = None
        if telegram_bot_token and telegram_chat_id:
            self.telegram = EnhancedTelegramService(
                bot_token=telegram_bot_token,
                chat_id=telegram_chat_id,
            )

        # Price tracking
        self.current_prices: Dict[str, Decimal] = {}
        self.price_history: Dict[str, List[Dict]] = {}

        # Alert management
        self.price_alerts: List[PriceAlert] = []

        # Callbacks for price updates
        self.price_update_callbacks: List[Callable] = []

        logger.info("✅ Jupiter-Sapphire Integration initialized")

    async def start(self):
        """Start the integration services"""
        if self.telegram:
            await self.telegram.start()
            # Mask wallet address for security
            wallet_addr = str(self.jupiter_client.keypair.pubkey())
            masked_wallet = f"{wallet_addr[:4]}...{wallet_addr[-4:]}"
            await self.send_telegram(
                "🚀 Jupiter Integration Started\n"
                f"Wallet: {masked_wallet}\n"
                "Real-time price monitoring active",
                priority=NotificationPriority.HIGH,
            )

    async def send_telegram(
        self,
        message: str,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
    ):
        """Send Telegram notification"""
        if self.telegram:
            await self.telegram.send_message(message, priority=priority)
        else:
            logger.info(f"[Telegram] {message}")

    async def get_jupiter_prices(self) -> Dict[str, Decimal]:
        """Fetch current prices from Jupiter"""
        prices = await self.jupiter_client.get_multiple_prices([
            self.jupiter_client.SOL_MINT,
            self.jupiter_client.ETH_MINT,
            self.jupiter_client.WBTC_MINT,
            self.jupiter_client.USDC_MINT,
        ])

        return {
            "SOL": prices[self.jupiter_client.SOL_MINT],
            "ETH": prices[self.jupiter_client.ETH_MINT],
            "wBTC": prices[self.jupiter_client.WBTC_MINT],
            "USDC": prices[self.jupiter_client.USDC_MINT],
        }

    async def update_prices(self):
        """Update prices and trigger callbacks"""
        try:
            new_prices = await self.get_jupiter_prices()

            # Store previous prices for change detection
            old_prices = self.current_prices.copy()

            # Update current prices
            self.current_prices = new_prices

            # Add to history
            timestamp = datetime.now()
            for token, price in new_prices.items():
                if token not in self.price_history:
                    self.price_history[token] = []

                self.price_history[token].append({
                    "timestamp": timestamp,
                    "price": price,
                })

                # Keep only last 1000 data points
                if len(self.price_history[token]) > 1000:
                    self.price_history[token] = self.price_history[token][-1000:]

            # Check for significant price moves
            await self.check_price_alerts(old_prices, new_prices)

            # Trigger callbacks for other traders
            for callback in self.price_update_callbacks:
                try:
                    await callback(new_prices)
                except Exception as e:
                    logger.error(f"Error in price update callback: {e}")

        except Exception as e:
            logger.error(f"Error updating prices: {e}")

    async def check_price_alerts(
        self,
        old_prices: Dict[str, Decimal],
        new_prices: Dict[str, Decimal],
    ):
        """Check and trigger price alerts"""
        for alert in self.price_alerts:
            if alert.token not in new_prices:
                continue

            # Check cooldown
            if alert.last_trigger_time:
                elapsed = datetime.now() - alert.last_trigger_time
                if elapsed < timedelta(minutes=alert.cooldown_minutes):
                    continue

            current_price = new_prices[alert.token]
            should_trigger = False
            message = ""

            if alert.condition == "above" and current_price > alert.threshold:
                should_trigger = True
                message = (
                    f"📈 {alert.token} Price Alert!\n"
                    f"Price: ${current_price:,.2f}\n"
                    f"Above threshold: ${alert.threshold:,.2f}"
                )

            elif alert.condition == "below" and current_price < alert.threshold:
                should_trigger = True
                message = (
                    f"📉 {alert.token} Price Alert!\n"
                    f"Price: ${current_price:,.2f}\n"
                    f"Below threshold: ${alert.threshold:,.2f}"
                )

            elif alert.condition == "change_pct" and alert.token in old_prices:
                change_pct = abs(
                    ((current_price - old_prices[alert.token]) / old_prices[alert.token])
                    * 100
                )
                if change_pct >= alert.threshold:
                    should_trigger = True
                    direction = "📈" if current_price > old_prices[alert.token] else "📉"
                    message = (
                        f"{direction} {alert.token} Price Move!\n"
                        f"Change: {change_pct:+.2f}%\n"
                        f"Price: ${current_price:,.2f}"
                    )

            if should_trigger:
                await self.send_telegram(message, priority=NotificationPriority.HIGH)
                alert.triggered = True
                alert.last_trigger_time = datetime.now()

    def add_price_alert(
        self,
        token: str,
        condition: str,
        threshold: Decimal,
        cooldown_minutes: int = 60,
    ):
        """Add a price alert"""
        alert = PriceAlert(
            token=token,
            condition=condition,
            threshold=threshold,
            cooldown_minutes=cooldown_minutes,
        )
        self.price_alerts.append(alert)
        logger.info(f"Added price alert: {token} {condition} {threshold}")

    def register_price_callback(self, callback: Callable):
        """Register a callback for price updates"""
        self.price_update_callbacks.append(callback)

    async def get_trading_signal(self, token: str) -> Optional[str]:
        """
        Generate simple trading signal based on recent price action

        Returns: "BUY", "SELL", or None
        """
        if token not in self.price_history or len(self.price_history[token]) < 20:
            return None

        # Get recent prices
        recent = self.price_history[token][-20:]
        prices = [float(p["price"]) for p in recent]

        # Simple momentum signal
        short_ma = sum(prices[-5:]) / 5  # 5-period MA
        long_ma = sum(prices) / 20  # 20-period MA

        if short_ma > long_ma * 1.01:  # 1% above
            return "BUY"
        elif short_ma < long_ma * 0.99:  # 1% below
            return "SELL"

        return None

    async def run_price_monitoring(self, interval_seconds: int = 60):
        """Run continuous price monitoring"""
        logger.info(f"Starting price monitoring (interval: {interval_seconds}s)")

        while True:
            try:
                await self.update_prices()

                # Log current prices
                for token, price in self.current_prices.items():
                    logger.info(f"{token}: ${price:,.2f}")

                await asyncio.sleep(interval_seconds)

            except KeyboardInterrupt:
                logger.info("Stopping price monitoring...")
                break
            except Exception as e:
                logger.error(f"Error in price monitoring: {e}")
                await asyncio.sleep(interval_seconds)

    async def close(self):
        """Close all connections"""
        await self.jupiter_client.close()
        if self.jupiter_trader:
            await self.jupiter_trader.close()


# Example usage
async def example_integration():
    """Example: Integrate Jupiter with Sapphire + Telegram alerts"""

    # Your credentials
    JUPITER_API_KEY = "d1302809-3996-4ceb-aad0-7da8a71d6149"
    SOLANA_PRIVATE_KEY = "5tg6XZMb96ZcGAip6jnpRmxWfQxNASr6tM9C8LmKxhhMC6gKEtsvQPdzhmMogrrbcf8wjTwyWnsfD12NjXJfeZc8"
    TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"  # Get from @BotFather
    TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"  # Get from @userinfobot

    # Trading config for $50 capital
    config = TradingConfig(
        total_capital_usd=Decimal("50"),
        risk_level=RiskLevel.CONSERVATIVE,
        max_daily_trades=5,
    )

    # Initialize integration
    integration = JupiterSapphireIntegration(
        jupiter_api_key=JUPITER_API_KEY,
        solana_private_key_b58=SOLANA_PRIVATE_KEY,
        telegram_bot_token=TELEGRAM_BOT_TOKEN,
        telegram_chat_id=TELEGRAM_CHAT_ID,
        trading_config=config,
    )

    await integration.start()

    # Add price alerts
    integration.add_price_alert("SOL", "above", Decimal("130"), cooldown_minutes=30)
    integration.add_price_alert("SOL", "below", Decimal("125"), cooldown_minutes=30)
    integration.add_price_alert("SOL", "change_pct", Decimal("2.0"), cooldown_minutes=15)

    # Register callback for other traders
    async def hyperliquid_price_update(prices):
        logger.info(f"Hyperliquid received price update: {prices}")
        # Send to Hyperliquid trader...

    integration.register_price_callback(hyperliquid_price_update)

    # Run monitoring
    await integration.run_price_monitoring(interval_seconds=60)

    await integration.close()


if __name__ == "__main__":
    asyncio.run(example_integration())
