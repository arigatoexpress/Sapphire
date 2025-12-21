# 🎯 Symphony Account Activation - Quick Start

## ✅ What's Already Complete

- ✅ **Backend Deployed** - `cloud-trader-00019-ztk` at https://cloud-trader-267358751314.europe-west1.run.app
- ✅ **Frontend Deployed** - https://sapphire-479610.web.app/mit
- ✅ **API Key Configured** - `sk_live_k7h5KAh71HJM7uKARBf4a-JGJoaltQoRaAuY7a4wjp8`
- ✅ **Trading Interface Built** - Quick-trade buttons ready
- ✅ **Status Tracking** - Real-time 0/5 progress bar
- ✅ **Security** - All endpoints authenticated via Firebase

---

## 📋 Your 3-Step Activation Process

### **Step 1: Fund Your Symphony Wallet** 💰
1. Go to **https://symphony.finance**
2. Connect your wallet (or create one)
3. Deposit **minimum $100 USDC** (recommended: $500)
   - Method:bridge, card, or transfer
   - USDC is the only supported collateral

### **Step 2: Access the MIT Dashboard** 🎨
1. Visit **https://sapphire-479610.web.app/mit**
2. Login with your Sapphire account
3. You'll see:
   - Activation progress: **0/5 trades**
   - Trading interface below the features

### **Step 3: Execute 5 Quick Trades** 🚀

**Option A: Use the Dashboard** (Easiest)

Click the quick-trade buttons:
1. **Long BTC ($10)** - Click → Wait for confirmation
2. **Long ETH ($10)** - Click → Progress becomes 2/5
3. **Long SOL ($10)** - Click → Progress becomes 3/5
4. **Short BTC ($10)** - Click → Progress becomes 4/5
5. **Long BTC ($10)** again - Click → ✅ **ACTIVATED!**

**Option B: Use Custom Trade Form**
- Select symbol: BTC-USDC, ETH-USDC, or SOL-USDC
- Choose side: Long or Short
- Set size: $10-$20 (minimize risk)
- Leverage: 1x or 2x (recommended: 1x)
- Click "Execute Trade"

---

## 🎉 What Happens When You Hit 5/5

The dashboard will:
- Show green **"Activated"** badge
- Display "Fund is live!" message
- Enable subscriber management features
- Allow you to configure management fees
- Hide the trading interface (no longer needed)

---

## 🔍 Test Your Setup Right Now

**Quick API Test** (from terminal):
```bash
# Check if Symphony is configured
curl https://cloud-trader-267358751314.europe-west1.run.app/api/symphony/status
```

**Expected Response**:
```json
{
  "configured": true,
  "trades_count": 0,
  "is_activated": false,
  "activation_progress": {
    "current": 0,
    "required": 5,
    "percentage": 0,
    "activated": false
  }
}
```

If you see `"configured": false`, the Symphony API key might not be loaded. Check your Cloud Run environment variables.

---

## ⚡ Pro Tips for Fast Activation

1. **Minimize Risk**: Use $10-20 position sizes
2. **Use 1x Leverage**: Lower risk, still counts
3. **Quick Turnaround**: Doesn't matter if trades are profitable
4. **Mix Symbols**: BTC, ETH, SOL all count equally
5. **Watch Progress**: Dashboard updates in real-time

---

## 🆘 Troubleshooting

**Problem**: "Symphony API not configured"
```bash
# Fix: Add var to Cloud Run
gcloud run services update cloud-trader \
  --region europe-west1 \
  --update-env-vars SYMPHONY_API_KEY=sk_live_k7h5KAh71HJM7uKARBf4a-JGJoaltQoRaAuY7a4wjp8
```

**Problem**: Trades not executing
- Check you're logged in (top-right should show your email)
- Ensure you have USDC in your Symphony wallet
- Check browser console for errors (F12)

**Problem**: Progress not updating
- Refresh the page manually (it should auto-refresh)
- Check `/api/symphony/status` endpoint directly

**Problem**: "Authentication required" error
- Log out and back in to refresh your Firebase token
- Try in an incognito window

---

## 📊 Current System Status

| Component | Status | URL |
|-----------|--------|-----|
| **Backend** | ✅ Live | https://cloud-trader-267358751314.europe-west1.run.app |
| **Frontend** | ✅ Live | https://sapphire-479610.web.app/mit |
| **API Status** | ✅ Public | /api/symphony/status |
| **Trading** | ✅ Protected | /api/symphony/trade/* (needs auth) |
| **Symphony Key** | ✅ Configured | sk_live_k7h5KAh...jh8 |

---

## 🚀 Ready to Activate!

**Your activation journey starts at**: https://sapphire-479610.web.app/mit

Once you fund your Symphony wallet and execute 5 small trades, you'll be **fully activated** and able to:
- Accept subscribers
- Earn management fees
- Build your trading reputation
- Scale your AI fund

**Estimated Time**: 10-15 minutes (including wallet funding)

---

**Questions?** Check the full guide: `/docs/SYMPHONY_ACTIVATION.md`
