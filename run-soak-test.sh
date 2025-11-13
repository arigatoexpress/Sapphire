#!/usr/bin/env bash

# 24-hour soak test script for trading system
# Usage: ./run-soak-test.sh <service_url>

set -euo pipefail

SERVICE_URL=${1:-"https://cloud-trader-342943608894.us-central1.run.app"}
DURATION=${2:-86400}  # 24 hours in seconds
INTERVAL=60  # Check every minute

echo "🧪 Starting 24-hour soak test"
echo "Service: ${SERVICE_URL}"
echo "Duration: ${DURATION} seconds ($(($DURATION / 3600)) hours)"
echo "Check interval: ${INTERVAL} seconds"
echo ""

START_TIME=$(date +%s)
END_TIME=$((START_TIME + DURATION))
CHECK_COUNT=0
SUCCESS_COUNT=0
FAIL_COUNT=0

# Create results directory
RESULTS_DIR="soak-test-results-$(date +%Y%m%d-%H%M%S)"
mkdir -p "${RESULTS_DIR}"

echo "📊 Results will be saved to: ${RESULTS_DIR}"
echo ""

while [ $(date +%s) -lt $END_TIME ]; do
    CHECK_COUNT=$((CHECK_COUNT + 1))
    CURRENT_TIME=$(date +%s)
    ELAPSED=$((CURRENT_TIME - START_TIME))
    HOURS=$((ELAPSED / 3600))
    MINUTES=$(((ELAPSED % 3600) / 60))
    
    echo "[$(printf "%02d:%02d" $HOURS $MINUTES)] Check #${CHECK_COUNT}..."
    
    # Test health endpoint
    if curl -f -s -m 10 "${SERVICE_URL}/healthz" > "${RESULTS_DIR}/health-${CHECK_COUNT}.json" 2>/dev/null; then
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        echo "  ✅ Health check passed"
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo "  ❌ Health check failed"
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) - Health check failed" >> "${RESULTS_DIR}/failures.log"
    fi
    
    # Test dashboard endpoint
    if curl -f -s -m 10 "${SERVICE_URL}/dashboard" > "${RESULTS_DIR}/dashboard-${CHECK_COUNT}.json" 2>/dev/null; then
        echo "  ✅ Dashboard check passed"
    else
        echo "  ❌ Dashboard check failed"
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) - Dashboard check failed" >> "${RESULTS_DIR}/failures.log"
    fi
    
    # Sleep until next check
    sleep $INTERVAL
done

ELAPSED_TOTAL=$((END_TIME - START_TIME))
HOURS_TOTAL=$((ELAPSED_TOTAL / 3600))

echo ""
echo "📊 Soak test complete!"
echo "Duration: ${HOURS_TOTAL} hours"
echo "Total checks: ${CHECK_COUNT}"
echo "Successful: ${SUCCESS_COUNT}"
echo "Failed: ${FAIL_COUNT}"
echo "Success rate: $(echo "scale=2; ${SUCCESS_COUNT} * 100 / ${CHECK_COUNT}" | bc)%"
echo ""
echo "Results saved to: ${RESULTS_DIR}"

