#!/bin/bash
# Trading Performance Dashboard Queries

echo "📈 Trading Performance Dashboard"
echo "==============================="
echo ""

PROJECT_ID="sapphireinfinite"

# Function to query logs
query_logs() {
    local filter="$1"
    local limit="${2:-10}"
    gcloud logging read "$filter" \
        --limit=$limit \
        --format="table(timestamp.date('%H:%M:%S'), textPayload)" \
        --project=$PROJECT_ID 2>/dev/null
}

# 1. Trading Volume
echo "📊 TRADING VOLUME (Last 24h):"
query_logs 'resource.type="cloud_run_revision" AND resource.labels.service_name="cloud-trader" AND textPayload:"placed order"' 20
echo ""

# 2. Win/Loss Ratio
echo "💰 P&L TRACKING:"
query_logs 'resource.type="cloud_run_revision" AND resource.labels.service_name="cloud-trader" AND (textPayload:"pnl" OR textPayload:"profit" OR textPayload:"loss")' 15
echo ""

# 3. Agent Performance
echo "🤖 AGENT ACTIVITY:"
query_logs 'resource.type="cloud_run_revision" AND resource.labels.service_name="cloud-trader" AND textPayload:"agent"' 10
echo ""

# 4. Risk Metrics
echo "⚠️ RISK METRICS:"
query_logs 'resource.type="cloud_run_revision" AND resource.labels.service_name="cloud-trader" AND (textPayload:"leverage" OR textPayload:"exposure" OR textPayload:"risk")' 10
echo ""

# 5. API Performance
echo "⚡ API PERFORMANCE:"
query_logs 'resource.type="cloud_run_revision" AND resource.labels.service_name="cloud-trader" AND textPayload:"latency"' 5
echo ""

# 6. Summary Stats
echo "📊 SUMMARY STATISTICS:"
echo "- Total Logs (24h):"
gcloud logging read \
    'resource.type="cloud_run_revision" AND resource.labels.service_name="cloud-trader" AND timestamp>="'$(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%S)'"' \
    --format="value(textPayload)" \
    --project=$PROJECT_ID | wc -l

echo "- Error Count (24h):"
gcloud logging read \
    'resource.type="cloud_run_revision" AND resource.labels.service_name="cloud-trader" AND severity>=ERROR AND timestamp>="'$(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%S)'"' \
    --format="value(textPayload)" \
    --project=$PROJECT_ID | wc -l

echo ""
echo "✅ Dashboard queries complete!"
