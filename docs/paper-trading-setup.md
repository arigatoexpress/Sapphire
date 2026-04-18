# Sapphire Paper Trading Setup Guide

Paper trading lets you validate the full signal pipeline — TradingView → webhook → scoring → Telegram — without real money on the line.

---

## How It Works

When `PAPER_TRADING=1` is set on the signal logger:
- All incoming signals are scored normally by `signal_pipeline.py`
- Position sizing, R:R, kernel gating — all real calculations
- Paper P&L is tracked in `data/paper_trading.jsonl`
- Telegram alerts are prefixed `[PAPER]` so you know they're not live
- No real orders are placed (the pipeline has no execution layer anyway)

To go **live**: remove `PAPER_TRADING=1` from the LaunchAgent env vars and reload. Nothing else changes.

---

## Step 1 — Enable Paper Trading Mode

Add `PAPER_TRADING=1` to the signal logger LaunchAgent:

```bash
# Edit the plist
nano ~/Library/LaunchAgents/com.sapphire.signal-logger.plist

# Add inside the <dict> after other EnvironmentVariables:
<key>PAPER_TRADING</key>
<string>1</string>

# Reload
launchctl bootout gui/$(id -u)/com.sapphire.signal-logger
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.sapphire.signal-logger.plist
```

Verify it's set:
```bash
curl -s http://localhost:18081/health | python3 -m json.tool
# Should show: "paper_trading": true
```

---

## Step 2 — TradingView Alert Setup

### Webhook URL
```
http://100.71.10.48:9090/webhook/tradingview
```
(Windows receiver → Mac signal logger at 100.67.171.79:18081)

### Alert Message Format (copy-paste into TradingView alert body)

**For BUY/LONG alerts:**
```json
{"symbol": "{{ticker}}", "action": "buy", "price": {{close}}, "confidence": 0.75, "strategy": "{{strategy.name}}", "take_profit": 0, "stop_loss": 0}
```

**For SELL/SHORT alerts:**
```json
{"symbol": "{{ticker}}", "action": "sell", "price": {{close}}, "confidence": 0.75, "strategy": "{{strategy.name}}", "take_profit": 0, "stop_loss": 0}
```

**With TP/SL (from Pine Script strategy):**
```json
{"symbol": "{{ticker}}", "action": "{{strategy.order.action}}", "price": {{close}}, "confidence": 0.8, "strategy": "{{strategy.name}}", "take_profit": {{strategy.order.price}}, "stop_loss": {{strategy.order.price}}}
```

### TradingView Alert Settings
- **Condition**: Your indicator/strategy signal
- **Actions**: Webhook URL (paste the URL above)
- **Message**: Paste the JSON template above
- **Alert name**: `ENS-BTCUSDT-buy` (or similar for easy tracking)

---

## Step 3 — Configure Watchlist Alerts

Create one alert per symbol per direction. Recommended starting watchlist:

| Symbol | TV Ticker | Alert Type | Confidence |
|--------|-----------|------------|------------|
| Bitcoin | BINANCE:BTCUSDT | RSI(14) < 30 → buy / RSI > 70 → sell | 0.80 |
| Ethereum | BINANCE:ETHUSDT | RSI(14) < 30 → buy / RSI > 70 → sell | 0.75 |
| S&P 500 ETF | AMEX:SPY | Daily close > 20MA → buy | 0.70 |
| Tesla | NASDAQ:TSLA | MACD crossover → buy/sell | 0.65 |
| ES Futures | CME_MINI:ES1! | VWAP cross → long/short | 0.70 |

**Minimum viable alert** (just price cross — no Pine needed):
1. Open chart for BTCUSDT on Binance
2. Click "Alert" (clock icon)
3. Set condition: `Close crosses above [value]`
4. In "Message" box: paste the JSON template (hardcode "buy" or "sell")
5. Enable webhook, paste URL

---

## Step 4 — Verify Signals Are Flowing

### Check the signal JSONL
```bash
# Most recent 5 signals
tail -5 ~/Code/Sapphire/data/signals/$(date +%Y-%m-%d).jsonl | python3 -m json.tool
```

### Check paper trading P&L file
```bash
tail -10 ~/Code/Sapphire/data/paper_trading.jsonl | python3 -c "
import sys, json
for line in sys.stdin:
    s = json.loads(line)
    print(f\"{s.get('symbol','?'):10} {s.get('action','?'):5} {s.get('paper_pnl_usd',0):+.2f} USD  [{s.get('paper_status','?')}]\")
"
```

### Check Telegram
When a signal comes in, you'll see:
```
[PAPER] 🟢 Signal Pipeline — abc12345
BUY BTCUSDT | rsi_cross
Price: $65,000.00
Confidence: 75%
Score: 72/100
💰 Recommended size: $1,500 (15.0%)
```

### Check Windows webhook is live
```bash
ssh aribs@100.71.10.48 'netstat -an | findstr 9090'
# Should show: TCP 0.0.0.0:9090 ... LISTENING
```

---

## Step 5 — Reading Paper Trading Results

Paper trading stats via command-line:
```bash
python3 -c "
from pathlib import Path
import json

path = Path.home() / 'Code/Sapphire/data/paper_trading.jsonl'
if not path.exists():
    print('No paper trades yet')
else:
    trades = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    wins = sum(1 for t in trades if t.get('paper_outcome') == 'win')
    losses = sum(1 for t in trades if t.get('paper_outcome') == 'loss')
    pnl = sum(t.get('paper_pnl_usd', 0) for t in trades)
    print(f'Trades: {len(trades)} | W/L: {wins}/{losses} | Total PnL: \${pnl:.2f}')
"
```

Or via the signal pipeline directly:
```bash
python3 -c "
import sys; sys.path.insert(0, 'services/alpha')
from signal_pipeline import pipeline
print(pipeline.signal_stats())
"
```

---

## Step 6 — Going Live

When you're satisfied with paper trading results:

1. Remove `PAPER_TRADING=1` from the LaunchAgent plist
2. Reload: `launchctl kickstart -k gui/$(id -u)/com.sapphire.signal-logger`
3. The `[PAPER]` prefix disappears from Telegram
4. The paper JSONL stays intact for backreference

**That's it.** The pipeline, scoring, and routing are identical. Paper mode only changes the Telegram prefix and the secondary P&L file.

---

## Troubleshooting

| Problem | Check |
|---------|-------|
| No signals appearing | `curl http://100.71.10.48:9090/webhook/health` — is Windows receiver alive? |
| Signal received but no Telegram | `tail -50 ~/Code/Sapphire/logs/signal-logger.log` |
| Score always 0 | Signal missing `confidence` field — add it to TV alert JSON |
| PAPER prefix not showing | `curl http://localhost:18081/health` — confirm `paper_trading: true` |
| TP/SL always 0 | Use Pine Script strategy alerts instead of condition alerts for auto TP/SL |
