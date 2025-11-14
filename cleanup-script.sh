#!/bin/bash

# Sapphire Trade System Cleanup Script
# Automatically removes old/unused Kubernetes resources

set -e

NAMESPACE="trading"
DRY_RUN=false

# Parse command line arguments
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
            echo "Options:"
            echo "  --dry-run     Show what would be deleted without actually deleting"
            echo "  --namespace   Specify namespace (default: trading)"
            echo "  --help        Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo "🧹 SAPPHIRE TRADE SYSTEM CLEANUP"
echo "================================"
echo "🕐 $(date)"
echo "📍 Namespace: $NAMESPACE"
if [ "$DRY_RUN" = true ]; then
    echo "🔍 DRY RUN MODE - No changes will be made"
fi
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

# Execute command or show dry run
execute() {
    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}[DRY RUN]${NC} Would execute: $@"
    else
        log_info "Executing: $@"
        if "$@"; then
            log_success "Command completed successfully"
        else
            log_error "Command failed: $@"
            return 1
        fi
    fi
}

# 1. Clean up old ReplicaSets
cleanup_replicasets() {
    log_info "Cleaning up old ReplicaSets..."
    
    # Find ReplicaSets with 0 replicas that are not owned by current deployments
    OLD_RS=$(kubectl get rs -n "$NAMESPACE" --no-headers -o custom-columns=":metadata.name,:spec.replicas,:metadata.ownerReferences[0].name" 2>/dev/null | awk '$2 == "0" && $3 == "<none>" {print $1}')
    
    if [ -n "$OLD_RS" ]; then
        RS_COUNT=$(echo "$OLD_RS" | wc -l)
        log_warning "Found $RS_COUNT old ReplicaSets to clean up:"
        echo "$OLD_RS" | sed 's/^/  • /'
        
        echo "$OLD_RS" | while read -r rs; do
            execute kubectl delete rs "$rs" -n "$NAMESPACE" --ignore-not-found=true
        done
    else
        log_success "No old ReplicaSets found"
    fi
}

# 2. Clean up failed/completed pods
cleanup_failed_pods() {
    log_info "Cleaning up failed and completed pods..."
    
    # Find failed pods
    FAILED_PODS=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | awk '$4 != "Running" && $4 != "Pending" {print $1}')
    
    if [ -n "$FAILED_PODS" ]; then
        POD_COUNT=$(echo "$FAILED_PODS" | wc -l)
        log_warning "Found $POD_COUNT failed/completed pods to clean up:"
        echo "$FAILED_PODS" | sed 's/^/  • /'
        
        echo "$FAILED_PODS" | while read -r pod; do
            execute kubectl delete pod "$pod" -n "$NAMESPACE" --ignore-not-found=true --grace-period=0 --force
        done
    else
        log_success "No failed pods found"
    fi
}

# 3. Clean up old jobs
cleanup_jobs() {
    log_info "Cleaning up old completed jobs..."
    
    # Find completed jobs older than 7 days
    OLD_JOBS=$(kubectl get jobs -n "$NAMESPACE" --no-headers -o custom-columns=":metadata.name,:status.conditions[0].type,:metadata.creationTimestamp" 2>/dev/null | awk -v cutoff=$(date -d '7 days ago' +%s) '
    {
        split($3, date_parts, "T")
        split(date_parts[1], date_split, "-")
        split(date_parts[2], time_split, ":")
        job_time = mktime(date_split[1] " " date_split[2] " " date_split[3] " " time_split[1] " " time_split[2] " " time_split[3])
        if ($2 == "Complete" && job_time < cutoff) print $1
    }')
    
    if [ -n "$OLD_JOBS" ]; then
        JOB_COUNT=$(echo "$OLD_JOBS" | wc -l)
        log_info "Found $JOB_COUNT old completed jobs (>7 days) to clean up:"
        echo "$OLD_JOBS" | sed 's/^/  • /'
        
        echo "$OLD_JOBS" | while read -r job; do
            execute kubectl delete job "$job" -n "$NAMESPACE" --ignore-not-found=true
        done
    else
        log_success "No old jobs to clean up"
    fi
}

# 4. Clean up unused configmaps
cleanup_configmaps() {
    log_info "Checking for unused ConfigMaps..."
    
    # This is more complex - would need to check which ConfigMaps are actually used
    # For now, just report what exists
    CONFIGMAPS=$(kubectl get configmaps -n "$NAMESPACE" --no-headers -o custom-columns=":metadata.name" 2>/dev/null)
    
    if [ -n "$CONFIGMAPS" ]; then
        CM_COUNT=$(echo "$CONFIGMAPS" | wc -l)
        log_info "Found $CM_COUNT ConfigMaps in namespace:"
        echo "$CONFIGMAPS" | sed 's/^/  • /'
        log_info "Manual review recommended for ConfigMap cleanup"
    else
        log_success "No ConfigMaps found"
    fi
}

# 5. Clean up dangling services
cleanup_services() {
    log_info "Checking for services without endpoints..."
    
    # Find services without corresponding pods
    SERVICES=$(kubectl get services -n "$NAMESPACE" --no-headers -o custom-columns=":metadata.name,:spec.selector" 2>/dev/null | grep -v "<none>")
    
    if [ -n "$SERVICES" ]; then
        echo "$SERVICES" | while read -r line; do
            SERVICE_NAME=$(echo "$line" | awk '{print $1}')
            SELECTOR=$(echo "$line" | awk '{print $2}')
            
            # Check if any pods match the selector
            POD_COUNT=$(kubectl get pods -n "$NAMESPACE" -l "$SELECTOR" --no-headers 2>/dev/null | wc -l)
            
            if [ "$POD_COUNT" -eq 0 ]; then
                log_warning "Service '$SERVICE_NAME' has no matching pods (selector: $SELECTOR)"
                # Uncomment to actually delete
                # execute kubectl delete service "$SERVICE_NAME" -n "$NAMESPACE" --ignore-not-found=true
            fi
        done
    fi
    
    log_success "Service check completed"
}

# 6. Clean up old PVCs
cleanup_pvcs() {
    log_info "Checking for unused PersistentVolumeClaims..."
    
    # Find PVCs not bound to pods
    UNUSED_PVCS=$(kubectl get pvc -n "$NAMESPACE" --no-headers 2>/dev/null | awk '$3 != "Bound" {print $1}')
    
    if [ -n "$UNUSED_PVCS" ]; then
        PVC_COUNT=$(echo "$UNUSED_PVCS" | wc -l)
        log_warning "Found $PVC_COUNT unused PVCs:"
        echo "$UNUSED_PVCS" | sed 's/^/  • /'
        log_warning "PVC cleanup requires manual confirmation"
    else
        log_success "No unused PVCs found"
    fi
}

# 7. Validate cleanup
validate_cleanup() {
    log_info "Validating cleanup results..."
    
    # Check remaining unhealthy resources
    UNHEALTHY_PODS=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | grep -v Running | grep -v Pending | wc -l)
    OLD_RS=$(kubectl get rs -n "$NAMESPACE" --no-headers 2>/dev/null | awk '$2 == "0" {print $1}' | wc -l)
    
    if [ "$UNHEALTHY_PODS" -gt 0 ]; then
        log_warning "Still have $UNHEALTHY_PODS unhealthy pods after cleanup"
    else
        log_success "All pods are healthy"
    fi
    
    if [ "$OLD_RS" -gt 0 ]; then
        log_warning "Still have $OLD_RS old ReplicaSets after cleanup"
    else
        log_success "No old ReplicaSets remaining"
    fi
}

# 8. Generate cleanup report
generate_cleanup_report() {
    echo ""
    echo "📊 CLEANUP REPORT"
    echo "================="
    echo "🕐 Completed: $(date)"
    echo "📍 Namespace: $NAMESPACE"
    if [ "$DRY_RUN" = true ]; then
        echo "🔍 Mode: DRY RUN (no changes made)"
    else
        echo "🔄 Mode: LIVE CLEANUP"
    fi
    echo ""
    
    # Show current resource counts
    PODS=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
    DEPLOYMENTS=$(kubectl get deployments -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
    SERVICES=$(kubectl get services -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
    RS=$(kubectl get rs -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
    
    echo "📊 CURRENT RESOURCES:"
    echo "  Pods: $PODS"
    echo "  Deployments: $DEPLOYMENTS"
    echo "  Services: $SERVICES"
    echo "  ReplicaSets: $RS"
    echo ""
    
    if [ "$DRY_RUN" = true ]; then
        echo "💡 To perform actual cleanup, run:"
        echo "   $0 --namespace=$NAMESPACE"
    fi
}

# Main execution
main() {
    local errors=0
    
    echo "Starting automated cleanup process..."
    echo ""
    
    # Safety check
    if [ "$NAMESPACE" = "default" ] || [ "$NAMESPACE" = "kube-system" ]; then
        log_error "Refusing to clean up system namespace: $NAMESPACE"
        exit 1
    fi
    
    # Run cleanup tasks
    cleanup_tasks=(
        "cleanup_replicasets"
        "cleanup_failed_pods"
        "cleanup_jobs"
        "cleanup_configmaps"
        "cleanup_services"
        "cleanup_pvcs"
        "validate_cleanup"
    )
    
    for task in "${cleanup_tasks[@]}"; do
        echo ""
        if ! $task; then
            ((errors++))
        fi
    done
    
    # Generate report
    generate_cleanup_report
    
    # Summary
    echo ""
    echo "📋 CLEANUP SUMMARY"
    echo "=================="
    if [ $errors -eq 0 ]; then
        if [ "$DRY_RUN" = true ]; then
            log_success "Dry run completed successfully - review output above"
        else
            log_success "Cleanup completed successfully!"
        fi
        return 0
    else
        log_error "$errors cleanup tasks had issues"
        return 1
    fi
}

# Run main function
main "$@"
