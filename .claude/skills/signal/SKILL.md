---
name: signal
description: Send a test trading signal through the Sapphire pipeline
disable-model-invocation: true
---

# /signal — Test Trading Signal

Send a test signal through the full pipeline: webhook (Windows) → signal logger (Mac) → Telegram.

## Usage

```
/signal ETHBTC buy 0.048 0.9        # symbol action price confidence
/signal HYPEUSDT sell 35.0           # confidence defaults to 0.5
/signal BTCUSDT buy                  # price defaults to 0, confidence 0.5
```

## Pipeline

```
TradingView alert (simulated)
  → POST http://100.x.x.z:9090/webhook/tradingview
  → webhook validates + enriches
  → POST http://100.x.x.w:18081/api/signals
  → signal logger saves to data/trading_signals.jsonl
  → Nemotron AI assessment
  → Telegram notification via NemotronRariBot
```

## How to Execute

1. Build the signal payload:
```json
{
  "secret": "sapphire_trading_2024",
  "symbol": "<SYMBOL>",
  "action": "<ACTION>",
  "strategy": "v3_ultra",
  "price": <PRICE>,
  "confidence": <CONFIDENCE>
}
```

2. Send to webhook:
```bash
curl -s -X POST http://100.x.x.z:9090/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '<payload>'
```

3. Verify signal was logged:
```bash
tail -1 data/trading_signals.jsonl | python3 -m json.tool
```

4. Check Telegram for notification

## Valid Symbols

ETHBTC, SOLBTC, ZECBTC, BTCUSDT, ETHUSDT, HYPEUSDT, SOLUSDT

## Valid Actions

buy, sell, long, short, exit, close
