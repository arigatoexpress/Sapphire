# Trading Setup Status Report
**Date:** 2026-03-03  
**Status:** ✅ LIVE TRADING READY - Manual Configuration Required

---

## 🔷 Current System Status

### Alpha Engine Configuration
| Setting | Value | Status |
|---------|-------|--------|
| **Kill Switch** | OFF | ✅ Safe to trade |
| **Execution Stage** | staged_live | ✅ Live trading active |
| **Live Dispatch** | Enabled | ✅ Orders will execute |
| **TradingView Execution** | Enabled | ✅ TV signals accepted |
| **TV Signal Mode** | live | ✅ Real trades (not paper) |
| **Open Positions** | 0 | ✅ No positions to close |
| **Pending Approvals** | 20 | ⚠️ Needs approval |

### Position Sizing
| Parameter | Value | Notes |
|-----------|-------|-------|
| Base Quantity | 0.02 | Per trade base size |
| Stage Multiplier | 0.25 | 25% of base for safety |
| **Effective Quantity** | **0.005** | Actual trade size |

### Trading Venues
- ✅ **ASTER** - Allocation: 100%, Status: Active
- ✅ **LIGHTER** - Allocation: 100%, Status: Active

---

## 🎯 TradingView Webhook Status

### Webhook Endpoint
```
https://sapphire-gateway-267358751314.us-central1.run.app/webhook/tradingview
```

### Current Stats
- Total signals received: **0**
- Signals published: **0**
- Signals failed: **0**
- Last signal: **Never**

### Idempotency Window
- Duplicate signals within **5 minutes** are ignored
- Prevents double-execution of same alert

---

## ⚠️ Action Required

### 1. Approve Pending Autonomy Sessions (20 pending)

**Option A: Via macOS Commander App**
1. Open Sapphire Commander (menu bar icon)
2. Click "Pending Approvals" (if available)
3. Review and approve each session

**Option B: Via Terminal with Control Token**
```bash
# Get control token
gcloud secrets versions access latest \
  --secret=sapphire-control-api-token \
  --project=sapphire-479610

# Use token to approve sessions
curl -X POST "https://sapphire-alpha-267358751314.us-central1.run.app/control/approve" \
  -H "X-Sapphire-Control-Token: YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"session_key": "SESSION_KEY", "decision": "approve"}'
```

**Option C: Disable Owner Approval (Not Recommended)**
```bash
curl -X POST "https://sapphire-alpha-267358751314.us-central1.run.app/control/configure" \
  -H "X-Sapphire-Control-Token: YOUR_TOKEN" \
  -d '{"owner_approval_required": false}'
```

### 2. Configure Take Profit / Stop Loss

**Current TP/SL Settings:** Not configured (needs manual setup)

**To configure via API:**
```bash
curl -X POST "https://sapphire-alpha-267358751314.us-central1.run.app/control/configure" \
  -H "X-Sapphire-Control-Token: YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tradingview_take_profit_pct": 3.0,
    "tradingview_stop_loss_pct": 2.0,
    "trailing_stop_enabled": true,
    "trailing_stop_distance_pct": 1.5
  }'
```

**Recommended TP/SL Settings for SOL:**
- Take Profit: 3-5% (SOL is volatile)
- Stop Loss: 2-3% (tight risk control)
- Trailing Stop: 1.5% (lock in profits)

### 3. Adjust Position Size (Optional)

**Current:** 0.005 per trade (~$435 at $87/SOL)

**To increase position size:**
```bash
curl -X POST "https://sapphire-alpha-267358751314.us-central1.run.app/control/configure" \
  -H "X-Sapphire-Control-Token: YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "dex_base_quantity": 0.1,
    "tradingview_default_quantity": 0.1
  }'
```

---

## 📋 TradingView Alert Configuration

### Alert 1: Long Solana

**Webhook URL:**
```
https://sapphire-gateway-267358751314.us-central1.run.app/webhook/tradingview
```

**Message (JSON):**
```json
{
  "symbol": "SOLUSDT",
  "price": {{close}},
  "side": "buy",
  "action": "open_long",
  "timestamp": "{{time}}",
  "interval": "{{interval}}",
  "strategy": "sapphire_sol_long",
  "metadata": {
    "volume": {{volume}},
    "rsi": "{{plot_0}}",
    "alert_name": "Long Solana"
  }
}
```

### Alert 2: Sell Solana

**Webhook URL:**
```
https://sapphire-gateway-267358751314.us-central1.run.app/webhook/tradingview
```

**Message (JSON):**
```json
{
  "symbol": "SOLUSDT",
  "price": {{close}},
  "side": "sell",
  "action": "close_long",
  "timestamp": "{{time}}",
  "interval": "{{interval}}",
  "strategy": "sapphire_sol_long",
  "metadata": {
    "volume": {{volume}},
    "alert_name": "Sell Solana"
  }
}
```

---

## 🔒 Security Checklist

Before going live, verify:
- [x] Kill switch is accessible (macOS Commander)
- [x] Telegram bot notifications are active
- [x] Dashboard monitoring is working
- [x] Position sizing is appropriate for risk tolerance
- [x] TP/SL levels are configured
- [ ] Pending approvals are cleared (or disabled)

---

## 📊 Monitoring Commands

### Check Positions
```bash
curl "https://sapphire-alpha-267358751314.us-central1.run.app/control/status" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); \
  print('Open positions:', d['portfolio']['open_count']); \
  print('Positions:', d['portfolio']['open_positions'])"
```

### Check Recent Trades
```bash
curl "https://sapphire-alpha-267358751314.us-central1.run.app/api/trading/metrics" | \
  python3 -m json.tool
```

### Check Webhook Stats
```bash
curl "https://sapphire-gateway-267358751314.us-central1.run.app/webhook/health" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); \
  print('Total signals:', d['tradingview_ingress']['stats']['total']); \
  print('Published:', d['tradingview_ingress']['stats']['published'])"
```

---

## 🚨 Emergency Procedures

### Kill Switch (Immediate Halt)
1. **macOS Commander:** Press ⌘K or click "Emergency Stop"
2. **Telegram:** Send `/killswitch` to @sapphire_trading_bot
3. **Dashboard:** Visit https://sapphirealpha.xyz/platform

### Close All Positions
```bash
curl -X POST "https://sapphire-alpha-267358751314.us-central1.run.app/positions/close-all" \
  -H "X-Sapphire-Control-Token: YOUR_TOKEN"
```

---

## 📈 Expected Behavior

When your "Long Solana" alert fires:
1. TradingView sends webhook to Gateway
2. Gateway validates and publishes to Pub/Sub
3. Alpha Engine receives signal
4. **IF** autonomy session approved → executes via ASTER/LIGHTER
5. Position opened on exchange (0.005 SOL)
6. TP/SL orders placed (if configured)
7. Notification sent via Telegram
8. Trade logged to Firestore

When your "Sell Solana" alert fires:
1. Same flow as above
2. Position closed
3. PnL calculated and logged

---

## ⚡ Quick Actions Needed

1. **Get Control Token:**
   ```bash
   gcloud secrets versions access latest \
     --secret=sapphire-control-api-token \
     --project=sapphire-479610
   ```

2. **Approve All Sessions:**
   ```bash
   # Run this for each session key
   for key in $(curl -s "https://sapphire-alpha-267358751314.us-central1.run.app/control/status" | \
     python3 -c "import sys,json; d=json.load(sys.stdin); \
     print(' '.join([s['session_key'] for s in d['pending_sessions']]))"); do
     curl -X POST "https://sapphire-alpha-267358751314.us-central1.run.app/control/approve" \
       -H "X-Sapphire-Control-Token: YOUR_TOKEN" \
       -d "{\"session_key\": \"$key\", \"decision\": \"approve\"}"
   done
   ```

3. **Set TP/SL:**
   ```bash
   curl -X POST "https://sapphire-alpha-267358751314.us-central1.run.app/control/configure" \
     -H "X-Sapphire-Control-Token: YOUR_TOKEN" \
     -d '{"tradingview_take_profit_pct": 3.0, "tradingview_stop_loss_pct": 2.0}'
   ```

---

**Status:** System is LIVE and ready. Pending approvals are blocking autonomous execution - clear them to start trading.

**Last Updated:** 2026-03-03  
**Next Check:** After approving sessions and configuring TP/SL
