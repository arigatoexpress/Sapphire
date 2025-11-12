#!/bin/bash
echo "🧪 COMPREHENSIVE END-TO-END TESTING - SAPPHIRE TRADING"
echo "======================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test results
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

log_test() {
    local test_name="$1"
    local result="$2"
    local details="$3"

    ((TESTS_TOTAL++))
    if [ "$result" = "PASS" ]; then
        ((TESTS_PASSED++))
        echo -e "${GREEN}✅ PASS${NC} - $test_name"
        [ -n "$details" ] && echo -e "   ${BLUE}$details${NC}"
    else
        ((TESTS_FAILED++))
        echo -e "${RED}❌ FAIL${NC} - $test_name"
        [ -n "$details" ] && echo -e "   ${RED}$details${NC}"
    fi
}

echo ""
echo "🔍 SYSTEM HEALTH CHECKS"
echo "========================"

# 1. Pod Health Check
echo ""
echo "📦 Testing Pod Health..."
TOTAL_PODS=$(kubectl get pods -n trading --no-headers | wc -l)
READY_PODS=$(kubectl get pods -n trading --no-headers | grep "1/1" | wc -l)

if [ "$READY_PODS" -eq "$TOTAL_PODS" ] && [ "$TOTAL_PODS" -eq 7 ]; then
    log_test "Pod Health" "PASS" "All 7 pods running (4 AI agents + 2 cloud-trader + 1 system)"
else
    log_test "Pod Health" "FAIL" "Expected 7 pods, found $TOTAL_PODS ready, $READY_PODS total"
fi

# 2. Infrastructure Check
echo ""
echo "🌐 Testing Infrastructure..."
LB_IP=$(kubectl get ingress -n trading -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}' 2>/dev/null)
CERT_STATUS=$(kubectl get managedcertificate -n trading -o jsonpath='{.items[0].status.certificateStatus}' 2>/dev/null)

if [ -n "$LB_IP" ]; then
    log_test "Load Balancer" "PASS" "External IP: $LB_IP"
else
    log_test "Load Balancer" "FAIL" "No external IP found"
fi

if [ "$CERT_STATUS" = "Active" ]; then
    log_test "SSL Certificate" "PASS" "Certificate is active"
else
    log_test "SSL Certificate" "FAIL" "Certificate status: $CERT_STATUS"
fi

# 3. API Health Check
echo ""
echo "🔗 Testing API Endpoints..."
if [ -n "$LB_IP" ]; then
    # Health check
    HEALTH_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 --max-time 30 "http://$LB_IP/healthz" 2>/dev/null || echo "failed")
    if [ "$HEALTH_CODE" = "200" ]; then
        log_test "API Health" "PASS" "HTTP 200 response"
    else
        log_test "API Health" "FAIL" "Health check failed (code: $HEALTH_CODE)"
    fi

    # Portfolio endpoint
    PORTFOLIO_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 --max-time 30 "http://$LB_IP/portfolio-status" 2>/dev/null || echo "failed")
    if [ "$PORTFOLIO_CODE" = "200" ]; then
        log_test "Portfolio API" "PASS" "Portfolio endpoint responding"
    else
        log_test "Portfolio API" "FAIL" "Portfolio API failed (code: $PORTFOLIO_CODE)"
    fi
else
    log_test "API Health" "FAIL" "Cannot test API - no load balancer IP"
    log_test "Portfolio API" "FAIL" "Cannot test API - no load balancer IP"
fi

# 4. HTTPS Testing
echo ""
echo "🔒 Testing HTTPS Endpoints..."
if [ -n "$LB_IP" ] && [ "$CERT_STATUS" = "Active" ]; then
    # HTTPS health check
    HTTPS_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 --max-time 30 "https://api.sapphiretrade.xyz/healthz" 2>/dev/null || echo "failed")
    if [ "$HTTPS_CODE" = "200" ]; then
        log_test "HTTPS API" "PASS" "HTTPS endpoint secure and responding"
    else
        log_test "HTTPS API" "FAIL" "HTTPS failed (code: $HTTPS_CODE)"
    fi
else
    log_test "HTTPS API" "FAIL" "HTTPS not available - cert not active or no LB IP"
fi

# 5. Frontend Testing
echo ""
echo "🖥️  Testing Frontend..."
FRONTEND_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 --max-time 30 "https://sapphireinfinite.web.app" 2>/dev/null || echo "failed")
if [ "$FRONTEND_CODE" = "200" ]; then
    log_test "Frontend" "PASS" "Firebase hosting responding"
else
    log_test "Frontend" "FAIL" "Frontend failed (code: $FRONTEND_CODE)"
fi

# 6. AI Agent Verification
echo ""
echo "🤖 Testing AI Agents..."
AGENT_PODS=$(kubectl get pods -n trading -l app=cloud-trader --no-headers | grep -v "cloud-trader-" | wc -l)
if [ "$AGENT_PODS" -eq 4 ]; then
    log_test "AI Agents" "PASS" "All 4 AI agents running"
else
    log_test "AI Agents" "FAIL" "Expected 4 AI agents, found $AGENT_PODS"
fi

# 7. Enhanced Telegram Bot Test
echo ""
echo "📱 Testing Enhanced Telegram Bot..."
# Check if Telegram service is initialized in logs
TELEGRAM_LOGS=$(kubectl logs -n trading deployment/cloud-trader --tail=50 2>/dev/null | grep -i "telegram\|enhanced" | wc -l)
if [ "$TELEGRAM_LOGS" -gt 0 ]; then
    log_test "Telegram Bot" "PASS" "Enhanced Telegram bot initialized"
else
    log_test "Telegram Bot" "WARN" "Cannot verify Telegram bot from logs"
fi

# 8. Database Connectivity
echo ""
echo "💾 Testing Database..."
DB_LOGS=$(kubectl logs -n trading deployment/cloud-trader --tail=20 2>/dev/null | grep -i "database\|bigquery\|connected" | wc -l)
if [ "$DB_LOGS" -gt 0 ]; then
    log_test "Database" "PASS" "Database connectivity established"
else
    log_test "Database" "FAIL" "No database connectivity logs found"
fi

# 9. Trading Engine Test
echo ""
echo "⚡ Testing Trading Engine..."
ENGINE_LOGS=$(kubectl logs -n trading deployment/cloud-trader --tail=30 2>/dev/null | grep -i "trading.*start\|engine.*ready\|strategy.*loaded" | wc -l)
if [ "$ENGINE_LOGS" -gt 0 ]; then
    log_test "Trading Engine" "PASS" "Trading engine initialized"
else
    log_test "Trading Engine" "FAIL" "Trading engine not ready"
fi

# 10. Resource Usage Check
echo ""
echo "📊 Testing Resource Usage..."
NODE_CPU=$(kubectl top nodes 2>/dev/null | grep -v NAME | awk '{print $3}' | sed 's/%//' | head -1)
NODE_MEM=$(kubectl top nodes 2>/dev/null | grep -v NAME | awk '{print $5}' | sed 's/%//' | head -1)

if [ -n "$NODE_CPU" ] && [ "$NODE_CPU" -lt 80 ]; then
    log_test "CPU Usage" "PASS" "CPU usage: ${NODE_CPU}%"
else
    log_test "CPU Usage" "WARN" "High CPU usage: ${NODE_CPU}%"
fi

if [ -n "$NODE_MEM" ] && [ "$NODE_MEM" -lt 85 ]; then
    log_test "Memory Usage" "PASS" "Memory usage: ${NODE_MEM}%"
else
    log_test "Memory Usage" "WARN" "High memory usage: ${NODE_MEM}%"
fi

echo ""
echo "📊 TEST SUMMARY"
echo "=============="
echo "Total Tests: $TESTS_TOTAL"
echo -e "Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Failed: ${RED}$TESTS_FAILED${NC}"

SUCCESS_RATE=$((TESTS_PASSED * 100 / TESTS_TOTAL))
echo "Success Rate: ${SUCCESS_RATE}%"

echo ""
if [ "$TESTS_FAILED" -eq 0 ]; then
    echo -e "${GREEN}🎉 ALL TESTS PASSED! SYSTEM READY FOR PRODUCTION${NC}"
    echo ""
    echo "🚀 NEXT STEPS:"
    echo "1. Update DNS: sapphiretrade.xyz → Firebase Hosting"
    echo "2. Update DNS: api.sapphiretrade.xyz → $LB_IP"
    echo "3. Enable live trading mode"
    echo "4. Monitor first live trades"
    echo ""
    echo "🌟 SAPPHIRE TRADING IS PRODUCTION READY!"
    exit 0
else
    echo -e "${YELLOW}⚠️  SOME TESTS FAILED - REVIEW ISSUES BEFORE GO-LIVE${NC}"
    echo ""
    echo "🔧 TROUBLESHOOTING:"
    echo "- Check pod logs: kubectl logs -n trading deployment/cloud-trader"
    echo "- Verify load balancer: kubectl get ingress -n trading"
    echo "- Test SSL cert: kubectl get managedcertificate -n trading"
    echo "- Check resource usage: kubectl top pods -n trading"
    exit 1
fi
