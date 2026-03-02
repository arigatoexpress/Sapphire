# TradingView Integration - Development Plan

**Status:** ⚠️ NOT WORKING - Requires Development  
**Last Updated:** 2026-03-02

---

## 🚨 Current Issues

### 1. TV Worker Errors
- HTTP 500 errors from PM Hub
- Health check timeouts (30s timeout exceeded)
- TV connection status: `tv_connected: false`

### 2. Missing Architecture Components
- No signal pipeline from TV to trading bots
- No webhook endpoint for TV alerts
- No signal translation layer (TV format → bot format)

---

## 📋 Development Tasks

### Phase 1: Fix TV Web Connection (Priority: HIGH)

**Issue:** TV Web session not connecting to tradingview.com

**Tasks:**
- [ ] Debug TV web session health check failures
- [ ] Fix Playwright/Chromium connection to TradingView
- [ ] Verify TV account login/authentication
- [ ] Test chart loading and indicator visibility

**Files to investigate:**
- `~/.openclaw/runtime/codex-projects/skills/tradingview-desktop-control/scripts/tv_web_inventory.py`
- `~/.openclaw/runtime/codex-projects/scripts/tradingview_web_session_health.py`
- TradingView Autonomous Manager (port 8081)

---

### Phase 2: Webhook Signal Endpoint (Priority: HIGH)

**Issue:** No way to receive signals from TradingView alerts

**Architecture:**
```
TradingView Alert → Webhook → Raspberry Pi → Trading Bot
```

**Implementation Options:**

#### Option A: Direct Webhook (Recommended)
Create a simple webhook receiver on the Pis:

```python
# webhook_server.py - Run on Pi 2
from flask import Flask, request
import json

app = Flask(__name__)

@app.route('/webhook/tradingview', methods=['POST'])
def tradingview_webhook():
    signal = request.json
    # Validate signal format
    # Transform to bot format
    # Publish to Pub/Sub or call bot directly
    return {'status': 'received'}
```

**Pros:** Simple, direct, no external dependencies  
**Cons:** Need to handle TV IP whitelist, SSL certificate

#### Option B: Cloud Run Webhook Relay
Create a Cloud Run service to receive webhooks and forward to Pis:

```
TV Alert → Cloud Run Webhook → Pub/Sub → Pi Subscription → Bot
```

**Pros:** Secure, scalable, works through VPN  
**Cons:** More complex, latency

---

### Phase 3: Signal Translation Layer (Priority: MEDIUM)

**Issue:** TV signal format doesn't match bot signal format

**TradingView Alert Format (example):**
```json
{
  "symbol": "ETHUSDT",
  "side": "buy",
  "price": 3500.00,
  "strategy": "EMA_Cross",
  "time": "2026-03-02T16:35:00Z"
}
```

**Bot Signal Format Required:**
```json
{
  "platform": "lighter",
  "symbol": "WETH",  // Note: ETH→WETH translation needed
  "side": "BUY",
  "quantity": 0.1,
  "order_type": "MARKET"
}
```

**Tasks:**
- [ ] Create signal schema validator
- [ ] Build symbol mapper (TV format → exchange format)
- [ ] Implement signal router (which bot gets which signal)
- [ ] Add signal logging/audit trail

---

### Phase 4: Strategy Integration (Priority: MEDIUM)

**Goal:** Allow TV strategies to control position sizing, stop losses

**TV Alert Message Format (enhanced):**
```json
{
  "symbol": "ETHUSDT",
  "action": "entry",
  "side": "buy",
  "price": 3500.00,
  "size_percent": 10,
  "stop_loss": 3400.00,
  "take_profit": 3800.00,
  "strategy": "EMA_Cross_v2"
}
```

**Tasks:**
- [ ] Parse advanced signal parameters
- [ ] Calculate position size from balance
- [ ] Set stop-loss/take-profit orders
- [ ] Track strategy performance per signal

---

### Phase 5: TV Interface Automation (Priority: LOW)

**Goal:** Full browser automation for TV (not just webhook)

**Use Cases:**
- Extract indicator values from TV chart
- Screenshot chart on signal
- Auto-refresh strategies
- Manage TV alerts programmatically

**Note:** This is complex and fragile. Webhook approach is more reliable.

---

## 🎯 Recommended Next Steps

### Immediate (Today)
1. **Choose architecture:** Direct webhook vs Cloud relay
2. **Create webhook endpoint** on Pi 2 (port 8082)
3. **Test with curl** to verify signal flow

### This Week
4. **Deploy webhook server** as systemd service
5. **Configure TV alert** with webhook URL
6. **Test end-to-end** signal → bot execution

### Next Week
7. **Add signal validation** and error handling
8. **Implement symbol mapping** (ETH→WETH, etc.)
9. **Add position sizing** from TV alerts

---

## 🔧 Technical Implementation

### Webhook Server (Minimal Viable)

```python
#!/usr/bin/env python3
"""
TradingView Webhook Receiver
Receives alerts from TradingView and forwards to trading bots
"""

from flask import Flask, request, jsonify
import json
import os
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Symbol mapping (TV format -> Exchange format)
SYMBOL_MAP = {
    'ETHUSDT': 'WETH',  # Lighter uses WETH
    'BTCUSDT': 'WBTC',
    'SOLUSDT': 'SOL',
}

@app.route('/health', methods=['GET'])
def health():
    return {'status': 'healthy', 'service': 'tv-webhook'}

@app.route('/webhook/tradingview', methods=['POST'])
def tradingview_webhook():
    """Receive TradingView alert"""
    try:
        data = request.json
        logger.info(f"Received TV signal: {json.dumps(data)}")
        
        # Validate required fields
        if not all(k in data for k in ['symbol', 'side']):
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Transform signal
        tv_symbol = data['symbol']
        exchange_symbol = SYMBOL_MAP.get(tv_symbol, tv_symbol)
        
        signal = {
            'source': 'tradingview',
            'platform': data.get('platform', 'lighter'),
            'symbol': exchange_symbol,
            'side': data['side'].upper(),
            'quantity': data.get('quantity', 0.01),
            'order_type': data.get('order_type', 'MARKET'),
            'timestamp': data.get('time')
        }
        
        # TODO: Send to bot (Pub/Sub or HTTP)
        # Option 1: Publish to Pub/Sub
        # publish_signal(signal)
        
        # Option 2: Call bot gateway directly
        # send_to_bot(signal)
        
        logger.info(f"Transformed signal: {json.dumps(signal)}")
        
        return jsonify({
            'status': 'received',
            'signal': signal
        })
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8082, debug=False)
```

### Systemd Service

```ini
# /etc/systemd/system/tv-webhook.service
[Unit]
Description=TradingView Webhook Receiver
After=network.target

[Service]
Type=simple
User=rari
WorkingDirectory=/home/rari/Sapphire/services/tv-webhook
Environment=PYTHONPATH=/home/rari/Sapphire/services
ExecStart=/usr/bin/python3 webhook_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### TradingView Alert Configuration

In TradingView alert message:
```
{
  "symbol": "{{ticker}}",
  "side": "{{strategy.order.action}}",
  "price": {{close}},
  "platform": "lighter",
  "quantity": 0.1,
  "time": "{{time}}"
}
```

Webhook URL:
```
http://YOUR_PUBLIC_IP:8082/webhook/tradingview
```

---

## ⚠️ Challenges

1. **Public IP/Port Forwarding:**
   - TradingView needs to reach your Pi
   - Options: Port forwarding, ngrok, Cloudflare Tunnel
   
2. **IP Whitelisting:**
   - TV webhooks come from specific IPs
   - Need to allow these in firewall

3. **SSL/HTTPS:**
   - TV requires HTTPS for webhooks
   - Need reverse proxy or Cloudflare

4. **VPN + Public Access:**
   - VPN obscures real IP
   - May need split tunneling or Cloud relay

---

## 💡 Recommendation

**Use Cloud Run Webhook Relay** (Option B):

```
TradingView → HTTPS Webhook (Cloud Run) → Pub/Sub → Pi (VPN)
```

This avoids:
- Port forwarding
- SSL certificate management
- IP whitelisting issues
- VPN conflicts

**Estimated effort:** 1-2 days to implement and test
