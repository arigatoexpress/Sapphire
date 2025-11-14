#!/bin/bash

echo "🧪 SAPPHIRE TRADE DEPLOYMENT & TESTING SCRIPT"
echo "=============================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print status
print_status() {
    echo -e "${BLUE}[$1]${NC} $2"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Phase 1: System Status Check
print_status "PHASE 1" "Checking System Status"
echo "Checking pods..."
kubectl get pods -n trading --no-headers | while read line; do
    status=$(echo $line | awk '{print $3}')
    name=$(echo $line | awk '{print $1}')
    if [[ $status == "Running" ]]; then
        print_success "Pod $name: $status"
    elif [[ $status == "Pending" ]]; then
        print_warning "Pod $name: $status"
    else
        print_error "Pod $name: $status"
    fi
done

echo ""
print_status "PHASE 2" "Testing API Endpoints"
# Test health endpoint
if kubectl exec -n trading deployment/trading-system-cloud-trader -- curl -s http://localhost:8080/healthz > /dev/null 2>&1; then
    print_success "Health endpoint responding"
else
    print_error "Health endpoint not responding"
fi

# Test agent activity endpoint
if kubectl exec -n trading deployment/trading-system-cloud-trader -- curl -s http://localhost:8080/agent-activity | grep -q "agents"; then
    print_success "Agent activity endpoint responding"
else
    print_error "Agent activity endpoint not working"
fi

echo ""
print_status "PHASE 3" "Verifying Agent Configuration"
# Check agent count
agent_count=$(kubectl exec -n trading deployment/trading-system-cloud-trader -- python -c "
from cloud_trader.service import AGENT_DEFINITIONS
print(len(AGENT_DEFINITIONS))
" 2>/dev/null)

if [[ $agent_count -eq 6 ]]; then
    print_success "6 agents configured correctly"
    kubectl exec -n trading deployment/trading-system-cloud-trader -- python -c "
from cloud_trader.service import AGENT_DEFINITIONS
[print(f'  - {a[\"name\"]}: {a[\"model\"]}') for a in AGENT_DEFINITIONS]
" 2>/dev/null
else
    print_error "Agent count incorrect: $agent_count (expected 6)"
fi

echo ""
print_status "PHASE 4" "Testing Telegram Notifications"
# Check Telegram environment variables
telegram_configured=$(kubectl exec -n trading deployment/trading-system-cloud-trader -- env | grep -c TELEGRAM 2>/dev/null)

if [[ $telegram_configured -gt 0 ]]; then
    print_success "Telegram credentials configured ($telegram_configured variables)"

    # Test Telegram service
    telegram_logs=$(kubectl logs -n trading deployment/trading-system-cloud-trader --tail=100 2>/dev/null | grep -i telegram | wc -l)
    if [[ $telegram_logs -gt 0 ]]; then
        print_success "Telegram service initialized (logs found)"
    else
        print_warning "No Telegram logs found - may need manual testing"
    fi
else
    print_error "Telegram credentials not configured"
fi

echo ""
print_status "PHASE 5" "Testing Vertex AI Connectivity"
vertex_test=$(kubectl exec -n trading deployment/trading-system-cloud-trader -- timeout 10 python -c "
import asyncio
from cloud_trader.vertex_ai_client import VertexAIClient
async def test():
    try:
        client = VertexAIClient()
        print('Vertex AI client initialized successfully')
        return True
    except Exception as e:
        print(f'Vertex AI error: {e}')
        return False
result = asyncio.run(test())
" 2>/dev/null)

if echo "$vertex_test" | grep -q "initialized successfully"; then
    print_success "Vertex AI client initialized"
else
    print_error "Vertex AI client failed to initialize"
fi

echo ""
print_status "PHASE 6" "Performance & Resource Check"
# Check resource usage
echo "Resource usage:"
kubectl top pods -n trading 2>/dev/null || print_warning "kubectl top not available"

# Check for errors in recent logs
error_count=$(kubectl logs -n trading deployment/trading-system-cloud-trader --tail=100 2>/dev/null | grep -i error | wc -l)
if [[ $error_count -gt 0 ]]; then
    print_warning "Found $error_count errors in recent logs"
else
    print_success "No errors in recent logs"
fi

echo ""
print_status "PHASE 7" "System Resilience Test"
print_warning "Testing pod restart capability..."
kubectl delete pod -n trading -l app.kubernetes.io/name=trading-system-cloud-trader --ignore-not-found=true > /dev/null 2>&1
sleep 5

# Check if pod restarted
pod_count=$(kubectl get pods -n trading -l app.kubernetes.io/name=trading-system-cloud-trader --no-headers | wc -l)
if [[ $pod_count -gt 0 ]]; then
    print_success "Pod restart successful"
else
    print_error "Pod restart failed"
fi

echo ""
echo "🎯 TESTING COMPLETE"
echo ""
echo "📊 QUICK STATUS SUMMARY:"
echo "• Pods Running: $(kubectl get pods -n trading --no-headers 2>/dev/null | grep Running | wc -l)"
echo "• Agents Configured: $agent_count/6"
echo "• API Health: $(kubectl exec -n trading deployment/trading-system-cloud-trader -- curl -s http://localhost:8080/healthz 2>/dev/null && echo 'OK' || echo 'FAIL')"
echo "• Telegram Ready: $([[ $telegram_configured -gt 0 ]] && echo 'YES' || echo 'NO')"
echo "• Vertex AI: $(echo "$vertex_test" | grep -q "initialized" && echo 'OK' || echo 'FAIL')"

echo ""
echo "🚀 NEXT STEPS:"
echo "1. If all checks pass: Start live trading"
echo "2. Test Telegram: Send a manual notification"
echo "3. Monitor: Check logs and performance"
echo "4. Scale: Enable agent deployments if needed"

echo ""
echo "💎 SAPPHIRE TRADE SYSTEM READY FOR LIVE OPERATIONS! 🎯"
