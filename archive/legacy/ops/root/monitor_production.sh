#!/bin/bash
# Production Monitoring Script for Sapphire V2.3
# Monitors backend health, platform connectivity, and autonomous learning

set -e

REGION="asia-southeast1"
SERVICE="sapphire-backend"
PROJECT="sapphire-479610"

echo "🔍 SAPPHIRE V2.3 PRODUCTION MONITORING"
echo "========================================"
echo ""

# 1. Check Cloud Run Service Status
echo "📍 1. Cloud Run Service Status (Singapore)"
echo "-------------------------------------------"
gcloud run services describe $SERVICE \
  --region=$REGION \
  --project=$PROJECT \
  --format="table(status.url,status.latestReadyRevisionName,status.conditions[0].status)" 2>/dev/null || echo "❌ Service not found"

echo ""

# 2. Get Service URL
SERVICE_URL=$(gcloud run services describe $SERVICE \
  --region=$REGION \
  --project=$PROJECT \
  --format="value(status.url)" 2>/dev/null)

if [ -n "$SERVICE_URL" ]; then
    echo "✅ Service URL: $SERVICE_URL"
    echo ""

    # 3. Health Check
    echo "🏥 2. Health Check"
    echo "------------------"
    HEALTH=$(curl -s -w "\nHTTP_CODE:%{http_code}\n" "$SERVICE_URL/health" 2>/dev/null || echo "FAILED")
    echo "$HEALTH"
    echo ""

    # 4. Platform Status
    echo "🌐 3. Platform Connectivity"
    echo "----------------------------"
    curl -s "$SERVICE_URL/api/platform-router/health" 2>/dev/null | jq '.' || echo "❌ Platform health endpoint unavailable"
    echo ""

    # 5. Agent Status
    echo "🤖 4. Autonomous Learning Agents"
    echo "--------------------------------"
    curl -s "$SERVICE_URL/api/agents/list" 2>/dev/null | jq '.agents[] | {id, platform, status}' || echo "❌ Agents endpoint unavailable"
    echo ""

    # 6. Recent Trades
    echo "💰 5. Recent Trading Activity"
    echo "-----------------------------"
    curl -s "$SERVICE_URL/api/positions" 2>/dev/null | jq '.' || echo "⏳ No positions yet"
    echo ""

    # 7. Learning Progress
    echo "🧠 6. Learning Progress"
    echo "-----------------------"
    curl -s "$SERVICE_URL/api/agents/metrics" 2>/dev/null | jq '.[] | {agent: .agent_id, trades: .total_trades, win_rate: .win_rate, patterns: .patterns_discovered}' || echo "⏳ Learning just started"
    echo ""

    # 8. System Metrics
    echo "📊 7. System Performance"
    echo "------------------------"
    curl -s "$SERVICE_URL/api/platform-router/metrics" 2>/dev/null | jq '.' || echo "⏳ Collecting metrics"
    echo ""

else
    echo "❌ Service URL not available yet"
fi

# 9. Recent Logs
echo "📝 8. Recent Logs (Last 10 lines)"
echo "----------------------------------"
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE" \
  --limit=10 \
  --project=$PROJECT \
  --format="table(timestamp,severity,textPayload)" 2>/dev/null || echo "⏳ No logs yet"

echo ""
echo "✅ Monitoring Complete"
echo "======================"
