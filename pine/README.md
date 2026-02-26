# Sapphire Pine Scripts

TradingView Pine Script strategies for the Sapphire trading system.

## Scripts
- `v3_ultra/` — Primary pair trading strategy (Z-score + Kalman + regime detection + Kelly sizing)
- `multi_symbol_screener/` — Scans ETH/BTC, SOL/BTC, ZEC/BTC, HYPE/USDT simultaneously
- `v1_basic/` — Simple mean reversion baseline
- `v2_strategy_nn/` — Strategy + neural network overlay

## Webhook Alert Format
```json
{
  "symbol": "{{ticker}}",
  "action": "{{strategy.order.action}}",
  "price": {{close}},
  "time": "{{time}}",
  "exchange": "{{exchange}}",
  "interval": "{{interval}}",
  "z_score": 0,
  "confidence": 0.85
}
```

## Webhook URL
Set in TradingView → Alert → Webhook URL:
`https://presents-exploration-grocery-retirement.trycloudflare.com/webhook/tradingview`

(Production: webhook.sapphirealpha.xyz/webhook/tradingview — pending cloudflared named tunnel)
