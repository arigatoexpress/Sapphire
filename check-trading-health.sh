#!/bin/bash
# Trading Health Check Script

echo "🏥 Trading System Health Check"
echo "=============================="
echo ""

# Check service health
echo "1️⃣ Cloud Trader Health:"
curl -s https://trader.sapphiretrade.xyz/healthz | jq .
echo ""

# Check orchestrator
echo "2️⃣ Orchestrator Status:"
curl -s https://api.sapphiretrade.xyz/orchestrator/ | jq .
echo ""

# Check recent errors
echo "3️⃣ Recent Errors (last 5):"
gcloud logging read \
  'resource.type="cloud_run_revision" AND severity>=ERROR AND resource.labels.service_name="cloud-trader"' \
  --limit=5 \
  --format="table(timestamp.date('%H:%M:%S'), textPayload)" \
  --project=quant-ai-trader-credits
echo ""

# Check circuit breaker metrics
echo "4️⃣ Circuit Breaker States:"
gcloud logging read \
  'resource.type="cloud_run_revision" AND textPayload:"circuit breaker" AND resource.labels.service_name="cloud-trader"' \
  --limit=10 \
  --format="value(textPayload)" \
  --project=quant-ai-trader-credits | grep -E "OPEN|CLOSED|half" | tail -5
echo ""

# Check trading positions
echo "5️⃣ Active Positions:"
gcloud logging read \
  'resource.type="cloud_run_revision" AND textPayload:"position" AND resource.labels.service_name="cloud-trader"' \
  --limit=10 \
  --format="value(textPayload)" \
  --project=quant-ai-trader-credits | grep -v "GET" | tail -5
echo ""

echo "✅ Health check complete!"
