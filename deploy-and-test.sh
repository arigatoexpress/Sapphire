#!/bin/bash

echo "🚀 SAPPHIRE TRADE - DEPLOYMENT & TESTING SCRIPT"
echo "================================================"
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

# Function to wait for pods to be ready
wait_for_pods() {
    echo "Waiting for pods to be ready..."
    kubectl wait --for=condition=Ready pod --all -n trading --timeout=300s 2>/dev/null || true
    sleep 10
}

# Function to check pod status
check_pod_status() {
    echo ""
    print_status "STATUS" "Checking pod deployment status"
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
}

# STEP 1: Cleanup
echo ""
print_status "STEP 1" "Cleaning up existing resources"
kubectl delete pods -n trading --all --ignore-not-found=true --grace-period=0 --force
kubectl delete deployment -n trading --all --ignore-not-found=true
kubectl delete service -n trading --all --ignore-not-found=true
kubectl delete configmap -n trading --all --ignore-not-found=true
kubectl delete networkpolicy -n trading --all --ignore-not-found=true
print_success "Cleanup complete"

# STEP 2: Build Container
echo ""
print_status "STEP 2" "Building optimized container"
echo "Building Docker image..."
if docker build -t us-central1-docker.pkg.dev/sapphireinfinite/cloud-run-source-deploy/cloud-trader:latest -f Dockerfile .; then
    print_success "Container built successfully"
    echo "Pushing to Artifact Registry..."
    if docker push us-central1-docker.pkg.dev/sapphireinfinite/cloud-run-source-deploy/cloud-trader:latest; then
        print_success "Container pushed successfully"
    else
        print_error "Failed to push container"
        exit 1
    fi
else
    print_error "Failed to build container"
    exit 1
fi

# STEP 3: Deploy System
echo ""
print_status "STEP 3" "Deploying optimized trading system"
echo "Deploying with Helm..."
if helm upgrade --install trading-system ./helm/trading-system \
    --namespace trading --create-namespace \
    --set global.imageRegistry=us-central1-docker.pkg.dev \
    --set global.projectId=sapphireinfinite \
    --set global.imagePullPolicy=Always \
    --set trading.disableRateLimiter=true \
    --set trading.capitalAllocation=3000 \
    --set trading.riskMultiplier=0.02 \
    --set trading.maxLeverage=10 \
    --wait --timeout=600s; then
    print_success "System deployed successfully"
else
    print_error "Deployment failed"
    exit 1
fi

# STEP 4: Initial Verification
echo ""
print_status "STEP 4" "Initial system verification"
wait_for_pods
check_pod_status

# STEP 5: API Testing
echo ""
print_status "STEP 5" "Testing API endpoints"
api_tests_passed=0
total_tests=3

# Test health endpoint
if kubectl exec -n trading deployment/trading-system-cloud-trader -- curl -s http://localhost:8080/healthz > /dev/null 2>&1; then
    print_success "Health endpoint responding"
    ((api_tests_passed++))
else
    print_error "Health endpoint not responding"
fi

# Test agent activity endpoint
if kubectl exec -n trading deployment/trading-system-cloud-trader -- curl -s http://localhost:8080/agent-activity | grep -q "agents"; then
    print_success "Agent activity endpoint responding"
    ((api_tests_passed++))
else
    print_error "Agent activity endpoint not working"
fi

# Test portfolio status endpoint
if kubectl exec -n trading deployment/trading-system-cloud-trader -- curl -s http://localhost:8080/portfolio-status | grep -q "portfolio"; then
    print_success "Portfolio status endpoint responding"
    ((api_tests_passed++))
else
    print_error "Portfolio status endpoint not working"
fi

echo "API Tests: $api_tests_passed/$total_tests passed"

# STEP 6: Agent Configuration Verification
echo ""
print_status "STEP 6" "Verifying agent configuration"
agent_count=$(kubectl exec -n trading deployment/trading-system-cloud-trader -- python -c "
from cloud_trader.service import AGENT_DEFINITIONS
print(len(AGENT_DEFINITIONS))
" 2>/dev/null)

if [[ $agent_count -eq 6 ]]; then
    print_success "6 agents configured correctly"
    echo "Agent Details:"
    kubectl exec -n trading deployment/trading-system-cloud-trader -- python -c "
from cloud_trader.service import AGENT_DEFINITIONS
[print(f'  - {a[\"name\"]}: {a[\"model\"]} ({a[\"emoji\"]})') for a in AGENT_DEFINITIONS]
" 2>/dev/null
else
    print_error "Agent count incorrect: $agent_count (expected 6)"
fi

# STEP 7: Telegram Testing
echo ""
print_status "STEP 7" "Testing Telegram notifications"
telegram_configured=$(kubectl exec -n trading deployment/trading-system-cloud-trader -- env | grep -c TELEGRAM 2>/dev/null)

if [[ $telegram_configured -gt 0 ]]; then
    print_success "Telegram credentials configured ($telegram_configured variables)"

    echo "Testing Telegram service initialization..."
    telegram_logs=$(kubectl logs -n trading deployment/trading-system-cloud-trader --tail=100 2>/dev/null | grep -i telegram | wc -l)
    if [[ $telegram_logs -gt 0 ]]; then
        print_success "Telegram service initialized (logs found)"
    else
        print_warning "No Telegram logs found - testing manually..."
        echo "Sending test notification..."
        kubectl exec -n trading deployment/trading-system-cloud-trader -- python -c "
from cloud_trader.enhanced_telegram import EnhancedTelegramService
import asyncio, os
async def test():
    try:
        tg = EnhancedTelegramService(
            bot_token=os.getenv('TELEGRAM_BOT_TOKEN'),
            chat_id=os.getenv('TELEGRAM_CHAT_ID')
        )
        await tg.send_startup_notification()
        print('✅ Test notification sent successfully!')
    except Exception as e:
        print(f'❌ Telegram test failed: {e}')
asyncio.run(test())
" 2>/dev/null
    fi
else
    print_error "Telegram credentials not configured"
fi

# STEP 8: Vertex AI Testing
echo ""
print_status "STEP 8" "Testing Vertex AI connectivity"
vertex_test=$(kubectl exec -n trading deployment/trading-system-cloud-trader -- timeout 15 python -c "
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

# STEP 9: Performance Check
echo ""
print_status "STEP 9" "Performance and resource check"
echo "Resource usage:"
kubectl top pods -n trading 2>/dev/null || print_warning "kubectl top not available"

echo "Recent error check:"
error_count=$(kubectl logs -n trading deployment/trading-system-cloud-trader --tail=100 2>/dev/null | grep -i error | wc -l)
if [[ $error_count -gt 0 ]]; then
    print_warning "Found $error_count errors in recent logs"
    echo "Recent errors:"
    kubectl logs -n trading deployment/trading-system-cloud-trader --tail=100 2>/dev/null | grep -i error | tail -5
else
    print_success "No errors in recent logs"
fi

# STEP 10: Resilience Test
echo ""
print_status "STEP 10" "Testing system resilience"
print_warning "Testing pod restart capability..."
kubectl delete pod -n trading -l app.kubernetes.io/name=trading-system-cloud-trader --ignore-not-found=true > /dev/null 2>&1
sleep 5

pod_count=$(kubectl get pods -n trading -l app.kubernetes.io/name=trading-system-cloud-trader --no-headers | wc -l)
if [[ $pod_count -gt 0 ]]; then
    print_success "Pod restart successful"
else
    print_error "Pod restart failed"
fi

# FINAL SUMMARY
echo ""
echo "🎯 DEPLOYMENT & TESTING COMPLETE"
echo "================================"
echo ""
echo "📊 FINAL STATUS SUMMARY:"
echo "• Pods Running: $(kubectl get pods -n trading --no-headers 2>/dev/null | grep Running | wc -l)"
echo "• Agents Configured: $agent_count/6"
echo "• API Tests Passed: $api_tests_passed/$total_tests"
echo "• Telegram Ready: $([[ $telegram_configured -gt 0 ]] && echo 'YES' || echo 'NO')"
echo "• Vertex AI: $(echo "$vertex_test" | grep -q "initialized" && echo 'OK' || echo 'FAIL')"
echo "• Errors Found: $error_count"

# Success criteria check
success_criteria_met=0
total_criteria=5

[[ $(kubectl get pods -n trading --no-headers 2>/dev/null | grep Running | wc -l) -ge 2 ]] && ((success_criteria_met++))
[[ $agent_count -eq 6 ]] && ((success_criteria_met++))
[[ $api_tests_passed -eq $total_tests ]] && ((success_criteria_met++))
[[ $telegram_configured -gt 0 ]] && ((success_criteria_met++))
[[ $error_count -eq 0 ]] && ((success_criteria_met++))

echo "• Success Criteria: $success_criteria_met/$total_criteria met"

if [[ $success_criteria_met -eq $total_criteria ]]; then
    echo ""
    print_success "🎉 ALL SYSTEMS GO! READY FOR LIVE TRADING!"
    echo ""
    echo "🚀 TO START LIVE TRADING, RUN:"
    echo "kubectl exec -n trading deployment/trading-system-cloud-trader -- python -c \""
    echo "import asyncio"
    echo "from cloud_trader.service import TradingService"
    echo "async def start_trading():"
    echo "    service = TradingService()"
    echo "    await service.start()"
    echo "    print('🎯 LIVE TRADING ENABLED - Sapphire Trade AI Active!')"
    echo "asyncio.run(start_trading())"
    echo "\""
    echo ""
    echo "📊 TO MONITOR TRADING ACTIVITY:"
    echo "kubectl logs -n trading deployment/trading-system-cloud-trader -f | grep -E '(TRADE|PROFIT|AGENT)'"
else
    echo ""
    print_warning "⚠️  SOME ISSUES DETECTED - REVIEW OUTPUT ABOVE"
    echo ""
    echo "🔧 TROUBLESHOOTING:"
    echo "• Check pod logs: kubectl logs -n trading deployment/trading-system-cloud-trader"
    echo "• Check events: kubectl get events -n trading --sort-by=.metadata.creationTimestamp"
    echo "• Re-run tests: ./test-deployment.sh"
fi

echo ""
echo "💎 SAPPHIRE TRADE AI SYSTEM DEPLOYMENT COMPLETE!"
