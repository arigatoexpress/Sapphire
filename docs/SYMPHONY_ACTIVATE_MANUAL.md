# 🚀 Symphony MIT Fund Activation - Manual Guide

## ✅ Setup Complete

- **API Key Configured**: `$SYMPHONY_API_KEY` (stored securely in environment)
- **Wallet Funded**: $250 USDC ✅
- **Fund Created**: MIT Agent

---

## 📋 Step 1: Get Your Agent ID

1. Go to **https://app.symphony.io/agentic-funds**
2. Find your "MIT" fund
3. Click on it to view details
4. Copy the **Agent ID** (looks like: `63946153-9f33-4b7e-9b32-b99a4a6037e2`)

---

## 🔥 Step 2: Execute 5 Activation Trades

Once you have your Agent ID, run these commands:

### **Trade 1: Long BTC**
```bash
curl -X POST 'https://api.symphony.io/agent/batch-open' \
  -H "x-api-key: $SYMPHONY_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "agentId": "YOUR_AGENT_ID_HERE",
    "symbol": "BTC",
    "action": "LONG",
    "weight": 10,
    "leverage": 1,
    "orderOptions": {
      "triggerPrice": 0,
      "stopLossPrice": 0,
      "takeProfitPrice": 0
    }
  }'
```

### **Trades 2-5**: Repeat with different symbols/sides

**Your API Key**: Stored in `$SYMPHONY_API_KEY` environment variable
**Funded Amount**: $250 USDC ✅  
**Activation Required**: 5 trades  
**Current Progress**: 0/5

- **Wallet Funded**: $250 USDC ✅
- **Fund Created**: MIT Agent

---

## 📋 Step 1: Get Your Agent ID

1. Go to **https://app.symphony.io/agentic-funds**
2. Find your "MIT" fund
3. Click on it to view details
4. Copy the **Agent ID** (looks like: `63946153-9f33-4b7e-9b32-b99a4a6037e2`)

---

## 🔥 Step 2: Execute 5 Activation Trades

Once you have your Agent ID, run these commands:

### **Trade 1: Long BTC**
```bash
curl -X POST 'https://api.symphony.io/agent/batch-open' \
  -H 'x-api-key: sk_live_MZDK1SgMeRQzEKpuRFM7FXbcMgD833YA8Y69DnpprvE' \
  -H 'Content-Type: application/json' \
  -d '{
    "agentId": "YOUR_AGENT_ID_HERE",
    "symbol": "BTC",
    "action": "LONG",
    "weight": 10,
    "leverage": 1,
    "orderOptions": {
      "triggerPrice": 0,
      "stopLossPrice": 0,
      "takeProfitPrice": 0
    }
  }'
```

### **Trade 2: Long ETH**
```bash
curl -X POST 'https://api.symphony.io/agent/batch-open' \
  -H 'x-api-key: sk_live_MZDK1SgMeRQzEKpuRFM7FXbcMgD833YA8Y69DnpprvE' \
  -H 'Content-Type: application/json' \
  -d '{
    "agentId": "YOUR_AGENT_ID_HERE",
    "symbol": "ETH",
    "action": "LONG",
    "weight": 10,
    "leverage": 1,
    "orderOptions": {
      "triggerPrice": 0,
      "stopLossPrice": 0,
      "takeProfitPrice": 0
    }
  }'
```

### **Trade 3: Long SOL**
```bash
curl -X POST 'https://api.symphony.io/agent/batch-open' \
  -H 'x-api-key: sk_live_MZDK1SgMeRQzEKpuRFM7FXbcMgD833YA8Y69DnpprvE' \
  -H 'Content-Type: application/json' \
  -d '{
    "agentId": "YOUR_AGENT_ID_HERE",
    "symbol": "SOL",
    "action": "LONG",
    "weight": 10,
    "leverage": 1,
    "orderOptions": {
      "triggerPrice": 0,
      "stopLossPrice": 0,
      "takeProfitPrice": 0
    }
  }'
```

### **Trade 4: Short BTC**
```bash
curl -X POST 'https://api.symphony.io/agent/batch-open' \
  -H 'x-api-key: sk_live_MZDK1SgMeRQzEKpuRFM7FXbcMgD833YA8Y69DnpprvE' \
  -H 'Content-Type: application/json' \
  -d '{
    "agentId": "YOUR_AGENT_ID_HERE",
    "symbol": "BTC",
    "action": "SHORT",
    "weight": 10,
    "leverage": 1,
    "orderOptions": {
      "triggerPrice": 0,
      "stopLossPrice": 0,
      "takeProfitPrice": 0
    }
  }'
```

### **Trade 5: Short ETH**
```bash
curl -X POST 'https://api.symphony.io/agent/batch-open' \
  -H 'x-api-key: sk_live_MZDK1SgMeRQzEKpuRFM7FXbcMgD833YA8Y69DnpprvE' \
  -H 'Content-Type: application/json' \
  -d '{
    "agentId": "YOUR_AGENT_ID_HERE",
    "symbol": "ETH",
    "action": "SHORT",
    "weight": 10,
    "leverage": 1,
    "orderOptions": {
      "triggerPrice": 0,
      "stopLossPrice": 0,
      "takeProfitPrice": 0
    }
  }'
```

---

## ✅ Success Response

Each successful trade will return:
```json
{
  "message": "Batch open trade submitted",
  "batchId": "...",
  "successful": 1,
  "failed": 0,
  "results": [...]
}
```

---

## 🎉 After 5 Trades

Your MIT fund will be **ACTIVATED**!

Check status at:
- **Symphony Dashboard**: https://app.symphony.io/agentic-funds
- **Sapphire MIT Dashboard**: https://sapphire-479610.web.app/mit

---

## 🔧 Alternative: Use Symphony Web UI

1. Go to **https://app.symphony.io**
2. Navigate to your MIT fund
3. Use the trading interface to execute 5 trades manually
4. Smaller trades ($10-20) recommended for activation

---

## 💡 Quick Tips

- **Position Size**: Use $10 with 1x leverage (minimal risk)
- **Time Between Trades**: Wait ~5 seconds between each
- **Symbols**: BTC, ETH, SOL all work
- **Actions**: Mix of LONG and SHORT
- **Goal**: Just complete 5 trades - profitability doesn't matter for activation

---

**Your API Key**: `sk_live_MZDK1SgMeRQzEKpuRFM7FXbcMgD833YA8Y69DnpprvE`
**Funded Amount**: $250 USDC ✅
**Activation Required**: 5 trades
**Current Progress**: 0/5
