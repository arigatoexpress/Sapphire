# Symphony Account Activation Guide

## 🎯 **Quick Activation Steps**

Your Symphony account needs **5 successful trades** to activate. Here's how to get there fast:

### **Step 1: Fund Your Symphony Wallet**

1. Navigate to https://symphony.finance
2. Click your profile (top right) → "Deposit"
3. Select "USDC" (only supported collateral)
4. Deposit via:
   - **Bridge** from another chain
   - **Card** (instant, small fee)
   - **Transfer** from another wallet

**Recommended**: Start with at least **$500 USDC** for comfortable trading.

---

### **Step 2: Create Your First A gentic Fund**

**Option A: Via MIT Dashboard**
1. Go to https://sapphire-479610.web.app/mit
2. Click "Create Fund" (when available)
3. Fill in:
   - **Name**: "Sapphire MIT Agent"
   - **Description**: "AI-powered autonomous trading"
   - **Type**: "Perpetuals"
   - **Autosubscribe**: ✅ (recommended)

**Option B: Via API**
```bash
curl -X POST https://cloud-trader-267358751314.europe-west1.run.app/api/symphony/fund/create \
  -H "Authorization: Bearer YOUR_FIREBASE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Sapphire MIT Agent",
    "description": "Autonomous AI trading on Monad",
    "fund_type": "perpetuals",
    "autosubscribe": true
  }'
```

---

### **Step 3: Execute 5 Activation Trades**

You can use **perpetual trades** OR **spot trades**. Both count toward activation.

#### **Perpetual Trade Example (Recommended)**
Safe, small position to minimize risk:

```bash
# Trade 1: Small BTC Long
curl -X POST https://cloud-trader-267358751314.europe-west1.run.app/api/symphony/trade/perpetual \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTC-USDC",
    "side": "LONG",
    "size": 10,
    "leverage": 1,
    "stop_loss": null,
    "take_profit": null
  }'

# Trade 2: Small ETH Long
# ... (change symbol to "ETH-USDC", size to 10)

# Trade 3: Small SOL Long
# ... (change symbol to "SOL-USDC", size to 10)

# Trade 4: Small BTC Short (if price drops)
# ... (change side to "SHORT")

# Trade 5: Close any position
# ... (use opposite side)
```

#### **Spot Trade Example (Lower Risk)**
```bash
# Trade 1: Buy small BTC
curl -X POST https://cloud-trader-267358751314.europe-west1.run.app/api/symphony/trade/spot \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTC-USDC",
    "side": "BUY",
    "quantity": 0.001,
    "order_type": "market"
  }'

# Trade 2-5: Repeat with different symbols or amounts
```

---

### **Step 4: Monitor Activation Progress**

**Via Dashboard**:
- Visit https://sapphire-479610.web.app/mit
- Watch the progress bar update: 0/5 → 1/5 → ... → 5/5

**Via API**:
```bash
curl https://cloud-trader-267358751314.europe-west1.run.app/api/symphony/status
```

Response shows:
```json
{
  "trades_count": 3,
  "is_activated": false,
  "activation_progress": {
    "current": 3,
    "required": 5,
    "percentage": 60,
    "activated": false
  }
}
```

---

### **Step 5: Activation Complete! 🎉**

Once you hit 5 trades:
- ✅ Dashboard shows "Activated" badge
- ✅ You can now accept subscribers
- ✅ Configure management fees
- ✅ Earn from other traders copying your strategy

---

## 🔐 **Getting Your Firebase Auth Token**

To trade via API, you need your Firebase auth token:

**Browser Console Method**:
```javascript
// 1. Login to https://sapphire-479610.web.app
// 2. Open browser console (F12)
// 3. Run:
firebase.auth().currentUser.getIdToken().then(token => {
  console.log('Token:', token);
  navigator.clipboard.writeText(token);
  alert('Token copied to clipboard!');
});
```

**Or use the MIT dashboard** (coming soon) which will have a built-in trading interface.

---

## 💡 **Pro Tips for Fast Activation**

1. **Start Small**: Use minimum position sizes ($10-20) to minimize risk
2. **Use 1x Leverage**: Lower risk while still counting toward activation
3. **Quick Turnaround**: Open and close positions fast (they don't need to be profitable)
4. **Mix Strategies**: Alternate between perpetuals and spot
5. **Test Mode**: Treat these 5 trades as practice runs

---

## 🆘 **Troubleshooting**

**Issue**: "Symphony API not configured"
- **Fix**: Ensure `SYMPHONY_API_KEY` is set in backend `.env` file

**Issue**: "Authentication required"
- **Fix**: Include valid Firebase token in `Authorization: Bearer TOKEN` header

**Issue**: Trade not counting toward activation
- **Fix**: Ensure trade executed successfully (check response for `"success": true`)

**Issue**: Can't deposit USDC
- **Fix**: Make sure you're connected to the right network (Monad)

---

## 📊 **Current Status**

**API Key**: ✅ Configured (`sk_live_k7h5KAh71HJM7uKARBf4a-JGJoaltQoRaAuY7a4wjp8`)
**Backend**: ⏳ Deploying...
**Frontend**: ✅ Live at https://sapphire-479610.web.app/mit
**Symphony Account**: ⏳ Awaiting first deposit & fund creation

---

**Once backend deploys**, you can start the activation process immediately! 🚀
