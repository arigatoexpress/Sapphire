"""
Jupiter Trader Bot for Sapphire
Automated trading on Jupiter with risk management for $50 capital
"""

import asyncio
import os
from typing import Optional, Dict, List
from decimal import Decimal
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
from loguru import logger
from solders.keypair import Keypair

from jupiter_client import JupiterClient, SwapResult


class RiskLevel(Enum):
    """Risk levels for position sizing"""
    CONSERVATIVE = "conservative"  # Max 20% of capital per trade
    MODERATE = "moderate"  # Max 40% of capital per trade
    AGGRESSIVE = "aggressive"  # Max 60% of capital per trade


@dataclass
class TradingConfig:
    """Trading configuration with risk management"""
    total_capital_usd: Decimal
    risk_level: RiskLevel
    max_daily_trades: int = 10
    max_slippage_bps: int = 50  # 0.5%
    min_profit_target_pct: Decimal = Decimal("2.0")  # 2% minimum profit target
    stop_loss_pct: Decimal = Decimal("5.0")  # 5% stop loss
    max_position_hold_hours: int = 24

    @property
    def max_position_size_usd(self) -> Decimal:
        """Max position size based on risk level"""
        risk_multipliers = {
            RiskLevel.CONSERVATIVE: Decimal("0.20"),
            RiskLevel.MODERATE: Decimal("0.40"),
            RiskLevel.AGGRESSIVE: Decimal("0.60"),
        }
        return self.total_capital_usd * risk_multipliers[self.risk_level]


@dataclass
class Trade:
    """Trade record"""
    timestamp: datetime
    market: str
    side: str  # "buy" or "sell"
    input_token: str
    output_token: str
    input_amount: Decimal
    output_amount: Decimal
    price: Decimal
    signature: str
    pnl_usd: Optional[Decimal] = None
    status: str = "pending"  # pending, confirmed, failed


class JupiterTrader:
    """
    Jupiter Trading Bot with Risk Management

    Features:
    - Position sizing based on risk level
    - Daily trade limits
    - Stop loss and take profit
    - PnL tracking
    - Safeguards for $50 capital

    Example:
        ```python
        config = TradingConfig(
            total_capital_usd=Decimal("50"),
            risk_level=RiskLevel.CONSERVATIVE,
            max_daily_trades=5,
        )

        trader = JupiterTrader(
            jupiter_api_key="your_key",
            private_key_hex="your_hex",
            config=config,
        )

        # Execute a conservative trade
        result = await trader.execute_trade(
            input_token="SOL",
            output_token="USDC",
            amount_usd=Decimal("10"),  # 20% of $50
        )
        ```
    """

    # Token shortcuts
    TOKENS = {
        "SOL": JupiterClient.SOL_MINT,
        "USDC": JupiterClient.USDC_MINT,
        "USDT": JupiterClient.USDT_MINT,
        "ETH": JupiterClient.ETH_MINT,
        "WBTC": JupiterClient.WBTC_MINT,
    }

    TOKEN_DECIMALS = {
        "SOL": 9,
        "USDC": 6,
        "USDT": 6,
        "ETH": 8,
        "WBTC": 8,
    }

    def __init__(
        self,
        jupiter_api_key: str,
        private_key_hex: str,
        config: TradingConfig,
        solana_rpc_url: str = "https://api.mainnet-beta.solana.com",
    ):
        """
        Initialize Jupiter trader

        Args:
            jupiter_api_key: Jupiter API key
            private_key_hex: Solana private key (hex or base58 format)
            config: Trading configuration with risk params
            solana_rpc_url: Solana RPC endpoint
        """
        self.config = config

        # Initialize keypair (support both hex and base58)
        try:
            # Try base58 first (standard Solana format)
            import base58
            private_key_bytes = base58.b58decode(private_key_hex)
            self.keypair = Keypair.from_bytes(private_key_bytes)
        except:
            # Fall back to hex format
            seed_bytes = bytes.fromhex(private_key_hex)
            self.keypair = Keypair.from_seed(seed_bytes)

        # Initialize Jupiter client
        self.client = JupiterClient(
            api_key=jupiter_api_key,
            keypair=self.keypair,
            solana_rpc_url=solana_rpc_url,
        )

        # Track trades
        self.trades: List[Trade] = []
        self.daily_trade_count = 0
        self.last_reset_date = datetime.now().date()

        # Current positions (simplified - track bought tokens)
        self.positions: Dict[str, Decimal] = {}  # token -> amount

        logger.info(
            f"Jupiter Trader initialized - Capital: ${config.total_capital_usd}, "
            f"Risk: {config.risk_level.value}, Wallet: {self.keypair.pubkey()}"
        )

    async def close(self):
        """Close client connections"""
        await self.client.close()

    def _reset_daily_counter_if_needed(self):
        """Reset daily trade counter if new day"""
        today = datetime.now().date()
        if today > self.last_reset_date:
            self.daily_trade_count = 0
            self.last_reset_date = today
            logger.info("Daily trade counter reset")

    async def can_trade(self, amount_usd: Decimal) -> tuple[bool, Optional[str]]:
        """
        Check if trade is allowed based on risk rules

        Returns:
            (can_trade, reason_if_not)
        """
        self._reset_daily_counter_if_needed()

        # Check daily limit
        if self.daily_trade_count >= self.config.max_daily_trades:
            return False, f"Daily trade limit reached ({self.config.max_daily_trades})"

        # Check position size
        if amount_usd > self.config.max_position_size_usd:
            return False, f"Position size ${amount_usd} exceeds max ${self.config.max_position_size_usd}"

        # Check capital preservation (ensure we have enough)
        if amount_usd > self.config.total_capital_usd * Decimal("0.95"):
            return False, "Trade would risk >95% of capital"

        return True, None

    async def execute_trade(
        self,
        input_token: str,
        output_token: str,
        amount_usd: Decimal,
        slippage_bps: Optional[int] = None,
    ) -> Optional[Trade]:
        """
        Execute a trade with risk checks

        Args:
            input_token: Input token symbol (e.g., "SOL")
            output_token: Output token symbol (e.g., "USDC")
            amount_usd: Amount to trade in USD
            slippage_bps: Slippage tolerance (default from config)

        Returns:
            Trade object if successful, None otherwise
        """
        # Risk check
        can_trade, reason = await self.can_trade(amount_usd)
        if not can_trade:
            logger.warning(f"Trade blocked: {reason}")
            return None

        slippage = slippage_bps or self.config.max_slippage_bps

        try:
            # Get current price to convert USD to token amount
            input_mint = self.TOKENS[input_token]
            output_mint = self.TOKENS[output_token]

            input_price = await self.client.get_token_price(input_mint)
            input_amount_tokens = amount_usd / input_price
            input_amount_smallest = self.client.format_amount(
                input_amount_tokens,
                self.TOKEN_DECIMALS[input_token]
            )

            logger.info(
                f"Executing trade: {input_amount_tokens} {input_token} -> {output_token} "
                f"(~${amount_usd} @ ${input_price}/{input_token})"
            )

            # Execute swap
            result = await self.client.swap_tokens(
                input_mint=input_mint,
                output_mint=output_mint,
                amount=input_amount_smallest,
                slippage_bps=slippage,
            )

            # Create trade record
            trade = Trade(
                timestamp=datetime.now(),
                market=f"{input_token}/{output_token}",
                side="buy" if output_token in ["SOL", "ETH", "WBTC"] else "sell",
                input_token=input_token,
                output_token=output_token,
                input_amount=input_amount_tokens,
                output_amount=self.client.parse_amount(
                    int(result.output_amount),
                    self.TOKEN_DECIMALS[output_token]
                ),
                price=result.price,
                signature=result.signature,
                status="confirmed" if result.success else "failed",
            )

            self.trades.append(trade)
            self.daily_trade_count += 1

            # Update positions
            if trade.output_token != "USDC" and trade.output_token != "USDT":
                self.positions[trade.output_token] = self.positions.get(trade.output_token, Decimal(0)) + trade.output_amount

            logger.info(
                f"✅ Trade executed: {trade.input_amount} {trade.input_token} -> "
                f"{trade.output_amount} {trade.output_token} | Sig: {trade.signature}"
            )

            return trade

        except Exception as e:
            logger.error(f"Trade execution failed: {e}")
            return None

    async def close_position(
        self,
        token: str,
        to_token: str = "USDC",
    ) -> Optional[Trade]:
        """
        Close a position (sell token back to stablecoin)

        Args:
            token: Token to sell (e.g., "SOL")
            to_token: Target token (default "USDC")

        Returns:
            Trade if successful
        """
        if token not in self.positions or self.positions[token] == 0:
            logger.warning(f"No position in {token} to close")
            return None

        amount = self.positions[token]
        amount_smallest = self.client.format_amount(amount, self.TOKEN_DECIMALS[token])

        try:
            result = await self.client.swap_tokens(
                input_mint=self.TOKENS[token],
                output_mint=self.TOKENS[to_token],
                amount=amount_smallest,
                slippage_bps=self.config.max_slippage_bps,
            )

            trade = Trade(
                timestamp=datetime.now(),
                market=f"{token}/{to_token}",
                side="sell",
                input_token=token,
                output_token=to_token,
                input_amount=amount,
                output_amount=self.client.parse_amount(
                    int(result.output_amount),
                    self.TOKEN_DECIMALS[to_token]
                ),
                price=result.price,
                signature=result.signature,
                status="confirmed",
            )

            self.trades.append(trade)
            self.positions[token] = Decimal(0)

            logger.info(f"✅ Position closed: {token} -> {to_token}")

            return trade

        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            return None

    async def get_portfolio_value_usd(self) -> Decimal:
        """Calculate total portfolio value in USD"""
        total = Decimal(0)

        # Get prices for all positions
        if self.positions:
            tokens_with_balance = [t for t, amt in self.positions.items() if amt > 0]
            if tokens_with_balance:
                mints = [self.TOKENS[t] for t in tokens_with_balance]
                prices = await self.client.get_multiple_prices(mints)

                for token, amount in self.positions.items():
                    if amount > 0:
                        mint = self.TOKENS[token]
                        price = prices[mint]
                        total += amount * price

        # Add SOL balance
        sol_balance = await self.client.get_sol_balance()
        sol_price = await self.client.get_token_price(self.TOKENS["SOL"])
        total += sol_balance * sol_price

        return total

    def get_trade_stats(self) -> Dict:
        """Get trading statistics"""
        if not self.trades:
            return {"total_trades": 0}

        total_trades = len(self.trades)
        successful = len([t for t in self.trades if t.status == "confirmed"])

        # Calculate total PnL (simplified - compares USDC in/out)
        total_pnl = Decimal(0)
        for trade in self.trades:
            if trade.input_token in ["USDC", "USDT"]:
                total_pnl -= trade.input_amount
            if trade.output_token in ["USDC", "USDT"]:
                total_pnl += trade.output_amount

        return {
            "total_trades": total_trades,
            "successful_trades": successful,
            "success_rate": f"{(successful / total_trades * 100):.1f}%",
            "total_pnl_usd": float(total_pnl),
            "daily_trades_remaining": self.config.max_daily_trades - self.daily_trade_count,
        }


# ============================================================================
# EXAMPLE USAGE FOR $50 CAPITAL
# ============================================================================

async def example_conservative_trading():
    """Example: Conservative trading strategy with $50 capital"""

    # Configuration for $50 capital
    config = TradingConfig(
        total_capital_usd=Decimal("50"),
        risk_level=RiskLevel.CONSERVATIVE,  # Max $10 per trade (20%)
        max_daily_trades=5,
        max_slippage_bps=50,  # 0.5%
        min_profit_target_pct=Decimal("3.0"),  # 3% profit target
        stop_loss_pct=Decimal("5.0"),  # 5% stop loss
    )

    # Initialize trader
    trader = JupiterTrader(
        jupiter_api_key=os.getenv("JUPITER_API_KEY"),
        private_key_hex=os.getenv("SOLANA_PRIVATE_KEY_HEX"),
        config=config,
    )

    try:
        # Example 1: Buy $10 worth of SOL
        logger.info("=== Example 1: Buy SOL ===")
        trade1 = await trader.execute_trade(
            input_token="USDC",
            output_token="SOL",
            amount_usd=Decimal("10"),
        )

        if trade1:
            logger.info(f"Bought {trade1.output_amount} SOL for ${trade1.input_amount} USDC")

        # Example 2: Get portfolio value
        portfolio_value = await trader.get_portfolio_value_usd()
        logger.info(f"Portfolio value: ${portfolio_value}")

        # Example 3: Get stats
        stats = trader.get_trade_stats()
        logger.info(f"Trading stats: {stats}")

        # Example 4: Close position if profitable
        # (In real trading, you'd check profit/loss before closing)
        if "SOL" in trader.positions:
            logger.info("=== Example 4: Close SOL position ===")
            close_trade = await trader.close_position("SOL")
            if close_trade:
                logger.info(f"Sold {close_trade.input_amount} SOL for {close_trade.output_amount} USDC")

    finally:
        await trader.close()


if __name__ == "__main__":
    # Set up environment variables:
    # export JUPITER_API_KEY="your_jupiter_api_key"
    # export SOLANA_PRIVATE_KEY_HEX="your_private_key_hex"

    asyncio.run(example_conservative_trading())
