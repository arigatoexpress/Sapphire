#!/bin/bash

# Deployment Validation Script
# Comprehensive health checks for Infrastructure as Code deployments

set -e

NAMESPACE="trading-system"
EXIT_ON_FAILURE=false

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
    if [ "$EXIT_ON_FAILURE" = true ]; then
        exit 1
    fi
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --namespace=*)
            NAMESPACE="${1#*=}"
            shift
            ;;
        --exit-on-failure)
            EXIT_ON_FAILURE=true
            shift
            ;;
        --help)
            echo "Usage: $0 [--namespace=NAMESPACE] [--exit-on-failure]"
            echo ""
            echo "Validate Infrastructure as Code deployment health"
            echo ""
            echo "Options:"
            echo "  --namespace       Target namespace (default: trading-system)"
            echo "  --exit-on-failure Exit on first failure (default: continue)"
            echo "  --help            Show this help"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

CHECKS_PASSED=0
TOTAL_CHECKS=0

check() {
    local name="$1"
    local command="$2"
    
    ((TOTAL_CHECKS++))
    log_info "Checking $name..."
    
    if eval "$command" >/dev/null 2>&1; then
        log_success "$name: PASSED"
        ((CHECKS_PASSED++))
        return 0
    else
        log_error "$name: FAILED"
        return 1
    fi
}

# Namespace checks
check_namespace() {
    check "Namespace existence" "kubectl get namespace '$NAMESPACE'"
    
    local phase
    phase=$(kubectl get namespace "$NAMESPACE" -o jsonpath='{.status.phase}' 2>/dev/null)
    if [ "$phase" = "Active" ]; then
        log_success "Namespace phase: Active"
    else
        log_error "Namespace phase: $phase"
    fi
}

# Resource quota checks
check_resource_quotas() {
    check "Resource quota" "kubectl get resourcequota production-trading-quota -n '$NAMESPACE'"
    
    # Check if quotas are reasonable
    local cpu_limit
    cpu_limit=$(kubectl get resourcequota production-trading-quota -n "$NAMESPACE" -o jsonpath='{.spec.hard.limits\.cpu}' 2>/dev/null)
    if [ -n "$cpu_limit" ]; then
        log_success "CPU limit: $cpu_limit"
    fi
}

# Secret checks
check_secrets() {
    local required_secrets=("aster-dex-credentials" "telegram-secret")
    
    for secret in "${required_secrets[@]}"; do
        check "Secret: $secret" "kubectl get secret '$secret' -n '$NAMESPACE'"
    done
}

# ConfigMap checks
check_configmaps() {
    local required_configmaps=("system-config" "agent-resource-tiers")
    
    for configmap in "${required_configmaps[@]}"; do
        check "ConfigMap: $configmap" "kubectl get configmap '$configmap' -n '$NAMESPACE'"
    done
}

# Infrastructure component checks
check_infrastructure() {
    local components=("redis" "trading-coordinator")
    
    for component in "${components[@]}"; do
        check "Deployment: $component" "kubectl get deployment '$component' -n '$NAMESPACE'"
        
        # Check if deployment is ready
        local ready_replicas desired_replicas
        ready_replicas=$(kubectl get deployment "$component" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
        desired_replicas=$(kubectl get deployment "$component" -n "$NAMESPACE" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "0")
        
        if [ "$ready_replicas" = "$desired_replicas" ] && [ "$desired_replicas" != "0" ]; then
            log_success "$component replicas: $ready_replicas/$desired_replicas READY"
        else
            log_error "$component replicas: $ready_replicas/$desired_replicas NOT READY"
        fi
        
        # Check service
        check "Service: ${component}-service" "kubectl get service '${component}-service' -n '$NAMESPACE'"
    done
}

# Agent checks
check_agents() {
    local agent_count
    agent_count=$(kubectl get deployments -n "$NAMESPACE" -l component=trading-agent --no-headers 2>/dev/null | wc -l)
    
    log_info "Found $agent_count trading agents"
    
    if [ "$agent_count" -gt 0 ]; then
        kubectl get deployments -n "$NAMESPACE" -l component=trading-agent --no-headers | while read -r line; do
            local agent_name ready desired
            agent_name=$(echo "$line" | awk '{print $1}')
            ready=$(echo "$line" | awk '{print $2}' | cut -d'/' -f1)
            desired=$(echo "$line" | awk '{print $2}' | cut -d'/' -f2)
            
            if [ "$ready" = "$desired" ]; then
                log_success "Agent $agent_name: READY ($ready/$desired)"
            else
                log_error "Agent $agent_name: NOT READY ($ready/$desired)"
            fi
        done
    fi
}

# Health checks
check_health() {
    log_info "Performing health checks..."
    
    # Check coordinator health
    if kubectl get service coordinator-service -n "$NAMESPACE" >/dev/null 2>&1; then
        # Port forward and test health endpoint
        local pod_name
        pod_name=$(kubectl get pods -n "$NAMESPACE" -l app=trading-coordinator -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
        
        if [ -n "$pod_name" ]; then
            # Try to exec health check
            if kubectl exec -n "$NAMESPACE" "$pod_name" -- curl -f -s http://localhost:8080/health >/dev/null 2>&1; then
                log_success "Coordinator health: OK"
            else
                log_warning "Coordinator health: UNRESPONSIVE"
            fi
        fi
    fi
}

# Resource usage checks
check_resources() {
    log_info "Checking resource usage..."
    
    # Get current resource usage
    if kubectl top pods -n "$NAMESPACE" >/dev/null 2>&1; then
        local total_cpu total_memory
        total_cpu=$(kubectl top pods -n "$NAMESPACE" --no-headers | awk '{sum += $2} END {print sum}' | sed 's/m//' || echo "0")
        total_memory=$(kubectl top pods -n "$NAMESPACE" --no-headers | awk '{sum += $3} END {print sum}' | sed 's/Mi//' || echo "0")
        
        log_success "Current usage: ${total_cpu}m CPU, ${total_memory}Mi Memory"
        
        # Check against quotas
        local cpu_quota mem_quota
        cpu_quota=$(kubectl get resourcequota production-trading-quota -n "$NAMESPACE" -o jsonpath='{.spec.hard.requests\.cpu}' 2>/dev/null | sed 's/m//' || echo "0")
        mem_quota=$(kubectl get resourcequota production-trading-quota -n "$NAMESPACE" -o jsonpath='{.spec.hard.requests\.memory}' 2>/dev/null | sed 's/Mi//' || echo "0")
        
        if [ "$cpu_quota" -gt 0 ] && [ "$total_cpu" -lt "$cpu_quota" ]; then
            local cpu_percent=$((total_cpu * 100 / cpu_quota))
            log_success "CPU quota usage: $cpu_percent%"
        fi
        
        if [ "$mem_quota" -gt 0 ] && [ "$total_memory" -lt "$mem_quota" ]; then
            local mem_percent=$((total_memory * 100 / mem_quota))
            log_success "Memory quota usage: $mem_percent%"
        fi
    else
        log_warning "Metrics server not available for resource monitoring"
    fi
}

# Generate report
generate_report() {
    echo ""
    echo "📊 VALIDATION REPORT"
    echo "==================="
    echo "Namespace: $NAMESPACE"
    echo "Timestamp: $(date)"
    echo ""
    echo "Checks Passed: $CHECKS_PASSED/$TOTAL_CHECKS"
    
    local success_rate=$((CHECKS_PASSED * 100 / TOTAL_CHECKS))
    
    if [ $success_rate -ge 90 ]; then
        log_success "Overall Status: EXCELLENT ($success_rate% pass rate)"
    elif [ $success_rate -ge 75 ]; then
        log_warning "Overall Status: GOOD ($success_rate% pass rate)"
    else
        log_error "Overall Status: NEEDS ATTENTION ($success_rate% pass rate)"
    fi
    
    echo ""
    echo "🎯 RECOMMENDATIONS:"
    
    if [ $CHECKS_PASSED -lt $TOTAL_CHECKS ]; then
        echo "• Run './cleanup-infrastructure.sh --dry-run' to identify issues"
        echo "• Check pod logs: kubectl logs -n $NAMESPACE <pod-name>"
        echo "• Verify secrets: kubectl get secrets -n $NAMESPACE"
    fi
    
    if [ $success_rate -ge 90 ]; then
        echo "• System is healthy and ready for production"
        echo "• Consider enabling auto-scaling: kubectl autoscale deployment..."
    fi
}

# Main execution
main() {
    echo "🔍 INFRASTRUCTURE VALIDATION"
    echo "============================"
    echo "Namespace: $NAMESPACE"
    if [ "$EXIT_ON_FAILURE" = true ]; then
        echo "Mode: Strict (exit on first failure)"
    else
        echo "Mode: Comprehensive (report all issues)"
    fi
    echo ""
    
    check_namespace
    check_resource_quotas
    check_secrets
    check_configmaps
    check_infrastructure
    check_agents
    check_health
    check_resources
    generate_report
}

# Run main function
main "$@"
