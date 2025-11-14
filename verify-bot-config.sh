#!/bin/bash

# Bot Configuration Verification Script
# Ensures new bots are properly configured with Telegram and Aster DEX

set -e

NAMESPACE="trading"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

usage() {
    echo "Usage: $0 <bot-name>"
    echo ""
    echo "Verify that a bot is properly configured with Telegram and Aster DEX"
    echo ""
    echo "EXAMPLES:"
    echo "  $0 momentum-bot"
    echo "  $0 sentiment-analysis-bot"
}

# Check if bot name provided
if [ $# -eq 0 ]; then
    usage
    exit 1
fi

BOT_NAME="$1"

echo "🔍 BOT CONFIGURATION VERIFICATION"
echo "=================================="
echo "Bot Name: $BOT_NAME"
echo "Namespace: $NAMESPACE"
echo ""

CHECKS_PASSED=0
TOTAL_CHECKS=0

check_resource() {
    local resource_type="$1"
    local resource_name="$2"
    local description="$3"
    
    ((TOTAL_CHECKS++))
    
    if kubectl get "$resource_type" "$resource_name" -n "$NAMESPACE" >/dev/null 2>&1; then
        log_success "$description: EXISTS"
        ((CHECKS_PASSED++))
        return 0
    else
        log_error "$description: MISSING"
        return 1
    fi
}

check_pod_status() {
    local pod_status
    pod_status=$(kubectl get pods -n "$NAMESPACE" -l "app=$BOT_NAME" --no-headers -o custom-columns=":status.phase" 2>/dev/null | head -1)
    
    ((TOTAL_CHECKS++))
    
    if [ "$pod_status" = "Running" ]; then
        log_success "Pod Status: RUNNING"
        ((CHECKS_PASSED++))
        return 0
    else
        log_error "Pod Status: $pod_status"
        return 1
    fi
}

check_deployment_ready() {
    local ready_status
    ready_status=$(kubectl get deployment "$BOT_NAME" -n "$NAMESPACE" --no-headers -o custom-columns=":status.readyReplicas,:status.replicas" 2>/dev/null)
    
    ((TOTAL_CHECKS++))
    
    local ready=$(echo "$ready_status" | cut -d' ' -f1)
    local total=$(echo "$ready_status" | cut -d' ' -f2)
    
    if [ "$ready" = "$total" ] && [ "$total" -gt 0 ]; then
        log_success "Deployment: $ready/$total READY"
        ((CHECKS_PASSED++))
        return 0
    else
        log_error "Deployment: $ready_status NOT READY"
        return 1
    fi
}

check_environment_variable() {
    local var_name="$1"
    local var_value
    
    ((TOTAL_CHECKS++))
    
    var_value=$(kubectl exec -n "$NAMESPACE" deployment/"$BOT_NAME" -- env 2>/dev/null | grep "^$var_name=" | cut -d'=' -f2-)
    
    if [ -n "$var_value" ]; then
        if [[ "$var_name" == *"TOKEN"* ]] || [[ "$var_name" == *"SECRET"* ]] || [[ "$var_name" == *"KEY"* ]]; then
            # Mask sensitive values
            masked_value="${var_value:0:10}..."
        else
            masked_value="$var_value"
        fi
        log_success "Environment $var_name: SET ($masked_value)"
        ((CHECKS_PASSED++))
        return 0
    else
        log_error "Environment $var_name: NOT SET"
        return 1
    fi
}

check_health_endpoint() {
    ((TOTAL_CHECKS++))
    
    local pod_name
    pod_name=$(kubectl get pods -n "$NAMESPACE" -l "app=$BOT_NAME" --no-headers -o custom-columns=":metadata.name" 2>/dev/null | head -1)
    
    if [ -n "$pod_name" ]; then
        # Try to curl health endpoint
        if kubectl exec -n "$NAMESPACE" "$pod_name" -- curl -f -s http://localhost:8080/health >/dev/null 2>&1; then
            log_success "Health Endpoint: RESPONDING"
            ((CHECKS_PASSED++))
            return 0
        else
            log_warning "Health Endpoint: NOT RESPONDING"
            return 1
        fi
    else
        log_error "Health Endpoint: NO POD FOUND"
        return 1
    fi
}

# Run all checks
echo "📋 CHECKING RESOURCES..."
check_resource "configmap" "$BOT_NAME-config" "ConfigMap"
check_resource "deployment" "$BOT_NAME" "Deployment"
check_resource "service" "$BOT_NAME-service" "Service"

echo ""
echo "🔧 CHECKING DEPLOYMENT STATUS..."
check_pod_status
check_deployment_ready

echo ""
echo "⚙️ CHECKING CONFIGURATION INJECTION..."
check_environment_variable "BOT_NAME"
check_environment_variable "BOT_STRATEGY"
check_environment_variable "CAPITAL_ALLOCATION"
check_environment_variable "RISK_LEVEL"
check_environment_variable "ASTER_API_KEY"
check_environment_variable "ASTER_API_SECRET"
check_environment_variable "TELEGRAM_BOT_TOKEN"
check_environment_variable "TELEGRAM_CHAT_ID"
check_environment_variable "LOG_LEVEL"
check_environment_variable "METRICS_ENABLED"

echo ""
echo "🏥 CHECKING HEALTH..."
check_health_endpoint

# Summary
echo ""
echo "📊 VERIFICATION SUMMARY"
echo "======================="
echo "Checks Passed: $CHECKS_PASSED/$TOTAL_CHECKS"

if [ "$CHECKS_PASSED" -eq "$TOTAL_CHECKS" ]; then
    echo ""
    log_success "🎉 ALL CHECKS PASSED!"
    log_success "Bot '$BOT_NAME' is properly configured and ready for trading!"
    echo ""
    echo "✅ Telegram notifications: CONFIGURED"
    echo "✅ Aster DEX API access: ENABLED"
    echo "✅ Health monitoring: ACTIVE"
    echo "✅ Capital allocation: SET"
    exit 0
else
    echo ""
    log_error "❌ $((TOTAL_CHECKS - CHECKS_PASSED)) checks failed"
    log_warning "Bot '$BOT_NAME' may have configuration issues"
    echo ""
    echo "🔧 TROUBLESHOOTING:"
    echo "• Check pod logs: kubectl logs -n $NAMESPACE deployment/$BOT_NAME"
    echo "• Check events: kubectl get events -n $NAMESPACE --sort-by=.metadata.creationTimestamp | tail -10"
    echo "• Re-run initialization: ./initialize-new-bot.sh --name $BOT_NAME [other options]"
    exit 1
fi
