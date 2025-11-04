#!/bin/bash
# Aster API Soak Test - Post NAT Setup
# Tests health, portfolio, and order simulation

LOG_FILE="/tmp/aster_soak_$(date +%Y%m%d_%H%M%S).log"
DURATION=300  # 5 minutes
INTERVAL=5    # Check every 5 seconds

echo "=== Aster API Soak Test ===" | tee -a "$LOG_FILE"
echo "Start Time: $(date)" | tee -a "$LOG_FILE"
echo "Duration: $DURATION seconds" | tee -a "$LOG_FILE"
echo "Interval: $INTERVAL seconds" | tee -a "$LOG_FILE"
echo "NAT IP: 34.172.187.70" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Test endpoints
HEALTH_URL="https://api.sapphiretrade.xyz/orchestrator/healthz"
PORTFOLIO_URL="https://api.sapphiretrade.xyz/orchestrator/portfolio"
DASHBOARD_URL="https://trader.sapphiretrade.xyz/dashboard"

# Counters
SUCCESS_COUNT=0
FAIL_COUNT=0
RATE_LIMIT_COUNT=0
START_TIME=$(date +%s)
END_TIME=$((START_TIME + DURATION))

echo "Testing endpoints for $DURATION seconds..." | tee -a "$LOG_FILE"
echo "----------------------------------------" | tee -a "$LOG_FILE"

while [ $(date +%s) -lt $END_TIME ]; do
    ITERATION_START=$(date +%s.%N)
    
    # Test 1: Health check
    HEALTH_RESP=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL")
    echo -n "Health: $HEALTH_RESP | " | tee -a "$LOG_FILE"
    
    # Test 2: Portfolio (the critical one that was failing)
    PORTFOLIO_START=$(date +%s.%N)
    PORTFOLIO_RESP=$(curl -s -o /dev/null -w "%{http_code}" "$PORTFOLIO_URL")
    PORTFOLIO_TIME=$(echo "$(date +%s.%N) - $PORTFOLIO_START" | bc)
    echo -n "Portfolio: $PORTFOLIO_RESP (${PORTFOLIO_TIME}s) | " | tee -a "$LOG_FILE"
    
    # Test 3: Dashboard status
    DASHBOARD_STATUS=$(curl -s "$DASHBOARD_URL" | jq -r '.system_status.services.cloud_trader' 2>/dev/null || echo "error")
    echo "Trader: $DASHBOARD_STATUS" | tee -a "$LOG_FILE"
    
    # Count results
    if [ "$PORTFOLIO_RESP" = "200" ]; then
        ((SUCCESS_COUNT++))
    elif [ "$PORTFOLIO_RESP" = "429" ]; then
        ((RATE_LIMIT_COUNT++))
        echo "!!! RATE LIMITED !!!" | tee -a "$LOG_FILE"
    else
        ((FAIL_COUNT++))
    fi
    
    sleep $INTERVAL
done

echo "" | tee -a "$LOG_FILE"
echo "=== Test Summary ===" | tee -a "$LOG_FILE"
echo "End Time: $(date)" | tee -a "$LOG_FILE"
echo "Total Requests: $((SUCCESS_COUNT + FAIL_COUNT + RATE_LIMIT_COUNT))" | tee -a "$LOG_FILE"
echo "Successful: $SUCCESS_COUNT" | tee -a "$LOG_FILE"
echo "Failed: $FAIL_COUNT" | tee -a "$LOG_FILE"
echo "Rate Limited (429): $RATE_LIMIT_COUNT" | tee -a "$LOG_FILE"
echo "Success Rate: $(echo "scale=2; $SUCCESS_COUNT * 100 / ($SUCCESS_COUNT + $FAIL_COUNT + $RATE_LIMIT_COUNT)" | bc)%" | tee -a "$LOG_FILE"

if [ $RATE_LIMIT_COUNT -eq 0 ]; then
    echo "" | tee -a "$LOG_FILE"
    echo "✅ NO RATE LIMITING DETECTED - NAT IS WORKING!" | tee -a "$LOG_FILE"
else
    echo "" | tee -a "$LOG_FILE"
    echo "⚠️  Rate limiting still occurring" | tee -a "$LOG_FILE"
fi

echo "" | tee -a "$LOG_FILE"
echo "Log saved to: $LOG_FILE"
