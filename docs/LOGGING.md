# Sapphire OS - Logging Infrastructure

## Overview

Comprehensive structured logging system for signal flow analysis and debugging across the entire trading infrastructure.

## Components

### 1. Structured Loggers

**Location:** `services/shared/logging_config.py`

Three specialized loggers:
- **WebhookLogger** - TradingView webhook events, AI enrichment, publishing
- **TradingLogger** - Signal received, validated, published, executed, errors
- **SelfImprovementLogger** - Weekly review, metrics analysis, task creation

### 2. Log Storage

**Primary:** Cloud Logging (stdout)
**Secondary:** Firestore (`system_logs` collection) for dashboard queries

### 3. Log Viewer Dashboard

**URL:** https://sapphire-log-viewer-267358751314.us-central1.run.app

Features:
- Real-time log streaming (30s auto-refresh)
- Filter by service (webhook, trading, self_improvement)
- Filter by level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Time range (1h, 6h, 24h, 7d)
- Search by message content
- Stats dashboard

## Event Types

### Webhook Events
- `webhook_request` - Incoming webhook from TradingView
- `webhook_validation` - Secret/token validation
- `ollama_enrichment` - AI analysis via Ollama
- `webhook_response` - Response sent back

### Trading Events
- `signal_received` - Signal received from source
- `signal_validated` - Validation result (symbol, action, price)
- `signal_published` - Published to Pub/Sub
- `signal_error` - Processing error
- `trade_executed` - Trade executed on exchange

### Self-Improvement Events
- `review_started` - Weekly review begins
- `metrics_analyzed` - Performance metrics calculated
- `task_created` - Improvement task created
- `review_completed` - Review finished

## Signal Flow Trace

Each signal gets a unique `signal_id` that flows through:

```
TradingView → Webhook → Pub/Sub → Bot → Exchange
     ↓           ↓         ↓       ↓       ↓
  webhook:   webhook:  signal: signal: trade:
  request   published  received validated executed
```

## Log Format

```json
{
  "timestamp": "2025-02-26T22:45:30.123Z",
  "service": "webhook",
  "component": "tradingview_receiver",
  "level": "INFO",
  "message": "Signal received: ETHBTC BUY",
  "event_type": "signal_received",
  "signal_id": "sig_1740612330_42",
  "symbol": "ETHBTC",
  "action": "buy"
}
```

## Usage

### Python Code

```python
from services.shared.logging_config import get_trading_logger, get_webhook_logger

trading_logger = get_trading_logger()
webhook_logger = get_webhook_logger()

# Log signal received
trading_logger.log_signal_received(
    signal_id="sig_123",
    symbol="ETHBTC",
    action="buy",
    source="tradingview",
    price=0.052
)

# Log webhook request
webhook_logger.log_request_received(
    request_id="req_456",
    client_ip="1.2.3.4",
    symbol="ETHBTC"
)
```

### Viewing Logs

```bash
# Cloud Logging
gcloud logging read "resource.labels.service_name=webhook-receiver" --limit=50

# Dashboard
open https://sapphire-log-viewer-267358751314.us-central1.run.app

# Firestore
gcloud firestore documents list --collection=system_logs --limit=10
```

## Deployment

### Webhook Receiver (Windows PC)

```batch
REM Download and run deployment script
curl -L -o deploy.bat https://raw.githubusercontent.com/arigatoexpress/Sapphire/main/scripts/deploy_windows_webhook.bat
deploy.bat
```

### Log Viewer (Cloud Run)

```bash
./scripts/deploy_log_dashboard.sh
```

## Troubleshooting

### No logs in Firestore
- Check `FIRESTORE_LOGGING=true` env var
- Verify service account has Firestore write permissions
- Check Cloud Logging for errors

### High latency in log viewer
- Add Firestore indexes for timestamp queries
- Limit query to 24h or less
- Use service filters

### Missing events
- Ensure all services use same logging_config
- Check for circular imports
- Verify log levels (DEBUG may be filtered in production)
