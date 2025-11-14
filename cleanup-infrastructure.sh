#!/bin/bash

# Infrastructure Cleanup Script
# Safe removal of infrastructure components with validation

set -e

NAMESPACE="trading-system"
DRY_RUN=false

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

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --namespace=*)
            NAMESPACE="${1#*=}"
            shift
            ;;
        --help)
            echo "Usage: $0 [--dry-run] [--namespace=NAMESPACE]"
            echo ""
            echo "Safely clean up infrastructure components"
            echo ""
            echo "Options:"
            echo "  --dry-run    Show what would be deleted"
            echo "  --namespace  Target namespace (default: trading-system)"
            echo "  --help       Show this help"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate namespace exists
validate_namespace() {
    if ! kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
        log_error "Namespace $NAMESPACE does not exist"
        exit 1
    fi
}

# Execute or show command
execute() {
    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}[DRY RUN]${NC} Would execute: $@"
    else
        log_info "Executing: $@"
        if "$@"; then
            log_success "Command completed"
        else
            log_error "Command failed: $@"
            exit 1
        fi
    fi
}

# Clean up agents
cleanup_agents() {
    log_info "Cleaning up trading agents..."
    
    # Get all agent deployments
    local agents
    agents=$(kubectl get deployments -n "$NAMESPACE" -l component=trading-agent -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")
    
    if [ -n "$agents" ]; then
        for agent in $agents; do
            log_info "Removing agent: $agent"
            execute kubectl delete deployment "$agent" -n "$NAMESPACE" --ignore-not-found=true
            execute kubectl delete service "${agent}-service" -n "$NAMESPACE" --ignore-not-found=true
            execute kubectl delete configmap "${agent}-config" -n "$NAMESPACE" --ignore-not-found=true
        done
    else
        log_info "No trading agents found"
    fi
}

# Clean up core infrastructure
cleanup_infrastructure() {
    log_info "Cleaning up core infrastructure..."
    
    # Remove deployments in order
    local components=("trading-coordinator" "redis")
    for component in "${components[@]}"; do
        log_info "Removing $component"
        execute kubectl delete deployment "$component" -n "$NAMESPACE" --ignore-not-found=true
        execute kubectl delete service "${component}-service" -n "$NAMESPACE" --ignore-not-found=true
    done
    
    # Remove HPAs
    execute kubectl delete hpa --all -n "$NAMESPACE" --ignore-not-found=true
    
    # Remove ConfigMaps (keep secrets for security)
    execute kubectl delete configmap system-config agent-resource-tiers -n "$NAMESPACE" --ignore-not-found=true
    
    # Remove ResourceQuota
    execute kubectl delete resourcequota production-trading-quota -n "$NAMESPACE" --ignore-not-found=true
}

# Clean up namespace
cleanup_namespace() {
    if [ "$DRY_RUN" = true ]; then
        log_warning "Would delete namespace $NAMESPACE"
        return
    fi
    
    log_warning "Deleting namespace $NAMESPACE..."
    log_warning "This will remove ALL resources in the namespace!"
    
    # Final confirmation for namespace deletion
    echo "Type 'DELETE' to confirm namespace deletion:"
    read -r confirmation
    
    if [ "$confirmation" != "DELETE" ]; then
        log_error "Namespace deletion cancelled"
        exit 1
    fi
    
    execute kubectl delete namespace "$NAMESPACE" --ignore-not-found=true --timeout=120s
}

# Validate cleanup
validate_cleanup() {
    if [ "$DRY_RUN" = true ]; then
        return
    fi
    
    log_info "Validating cleanup..."
    
    # Check if namespace still exists
    if kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
        # Check if resources are gone
        local remaining
        remaining=$(kubectl get all -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
        
        if [ "$remaining" -gt 0 ]; then
            log_warning "Some resources still remain in namespace $NAMESPACE"
            kubectl get all -n "$NAMESPACE"
        else
            log_success "Namespace $NAMESPACE is clean"
        fi
    else
        log_success "Namespace $NAMESPACE completely removed"
    fi
}

# Show cleanup summary
show_summary() {
    echo ""
    if [ "$DRY_RUN" = true ]; then
        log_info "DRY RUN COMPLETE - No changes made"
        echo ""
        echo "To perform actual cleanup, run:"
        echo "  $0"
        echo ""
        echo "To clean up everything including namespace, run:"
        echo "  $0 --namespace=$NAMESPACE (then manually delete namespace)"
    else
        log_success "CLEANUP COMPLETE"
        echo ""
        echo "✅ Removed:"
        echo "   • All trading agent deployments"
        echo "   • Core infrastructure components"
        echo "   • Configuration maps"
        echo "   • Auto-scaling policies"
        echo ""
        echo "🔒 Preserved:"
        echo "   • Secrets (aster-dex-credentials, telegram-secret)"
        echo "   • Namespace (for potential reuse)"
        echo ""
        echo "🚀 Ready for fresh deployment:"
        echo "   ./deploy-infrastructure.sh"
        echo "   ./deploy-agents.sh"
    fi
}

# Main execution
main() {
    echo "🧹 INFRASTRUCTURE CLEANUP"
    echo "========================="
    echo "Namespace: $NAMESPACE"
    if [ "$DRY_RUN" = true ]; then
        echo "Mode: DRY RUN"
    else
        echo "Mode: LIVE CLEANUP"
    fi
    echo ""
    
    validate_namespace
    cleanup_agents
    cleanup_infrastructure
    validate_cleanup
    show_summary
}

# Run main function
main "$@"
