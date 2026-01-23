# Jupiter Trading Bot for Sapphire

Clean, dependency-free Solana trading via Jupiter Exchange API.

## Features

✅ **Spot Trading** - Best price aggregation across all Solana DEXs
✅ **Perpetuals** - SOL, ETH, wBTC with up to 100x leverage (coming soon)
✅ **Lending/Borrowing** - Earn yield on assets (coming soon)
✅ **Limit Orders & DCA** - Automated trading strategies (coming soon)

✅ **Risk Management** - Position sizing, daily limits, stop loss
✅ **No Dependency Hell** - REST API only, no complex SDK chains
✅ **Python 3.13 Compatible** - Works on latest Python!

## Quick Start

### 1. Get Jupiter API Key

Visit [Jupiter Portal](https://jup.ag/portal) and create an API key.

### 2. Install Dependencies

```bash
cd services/bot-jupiter
pip install -r requirements.txt
```

**Note:** Uses `solana==0.34.2` and `solders==0.21.0` - compatible versions without drift conflicts!

### 3. Set Environment Variables

```bash
export JUPITER_API_KEY="your_jupiter_api_key_here"
export SOLANA_PRIVATE_KEY_HEX="your_lighter_private_key_hex"
```

Your Lighter private key (already provided):
```
9c0e8f03f7c362122dbf8bd3588fcad8ced94b5b93e83ed7ec554480fd78b1d70a116a962cb6a728
```

Lighter public key:
```
5f87610ad615c57585e5c2a83d142f89d9bf5fc3bb986f5546d2c751d734026ddbe48ef0b4f1b43e
```

### 4. Run Example

```python
from jupiter_trader import JupiterTrader, TradingConfig, RiskLevel
from decimal import Decimal

# Configure for $50 capital
config = TradingConfig(
    total_capital_usd=Decimal("50"),
    risk_level=RiskLevel.CONSERVATIVE,  # Max $10/trade
    max_daily_trades=5,
    max_slippage_bps=50,  # 0.5%
)

# Initialize trader
trader = JupiterTrader(
    jupiter_api_key="your_key",
    private_key_hex="your_hex",
    config=config,
)

# Execute trade
trade = await trader.execute_trade(
    input_token="USDC",
    output_token="SOL",
    amount_usd=Decimal("10"),  # 20% of capital
)
```

## Risk Management for $50 Capital

### Conservative Strategy (Recommended)
```python
config = TradingConfig(
    total_capital_usd=Decimal("50"),
    risk_level=RiskLevel.CONSERVATIVE,
    max_daily_trades=5,
    max_slippage_bps=50,  # 0.5%
    min_profit_target_pct=Decimal("3.0"),  # 3% profit
    stop_loss_pct=Decimal("5.0"),  # 5% loss
)
```

**Parameters:**
- **Max position:** $10 (20% of capital)
- **Daily limit:** 5 trades
- **Slippage:** 0.5%
- **Stop loss:** 5%

### Moderate Strategy
```python
config = TradingConfig(
    total_capital_usd=Decimal("50"),
    risk_level=RiskLevel.MODERATE,
    max_daily_trades=8,
)
```

**Parameters:**
- **Max position:** $20 (40% of capital)
- **Daily limit:** 8 trades

### Aggressive Strategy (Higher Risk!)
```python
config = TradingConfig(
    total_capital_usd=Decimal("50"),
    risk_level=RiskLevel.AGGRESSIVE,
    max_daily_trades=10,
)
```

**Parameters:**
- **Max position:** $30 (60% of capital)
- **Daily limit:** 10 trades
- ⚠️ **Warning:** Higher risk of significant losses!

## Supported Tokens

```python
# Token shortcuts built-in
"SOL"  # Solana
"USDC" # USD Coin
"USDT" # Tether
"ETH"  # Wormhole Ethereum
"WBTC" # Wormhole Bitcoin
```

## API Methods

### JupiterClient (Low-level)

```python
# Get quote
quote = await client.get_swap_quote(
    input_mint=JupiterClient.SOL_MINT,
    output_mint=JupiterClient.USDC_MINT,
    amount=1_000_000_000,  # 1 SOL
    slippage_bps=50,
)

# Execute swap
result = await client.execute_swap(quote)

# Get prices
sol_price = await client.get_token_price(JupiterClient.SOL_MINT)
prices = await client.get_multiple_prices([SOL_MINT, ETH_MINT])

# Search tokens
tokens = await client.search_tokens("bonk")
```

### JupiterTrader (High-level with risk management)

```python
# Execute trade with USD amount
trade = await trader.execute_trade(
    input_token="USDC",
    output_token="SOL",
    amount_usd=Decimal("10"),
)

# Close position
close_trade = await trader.close_position("SOL", to_token="USDC")

# Get portfolio value
portfolio_usd = await trader.get_portfolio_value_usd()

# Get stats
stats = trader.get_trade_stats()
# Returns: {
#   "total_trades": 5,
#   "successful_trades": 5,
#   "success_rate": "100.0%",
#   "total_pnl_usd": 2.5,
#   "daily_trades_remaining": 0,
# }
```

## Testing

### Test on Devnet First!

**IMPORTANT:** Before trading with real money, test on Solana devnet:

1. Get devnet SOL from faucet: https://faucet.solana.com/
2. Use devnet RPC:
   ```python
   trader = JupiterTrader(
       jupiter_api_key="your_key",
       private_key_hex="your_hex",
       config=config,
       solana_rpc_url="https://api.devnet.solana.com",
   )
   ```

### Start Small

Even on mainnet, **start with $10 trades** to test:

```python
# First trade: $10 only
trade = await trader.execute_trade(
    input_token="USDC",
    output_token="SOL",
    amount_usd=Decimal("10"),
)

# Monitor for 1 hour, then close
await asyncio.sleep(3600)
close_trade = await trader.close_position("SOL")
```

## Safety Features

### Built-in Safeguards

1. ✅ **Position Size Limits** - Can't trade more than risk level allows
2. ✅ **Daily Trade Limits** - Prevents over-trading
3. ✅ **Capital Preservation** - Won't risk >95% of capital in one trade
4. ✅ **Slippage Protection** - Max 0.5% slippage by default
5. ✅ **Trade Logging** - All trades tracked with timestamps

### Example Safety Checks

```python
# Will be blocked if exceeds limits
can_trade, reason = await trader.can_trade(Decimal("30"))
if not can_trade:
    print(f"Trade blocked: {reason}")
    # Output: "Position size $30 exceeds max $10"
```

## Integration with Sapphire

### Add to Cloud Trader

Create `/cloud_trader/services/jupiter_service.py`:

```python
from sapphire_repo.services.bot-jupiter.jupiter_trader import JupiterTrader

class JupiterService:
    def __init__(self, config):
        self.trader = JupiterTrader(...)

    async def execute_signal(self, signal):
        return await self.trader.execute_trade(...)
```

### Add to Configuration

In your trading config:

```python
ENABLE_JUPITER = True
JUPITER_API_KEY = os.getenv("JUPITER_API_KEY")
JUPITER_CAPITAL_USD = Decimal("50")
JUPITER_RISK_LEVEL = "conservative"
```

## Cost Estimates

### Jupiter API Pricing

From [Jupiter Portal](https://jup.ag/portal):
- **Free tier:** Limited rate limits
- **Paid tiers:** Higher throughput for serious trading

### Solana Transaction Fees

- **Base fee:** ~0.000005 SOL per transaction (~$0.0006 @ $120/SOL)
- **Priority fee:** Optional, for faster confirmation
- **Example:** 10 trades/day = ~$0.006/day in fees

**With $50 capital:**
- Conservative (5 trades/day): ~$0.003/day = ~$0.09/month
- Aggressive (10 trades/day): ~$0.006/day = ~$0.18/month

## Troubleshooting

### "Insufficient funds" error

Check your wallet balance:
```python
balance = await client.get_sol_balance()
print(f"SOL balance: {balance}")
```

Make sure you have:
- Enough SOL for gas fees (~0.01 SOL minimum)
- Enough USDC/tokens for trades

### "Slippage tolerance exceeded"

Increase slippage tolerance:
```python
trade = await trader.execute_trade(
    input_token="USDC",
    output_token="SOL",
    amount_usd=Decimal("10"),
    slippage_bps=100,  # 1% instead of 0.5%
)
```

### Rate limit errors

Upgrade your Jupiter API tier or reduce trade frequency.

## Next Steps

1. ✅ Get Jupiter API key from [portal](https://jup.ag/portal)
2. ✅ Test on devnet first
3. ✅ Start with $10 trades on mainnet
4. ✅ Monitor performance for 1 week
5. ✅ Gradually increase to $50 capital

## Resources

- **Jupiter Docs:** https://dev.jup.ag
- **Jupiter Portal:** https://jup.ag/portal
- **Solana Explorer:** https://solscan.io
- **Price Charts:** https://birdeye.so

## Support

For issues or questions:
- Jupiter Discord: https://discord.gg/jup
- Solana Stack Exchange: https://solana.stackexchange.com/

---

**Last Updated:** 2026-01-22
**Status:** ✅ Ready for testing
**Capital:** $50 USDT
**Risk Level:** Conservative recommended
