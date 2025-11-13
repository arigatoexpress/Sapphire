#!/bin/bash
# Real-time Trading Monitor Script

echo "🚀 Starting Live Trading Monitor..."
echo "=================================="
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Monitor trading activity
echo -e "${BLUE}📊 REAL-TIME TRADING ACTIVITY:${NC}"
echo "Monitoring for: trades, positions, orders, errors..."
echo ""

gcloud beta logging tail \
  "resource.type=cloud_run_revision AND resource.labels.service_name=cloud-trader AND (textPayload:'order' OR textPayload:'position' OR textPayload:'trade' OR textPayload:'error' OR textPayload:'placed' OR textPayload:'executed')" \
  --format="table(timestamp.date('%Y-%m-%d %H:%M:%S'):label=TIME, textPayload:label=EVENT)" \
  --project=sapphireinfinite
