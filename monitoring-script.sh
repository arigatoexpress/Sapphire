#!/bin/bash

# Sapphire Trade System Monitoring Script
# Monitors deployments, cleans up old resources, and validates system health

set -e

NAMESPACE="trading"
PROJECT="sapphireinfinite"

echo "🤖 SAPPHIRE TRADE SYSTEM MONITORING"
echo "===================================="
echo "🕐 $(date)"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
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

# 1. Check cluster connectivity
check_cluster() {
    log_info "Checking Kubernetes cluster connectivity..."
    
    if ! kubectl cluster-info >/dev/null 2>&1; then
        log_error "Cannot connect to Kubernetes cluster"
        return 1
    fi
    
    log_success "Cluster connectivity OK"
    return 0
}

# 2. Check namespace exists
check_namespace() {
    log_info "Checking namespace '$NAMESPACE'..."
    
    if ! kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
        log_error "Namespace '$NAMESPACE' does not exist"
        return 1
    fi
    
    log_success "Namespace '$NAMESPACE' exists"
    return 0
}

# 3. Monitor pod status
monitor_pods() {
    log_info "Monitoring pod status..."
    
    # Get all pods in namespace
    PODS=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
    
    if [ "$PODS" -eq 0 ]; then
        log_warning "No pods found in namespace '$NAMESPACE'"
        return 1
    fi
    
    # Check for unhealthy pods
    UNHEALTHY_PODS=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | grep -v Running | wc -l)
    
    if [ "$UNHEALTHY_PODS" -gt 0 ]; then
        log_warning "Found $UNHEALTHY_PODS unhealthy pods:"
        kubectl get pods -n "$NAMESPACE" | grep -v Running
        return 1
    fi
    
    # List running pods
    RUNNING_PODS=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | grep Running | wc -l)
    log_success "Found $RUNNING_PODS healthy pods"
    
    return 0
}

# 4. Monitor deployments
monitor_deployments() {
    log_info "Monitoring deployments..."
    
    # Get deployment status
    DEPLOYMENTS=$(kubectl get deployments -n "$NAMESPACE" --no-headers 2>/dev/null)
    
    if [ -z "$DEPLOYMENTS" ]; then
        log_warning "No deployments found in namespace '$NAMESPACE'"
        return 1
    fi
    
    echo "$DEPLOYMENTS" | while read -r line; do
        NAME=$(echo "$line" | awk '{print $1}')
        READY=$(echo "$line" | awk '{print $2}')
        UP_TO_DATE=$(echo "$line" | awk '{print $3}')
        AVAILABLE=$(echo "$line" | awk '{print $4}')
        AGE=$(echo "$line" | awk '{print $5}')
        
        if [ "$AVAILABLE" = "$READY" ] && [ "$READY" = "$UP_TO_DATE" ]; then
            log_success "Deployment $NAME: $READY ready"
        else
            log_warning "Deployment $NAME may have issues: Ready=$READY, UpToDate=$UP_TO_DATE, Available=$AVAILABLE"
        fi
    done
    
    return 0
}

# 5. Check for old ReplicaSets
cleanup_old_replicasets() {
    log_info "Checking for old ReplicaSets to clean up..."
    
    # Find old ReplicaSets (not owned by current deployments)
    OLD_RS=$(kubectl get rs -n "$NAMESPACE" --no-headers 2>/dev/null | awk '$2 == "0" {print $1}')
    
    if [ -n "$OLD_RS" ]; then
        log_warning "Found old ReplicaSets with 0 replicas:"
        echo "$OLD_RS"
        
        # Ask for confirmation before deleting (commented out for automation)
        # echo "$OLD_RS" | while read -r rs; do
        #     log_info "Deleting old ReplicaSet: $rs"
        #     kubectl delete rs "$rs" -n "$NAMESPACE" --ignore-not-found=true
        # done
        
        log_warning "Old ReplicaSets found - manual cleanup recommended"
        return 1
    else
        log_success "No old ReplicaSets found"
        return 0
    fi
}

# 6. Check for failed pods
cleanup_failed_pods() {
    log_info "Checking for failed/completed pods..."
    
    # Find failed or completed pods
    FAILED_PODS=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | grep -E "(Failed|Completed|CrashLoopBackOff|Error)" | wc -l)
    
    if [ "$FAILED_PODS" -gt 0 ]; then
        log_warning "Found $FAILED_PODS failed/completed pods:"
        kubectl get pods -n "$NAMESPACE" | grep -E "(Failed|Completed|CrashLoopBackOff|Error)"
        
        # Ask for confirmation before deleting (commented out for automation)
        # kubectl delete pods -n "$NAMESPACE" --field-selector=status.phase=Failed --ignore-not-found=true
        # kubectl delete pods -n "$NAMESPACE" --field-selector=status.phase=Succeeded --ignore-not-found=true
        
        log_warning "Failed pods found - manual cleanup recommended"
        return 1
    else
        log_success "No failed pods found"
        return 0
    fi
}

# 7. Check resource usage
check_resource_usage() {
    log_info "Checking resource usage..."
    
    # Check if metrics server is available
    if kubectl top pods -n "$NAMESPACE" >/dev/null 2>&1; then
        log_info "Resource usage (top pods):"
        kubectl top pods -n "$NAMESPACE" | head -10
        
        # Check for high CPU/memory usage
        HIGH_CPU=$(kubectl top pods -n "$NAMESPACE" --no-headers 2>/dev/null | awk '$3 > 80 {print $1 ": " $3 "% CPU"}')
        HIGH_MEM=$(kubectl top pods -n "$NAMESPACE" --no-headers 2>/dev/null | awk '$4 > 80 {print $1 ": " $4 "% MEM"}')
        
        if [ -n "$HIGH_CPU" ]; then
            log_warning "High CPU usage detected:"
            echo "$HIGH_CPU"
        fi
        
        if [ -n "$HIGH_MEM" ]; then
            log_warning "High memory usage detected:"
            echo "$HIGH_MEM"
        fi
        
        log_success "Resource monitoring completed"
        return 0
    else
        log_warning "Metrics server not available - cannot check resource usage"
        return 1
    fi
}

# 8. Validate services
validate_services() {
    log_info "Validating services..."
    
    SERVICES=$(kubectl get services -n "$NAMESPACE" --no-headers 2>/dev/null)
    
    if [ -z "$SERVICES" ]; then
        log_warning "No services found in namespace '$NAMESPACE'"
        return 1
    fi
    
    echo "$SERVICES" | while read -r line; do
        NAME=$(echo "$line" | awk '{print $1}')
        TYPE=$(echo "$line" | awk '{print $2}')
        CLUSTER_IP=$(echo "$line" | awk '{print $3}')
        EXTERNAL_IP=$(echo "$line" | awk '{print $4}')
        PORTS=$(echo "$line" | awk '{print $5}')
        
        if [ "$TYPE" = "LoadBalancer" ] && [ "$EXTERNAL_IP" = "<pending>" ]; then
            log_warning "Service $NAME has pending external IP"
        else
            log_success "Service $NAME: $TYPE, Ports: $PORTS"
        fi
    done
    
    return 0
}

# 9. Check secrets and configmaps
validate_secrets_configmaps() {
    log_info "Validating secrets and configmaps..."
    
    # Check secrets
    SECRETS=$(kubectl get secrets -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
    log_info "Found $SECRETS secrets"
    
    # Check configmaps
    CONFIGMAPS=$(kubectl get configmaps -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
    log_info "Found $CONFIGMAPS configmaps"
    
    # Validate critical secrets exist
    CRITICAL_SECRETS=("aster-dex-credentials" "vertex-ai-secret")
    for secret in "${CRITICAL_SECRETS[@]}"; do
        if ! kubectl get secret "$secret" -n "$NAMESPACE" >/dev/null 2>&1; then
            log_error "Critical secret missing: $secret"
            return 1
        fi
    done
    
    log_success "Secrets and configmaps validation completed"
    return 0
}

# 10. Check network policies
validate_network_policies() {
    log_info "Checking network policies..."
    
    NP_COUNT=$(kubectl get networkpolicies -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
    
    if [ "$NP_COUNT" -gt 0 ]; then
        log_success "Found $NP_COUNT network policies"
        return 0
    else
        log_warning "No network policies found - consider adding security policies"
        return 1
    fi
}

# 11. Generate health report
generate_health_report() {
    log_info "Generating system health report..."
    
    # Collect system metrics
    TOTAL_PODS=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
    RUNNING_PODS=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | grep Running | wc -l)
    DEPLOYMENTS=$(kubectl get deployments -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
    SERVICES=$(kubectl get services -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
    
    echo ""
    echo "📊 SYSTEM HEALTH REPORT"
    echo "======================="
    echo "🕐 Generated: $(date)"
    echo "📍 Namespace: $NAMESPACE"
    echo ""
    echo "🔢 POD STATUS:"
    echo "  Total Pods: $TOTAL_PODS"
    echo "  Running Pods: $RUNNING_PODS"
    echo "  Unhealthy Pods: $((TOTAL_PODS - RUNNING_PODS))"
    echo ""
    echo "🚀 DEPLOYMENTS: $DEPLOYMENTS"
    echo "🌐 SERVICES: $SERVICES"
    echo ""
    
    # Test critical services
    if kubectl get deployment sapphire-cloud-trader -n "$NAMESPACE" >/dev/null 2>&1; then
        echo "✅ Core trading system: DEPLOYED"
    else
        echo "❌ Core trading system: MISSING"
    fi
    
    # Test API connectivity (if service exists)
    if kubectl get service sapphire-cloud-trader-service -n "$NAMESPACE" >/dev/null 2>&1; then
        SERVICE_IP=$(kubectl get service sapphire-cloud-trader-service -n "$NAMESPACE" -o jsonpath='{.spec.clusterIP}')
        echo "✅ Trading API service: AVAILABLE (ClusterIP: $SERVICE_IP)"
        
        # Quick health check
        if kubectl exec deployment/sapphire-cloud-trader -n "$NAMESPACE" -- curl -f http://localhost:8080/healthz >/dev/null 2>&1; then
            echo "✅ Trading API health: HEALTHY"
        else
            echo "⚠️ Trading API health: UNRESPONSIVE"
        fi
    else
        echo "❌ Trading API service: MISSING"
    fi
}

# 12. Cleanup recommendations
provide_cleanup_recommendations() {
    log_info "Providing cleanup recommendations..."
    
    echo ""
    echo "🧹 CLEANUP RECOMMENDATIONS"
    echo "=========================="
    
    # Check for old resources
    OLD_RS=$(kubectl get rs -n "$NAMESPACE" --no-headers 2>/dev/null | awk '$2 == "0" {print $1}' | wc -l)
    FAILED_PODS=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | grep -E "(Failed|Completed|CrashLoopBackOff|Error)" | wc -l)
    
    if [ "$OLD_RS" -gt 0 ]; then
        echo "• Remove $OLD_RS old ReplicaSets: kubectl delete rs -n $NAMESPACE --field-selector=spec.replicas=0"
    fi
    
    if [ "$FAILED_PODS" -gt 0 ]; then
        echo "• Clean up $FAILED_PODS failed pods: kubectl delete pods -n $NAMESPACE --field-selector=status.phase=Failed"
    fi
    
    if [ "$OLD_RS" -eq 0 ] && [ "$FAILED_PODS" -eq 0 ]; then
        echo "• System is clean - no cleanup needed ✅"
    fi
    
    echo ""
    echo "🔄 MAINTENANCE SCHEDULE:"
    echo "• Run this script daily for monitoring"
    echo "• Clean up old resources weekly"
    echo "• Review resource usage monthly"
    echo "• Update deployments as needed"
}

# Main execution
main() {
    local errors=0
    
    echo "Starting Sapphire Trade system monitoring..."
    echo ""
    
    # Run all checks
    checks=(
        "check_cluster"
        "check_namespace" 
        "monitor_pods"
        "monitor_deployments"
        "cleanup_old_replicasets"
        "cleanup_failed_pods"
        "check_resource_usage"
        "validate_services"
        "validate_secrets_configmaps"
        "validate_network_policies"
    )
    
    for check in "${checks[@]}"; do
        if ! $check; then
            ((errors++))
        fi
        echo ""
    done
    
    # Generate reports
    generate_health_report
    provide_cleanup_recommendations
    
    # Summary
    echo ""
    echo "📋 MONITORING SUMMARY"
    echo "===================="
    if [ $errors -eq 0 ]; then
        log_success "All checks passed! System is healthy."
        return 0
    else
        log_error "$errors checks failed. Review output above."
        return 1
    fi
}

# Run main function
main "$@"
