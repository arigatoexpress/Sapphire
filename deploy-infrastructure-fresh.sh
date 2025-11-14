#!/bin/bash

# Infrastructure as Code Deployment Script
# Safe, declarative, and version-controlled deployments

set -e

NAMESPACE="trading-system-fresh"
FRAMEWORK_FILE="infrastructure-as-code-framework.yaml"

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

# Validate prerequisites
validate_prerequisites() {
    log_info "Validating prerequisites..."
    
    # Check kubectl access
    if ! kubectl cluster-info >/dev/null 2>&1; then
        log_error "Cannot access Kubernetes cluster"
        exit 1
    fi
    
    # Check manifest file exists
    if [ ! -f "$FRAMEWORK_FILE" ]; then
        log_error "Framework file $FRAMEWORK_FILE not found"
        exit 1
    fi
    
    # Validate YAML syntax
    if ! kubectl apply --dry-run=client -f "$FRAMEWORK_FILE" >/dev/null 2>&1; then
        log_error "Invalid YAML syntax in $FRAMEWORK_FILE"
        exit 1
    fi
    
    log_success "Prerequisites validated"
}

# Clean deployment environment
clean_environment() {
    log_info "Cleaning deployment environment..."
    
    # Remove old namespace if it exists (nuclear option for clean slate)
    if kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
        log_warning "Removing existing namespace $NAMESPACE for clean deployment"
        kubectl delete namespace "$NAMESPACE" --ignore-not-found=true --timeout=60s || true
        
        # Wait for namespace deletion
        log_info "Waiting for namespace cleanup..."
        for i in {1..30}; do
            if ! kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
                break
            fi
            sleep 2
        done
    fi
    
    log_success "Environment cleaned"
}

# Deploy infrastructure
deploy_infrastructure() {
    log_info "Deploying infrastructure from $FRAMEWORK_FILE..."
    
    # Apply the framework
    if kubectl apply -f "$FRAMEWORK_FILE"; then
        log_success "Infrastructure deployed successfully"
    else
        log_error "Infrastructure deployment failed"
        exit 1
    fi
}

# Validate deployment
validate_deployment() {
    log_info "Validating deployment..."
    
    # Wait for namespace to be active
    log_info "Waiting for namespace $NAMESPACE..."
    kubectl wait --for=condition=Ready namespace/"$NAMESPACE" --timeout=60s 2>/dev/null || true
    
    # Check core components
    local components=("redis" "trading-coordinator")
    for component in "${components[@]}"; do
        log_info "Checking $component..."
        
        # Wait for deployment to be ready
        if kubectl wait --for=condition=available --timeout=120s deployment/"$component" -n "$NAMESPACE" 2>/dev/null; then
            log_success "$component is ready"
        else
            log_error "$component failed to become ready"
            kubectl describe deployment "$component" -n "$NAMESPACE"
            exit 1
        fi
    done
    
    # Check services
    local services=("redis-service" "coordinator-service")
    for service in "${services[@]}"; do
        if kubectl get service "$service" -n "$NAMESPACE" >/dev/null 2>&1; then
            log_success "Service $service exists"
        else
            log_error "Service $service missing"
            exit 1
        fi
    done
    
    log_success "Deployment validation complete"
}

# Show deployment status
show_status() {
    echo ""
    log_info "DEPLOYMENT STATUS"
    echo "=================="
    kubectl get all -n "$NAMESPACE"
    echo ""
    kubectl get resourcequotas -n "$NAMESPACE"
    echo ""
    kubectl get configmaps -n "$NAMESPACE"
}

# Main execution
main() {
    echo "🚀 INFRASTRUCTURE AS CODE DEPLOYMENT"
    echo "===================================="
    echo "Namespace: $NAMESPACE"
    echo "Framework: $FRAMEWORK_FILE"
    echo ""
    
    validate_prerequisites
    clean_environment
    deploy_infrastructure
    validate_deployment
    show_status
    
    echo ""
    log_success "🎉 INFRASTRUCTURE DEPLOYMENT COMPLETE!"
    echo ""
    echo "✅ What's deployed:"
    echo "   • Namespace: $NAMESPACE"
    echo "   • Resource Quotas: Production-ready limits"
    echo "   • Redis: Data caching service"
    echo "   • Trading Coordinator: Core orchestration"
    echo "   • Configuration: System and resource tiers"
    echo ""
    echo "🚀 Ready for agent deployments!"
    echo "   Run: ./deploy-agents.sh"
}

# Run main function
main "$@"
