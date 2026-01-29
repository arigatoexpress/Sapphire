"""
Jupiter Trader - Unified Integration for Sapphire Cloud Trader
Integrates Jupiter Ultra Swap API with the Sapphire trading system.

Features:
- Spot swaps with best price aggregation
- Real-time price monitoring
- Trade verification via Solana RPC
- Position tracking
- Telegram notifications
"""

import asyncio
import sys
from decimal import Decimal
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

# Add bot-jupiter to path
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "bot-jupiter"))

from loguru import logger
from solders.keypair import Keypair
import base58

from jupiter_client import JupiterClient, SwapResult
from jupiter_integration import JupiterSapphireIntegration

# Optional HFT strategy (requires finta, talib, etc.)
try:
    from jupiter_hft_strategy import JupiterHFTStrategy, TradingSignal, Signal
    HAS_HFT_STRATEGY = True
except ImportError as e:
    logger.warning(f"HFT Strategy not available: {e}. Install dependencies to enable.")
    HAS_HFT_STRATEGY = False
    # Create dummy classes for type hints
    class Signal:
        LONG = "LONG"
        SHORT = "SHORT"
        HOLD = "HOLD"
    class TradingSignal:
        pass
    class JupiterHFTStrategy:
        pass


class JupiterTraderUnified:
    """
    Unified Jupiter trader for Sapphire cloud_trader integration.

    Responsibilities:
    - Execute swaps via Jupiter Ultra API
    - Verify transactions on Solana
    - Track positions and balances
    - Send trade notifications
    - Integrate with HFT strategy
    """

    def __init__(
        self,
        api_key: str,
        private_key_b58: str,
        telegram_bot_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        capital_usd: Decimal = Decimal("50"),
        enable_hft_strategy: bool = False,
    ):
        """
        Initialize Jupiter trader

        Args:
            api_key: Jupiter API key
            private_key_b58: Solana private key (base58 format)
            telegram_bot_token: Optional Telegram bot token
            telegram_chat_id: Optional Telegram chat ID
            capital_usd: Total trading capital
            enable_hft_strategy: Whether to use HFT strategy for signals
        """
        # Load Solana keypair
        private_bytes = base58.b58decode(private_key_b58)
        self.keypair = Keypair.from_bytes(private_bytes)

        # Initialize Jupiter client
        self.client = JupiterClient(
            api_key=api_key,
            keypair=self.keypair,
        )

        # Initialize integration (handles Telegram, price monitoring)
        self.integration = None
        if telegram_bot_token and telegram_chat_id:
            self.integration = JupiterSapphireIntegration(
                jupiter_api_key=api_key,
                solana_private_key_b58=private_key_b58,
                telegram_bot_token=telegram_bot_token,
                telegram_chat_id=telegram_chat_id,
            )

        # Initialize HFT strategy (optional)
        self.hft_strategy = None
        if enable_hft_strategy and HAS_HFT_STRATEGY:
            self.hft_strategy = JupiterHFTStrategy(
                capital_usd=capital_usd,
                max_position_pct=0.20,
                confidence_threshold=0.70,
            )
        elif enable_hft_strategy and not HAS_HFT_STRATEGY:
            logger.warning("HFT strategy requested but dependencies not available. Running without HFT strategy.")

        # Position tracking
        self.open_positions: Dict[str, Dict] = {}
        self.capital = capital_usd

        # Mask wallet address for security (only show first 4 and last 4 chars)
        wallet_addr = str(self.keypair.pubkey())
        masked_wallet = f"{wallet_addr[:4]}...{wallet_addr[-4:]}"
        logger.info(f"✅ Jupiter Trader initialized - Wallet: {masked_wallet}")

    async def start(self):
        """Start the trader and integration services"""
        if self.integration:
            await self.integration.start()
        logger.info("🚀 Jupiter Trader started")

    async def close(self):
        """Close all connections"""
        await self.client.close()
        if self.integration:
            await self.integration.close()

    # ========================================================================
    # CORE TRADING METHODS (Compatible with PlatformRouter)
    # ========================================================================

    async def execute_trade(
        self,
        symbol: str,
        side: str,
        quantity: float,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute trade (compatible with PlatformRouter interface)

        Args:
            symbol: Trading pair (e.g., "SOL-USDC")
            side: "BUY" or "SELL"
            quantity: Amount to trade in base currency
            **kwargs: Additional parameters

        Returns:
            Standardized execution result dict
        """
        start_time = datetime.now()

        try:
            # Parse symbol to get mints
            base, quote = self._parse_symbol(symbol)

            # Determine input/output mints based on side
            if side == "BUY":
                # Buying base with quote (e.g., buy SOL with USDC)
                input_mint = self._get_mint_address(quote)
                output_mint = self._get_mint_address(base)
                # quantity is in quote currency (USDC)
                amount = self.client.format_amount(Decimal(str(quantity)), 6)  # USDC = 6 decimals
            else:  # SELL
                # Selling base for quote (e.g., sell SOL for USDC)
                input_mint = self._get_mint_address(base)
                output_mint = self._get_mint_address(quote)
                # quantity is in base currency (SOL)
                decimals = 9 if base == "SOL" else 6
                amount = self.client.format_amount(Decimal(str(quantity)), decimals)

            # Get swap order
            order = await self.client.get_swap_order(
                input_mint=input_mint,
                output_mint=output_mint,
                amount=amount,
            )

            # Execute swap
            result = await self.client.execute_swap(order)

            # Calculate latency
            latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            if result.success:
                # Parse amounts
                input_amount = self.client.parse_amount(
                    int(result.input_amount),
                    6 if quote == "USDC" else 9
                )
                output_amount = self.client.parse_amount(
                    int(result.output_amount),
                    9 if base == "SOL" else 6
                )

                # Calculate price
                if side == "BUY":
                    price = float(input_amount / output_amount) if output_amount > 0 else 0
                    filled_quantity = float(output_amount)
                else:
                    price = float(output_amount / input_amount) if input_amount > 0 else 0
                    filled_quantity = float(input_amount)

                # Update position tracking
                self._update_position(symbol, side, filled_quantity, price)

                # Send Telegram notification
                if self.integration:
                    await self._send_trade_notification(
                        symbol, side, filled_quantity, price, result.signature,
                        float(input_amount), float(output_amount), latency_ms
                    )

                logger.info(
                    f"✅ Jupiter {side} {filled_quantity} {symbol} @ ${price:.6f} "
                    f"| Tx: {result.signature[:8]}... | {latency_ms}ms"
                )

                return {
                    "success": True,
                    "platform": "jupiter",
                    "symbol": symbol,
                    "side": side,
                    "quantity": filled_quantity,
                    "price": price,
                    "tx_sig": result.signature,
                    "latency_ms": latency_ms,
                    "raw_response": {
                        "input_amount": str(result.input_amount),
                        "output_amount": str(result.output_amount),
                        "order": order,
                    },
                }
            else:
                logger.error(f"❌ Jupiter {side} failed: {result.error}")
                return {
                    "success": False,
                    "platform": "jupiter",
                    "symbol": symbol,
                    "side": side,
                    "quantity": quantity,
                    "price": 0,
                    "error": result.error,
                    "latency_ms": latency_ms,
                }

        except Exception as e:
            latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error(f"❌ Jupiter trade error: {e}")
            return {
                "success": False,
                "platform": "jupiter",
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": 0,
                "error": str(e),
                "latency_ms": latency_ms,
            }

    async def get_position(self, symbol: str) -> Optional[Dict]:
        """Get current position for symbol"""
        return self.open_positions.get(symbol)

    async def close_position(self, symbol: str) -> Dict[str, Any]:
        """Close position for symbol"""
        position = self.open_positions.get(symbol)
        if not position:
            return {"success": False, "error": "No open position"}

        # Execute opposite trade to close
        opposite_side = "SELL" if position["side"] == "BUY" else "BUY"
        return await self.execute_trade(
            symbol=symbol,
            side=opposite_side,
            quantity=position["quantity"],
        )

    async def get_current_price(self, symbol: str) -> Optional[Decimal]:
        """Get current market price for symbol"""
        try:
            base, _ = self._parse_symbol(symbol)
            mint = self._get_mint_address(base)
            return await self.client.get_token_price(mint)
        except Exception as e:
            logger.error(f"Error getting price for {symbol}: {e}")
            return None

    async def get_balance(self, asset: str = "USDC") -> Decimal:
        """Get wallet balance for asset"""
        try:
            if asset == "SOL":
                return await self.client.get_sol_balance()
            else:
                # Get holdings via Ultra API
                holdings = await self.client.get_holdings()
                mint = self._get_mint_address(asset)

                if mint in holdings.get("tokens", {}):
                    token_accounts = holdings["tokens"][mint]
                    if token_accounts and len(token_accounts) > 0:
                        return Decimal(str(token_accounts[0]["uiAmount"]))

                return Decimal(0)
        except Exception as e:
            logger.error(f"Error getting balance for {asset}: {e}")
            return Decimal(0)

    # ========================================================================
    # HFT STRATEGY INTEGRATION
    # ========================================================================

    async def analyze_symbol(self, symbol: str, df: Any) -> Optional[TradingSignal]:
        """
        Analyze symbol using HFT strategy

        Args:
            symbol: Trading pair
            df: OHLCV DataFrame with price data

        Returns:
            TradingSignal if confident signal found
        """
        if not self.hft_strategy:
            return None

        base, _ = self._parse_symbol(symbol)
        return await self.hft_strategy.analyze_and_generate_signal(
            base, df, timeframe="15m"
        )

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _parse_symbol(self, symbol: str) -> tuple:
        """Parse symbol into base/quote (e.g., SOL-USDC -> SOL, USDC)"""
        parts = symbol.replace("/", "-").split("-")
        if len(parts) == 2:
            return parts[0], parts[1]
        # Handle SOLUSDC format
        if symbol.endswith("USDC"):
            return symbol[:-4], "USDC"
        if symbol.endswith("USDT"):
            return symbol[:-4], "USDT"
        return symbol, "USDC"  # Default to USDC

    def _get_mint_address(self, token: str) -> str:
        """Get Solana mint address for token symbol"""
        mint_map = {
            "SOL": JupiterClient.SOL_MINT,
            "USDC": JupiterClient.USDC_MINT,
            "USDT": JupiterClient.USDT_MINT,
            "ETH": JupiterClient.ETH_MINT,
            "WETH": JupiterClient.ETH_MINT,
            "BTC": JupiterClient.WBTC_MINT,
            "WBTC": JupiterClient.WBTC_MINT,
        }
        return mint_map.get(token.upper(), JupiterClient.USDC_MINT)

    def _update_position(self, symbol: str, side: str, quantity: float, price: float):
        """Update position tracking"""
        if symbol in self.open_positions:
            existing = self.open_positions[symbol]

            # If closing position
            if existing["side"] != side:
                new_quantity = abs(existing["quantity"] - quantity)
                if new_quantity < 0.0001:  # Position closed
                    del self.open_positions[symbol]
                    logger.info(f"📊 Closed position: {symbol}")
                else:
                    # Partial close
                    existing["quantity"] = new_quantity
                    logger.info(f"📊 Partial close: {symbol} remaining {new_quantity}")
            else:
                # Adding to position
                existing["quantity"] += quantity
                existing["entry_price"] = (
                    existing["entry_price"] * (existing["quantity"] - quantity) + price * quantity
                ) / existing["quantity"]
                logger.info(f"📊 Added to position: {symbol} total {existing['quantity']}")
        else:
            # New position
            self.open_positions[symbol] = {
                "side": side,
                "quantity": quantity,
                "entry_price": price,
                "open_time": datetime.now(),
            }
            logger.info(f"📊 Opened position: {side} {quantity} {symbol} @ ${price}")

    async def _send_trade_notification(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        tx_sig: str,
        input_amount: float,
        output_amount: float,
        latency_ms: int,
    ):
        """Send Telegram notification for Jupiter swap"""
        if not self.integration or not self.integration.telegram:
            return

        from enhanced_telegram import NotificationPriority

        # Use the new specialized Jupiter notification method
        await self.integration.telegram.send_jupiter_swap_notification(
            symbol=symbol,
            side=side,
            price=price,
            quantity=quantity,
            input_amount=input_amount,
            output_amount=output_amount,
            tx_signature=tx_sig,
            latency_ms=latency_ms,
            priority=NotificationPriority.HIGH,
        )


# Example usage
async def example_unified_trader():
    """Example: Use unified Jupiter trader"""

    # Your credentials
    JUPITER_API_KEY = "d1302809-3996-4ceb-aad0-7da8a71d6149"
    SOLANA_PRIVATE_KEY = "5tg6XZMb96ZcGAip6jnpRmxWfQxNASr6tM9C8LmKxhhMC6gKEtsvQPdzhmMogrrbcf8wjTwyWnsfD12NjXJfeZc8"

    # Optional Telegram
    TELEGRAM_BOT_TOKEN = None  # "YOUR_BOT_TOKEN"
    TELEGRAM_CHAT_ID = None  # "YOUR_CHAT_ID"

    # Initialize trader
    trader = JupiterTraderUnified(
        api_key=JUPITER_API_KEY,
        private_key_b58=SOLANA_PRIVATE_KEY,
        telegram_bot_token=TELEGRAM_BOT_TOKEN,
        telegram_chat_id=TELEGRAM_CHAT_ID,
        capital_usd=Decimal("50"),
        enable_hft_strategy=False,
    )

    try:
        await trader.start()

        # Example: Execute a buy order
        result = await trader.execute_trade(
            symbol="SOL-USDC",
            side="BUY",
            quantity=1.28,  # $1.28 worth of SOL (0.01 SOL at ~$128)
        )

        print(f"Trade result: {result}")

        # Get current price
        price = await trader.get_current_price("SOL-USDC")
        print(f"Current SOL price: ${price}")

        # Get balance
        sol_balance = await trader.get_balance("SOL")
        usdc_balance = await trader.get_balance("USDC")
        print(f"SOL Balance: {sol_balance}")
        print(f"USDC Balance: {usdc_balance}")

    finally:
        await trader.close()


if __name__ == "__main__":
    asyncio.run(example_unified_trader())
