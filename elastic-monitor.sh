#!/bin/bash

# Elastic Infrastructure Monitoring Script
# Monitors resource usage, costs, and scaling decisions

NAMESPACE="trading"
COST_OPTIMIZATION_ENABLED=true

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

# Get cluster resource usage
get_cluster_usage() {
    echo ""
    log_info "CLUSTER RESOURCE USAGE"
    echo "======================="
    
    # Get node capacity and allocation
    kubectl get nodes --no-headers | while read node; do
        NODE_NAME=$(echo $node | awk '{print $1}')
        echo "Node: $NODE_NAME"
        kubectl describe node "$NODE_NAME" | grep -A 10 "Allocated resources" | tail -11
        echo ""
    done
}

# Analyze agent performance vs resource usage
analyze_agent_efficiency() {
    echo ""
    log_info "AGENT EFFICIENCY ANALYSIS"
    echo "=========================="
    
    # Get all trading pods with resource usage
    kubectl get pods -n "$NAMESPACE" -o custom-columns="NAME:.metadata.name,CPU:.status.containerStatuses[0].resources.requests.cpu,MEM:.status.containerStatuses[0].resources.requests.memory,STATUS:.status.phase" | grep -v "NAME" | while read line; do
        POD_NAME=$(echo $line | awk '{print $1}')
        CPU_REQ=$(echo $line | awk '{print $2}')
        MEM_REQ=$(echo $line | awk '{print $3}')
        STATUS=$(echo $line | awk '{print $4}')
        
        if [[ $POD_NAME == *"trading"* ]]; then
            echo "Pod: $POD_NAME"
            echo "  CPU Request: $CPU_REQ"
            echo "  Memory Request: $MEM_REQ"
            echo "  Status: $STATUS"
            
            # Get actual usage if metrics available
            CPU_USAGE=$(kubectl top pods -n "$NAMESPACE" "$POD_NAME" 2>/dev/null | tail -1 | awk '{print $2}' || echo "N/A")
            MEM_USAGE=$(kubectl top pods -n "$NAMESPACE" "$POD_NAME" 2>/dev/null | tail -1 | awk '{print $3}' || echo "N/A")
            
            echo "  CPU Usage: $CPU_USAGE"
            echo "  Memory Usage: $MEM_USAGE"
            echo ""
        fi
    done
}

# Check HPA status
check_autoscaling() {
    echo ""
    log_info "AUTOSCALING STATUS"
    echo "==================="
    
    kubectl get hpa -n "$NAMESPACE" -o custom-columns="NAME:.metadata.name,REFERENCE:.spec.scaleTargetRef.name,REPLICAS:.status.currentReplicas/:.status.desiredReplicas,AGE:.metadata.creationTimestamp" | while read line; do
        HPA_NAME=$(echo $line | awk '{print $1}')
        TARGET=$(echo $line | awk '{print $2}')
        REPLICAS=$(echo $line | awk '{print $3}')
        AGE=$(echo $line | awk '{print $4}')
        
        echo "HPA: $HPA_NAME"
        echo "  Target: $TARGET"
        echo "  Replicas: $REPLICAS"
        echo "  Age: $AGE"
        echo ""
    done
}

# Cost optimization recommendations
cost_recommendations() {
    if [ "$COST_OPTIMIZATION_ENABLED" = true ]; then
        echo ""
        log_info "COST OPTIMIZATION RECOMMENDATIONS"
        echo "==================================="
        
        # Check for over-provisioned resources
        kubectl get pods -n "$NAMESPACE" -o custom-columns="NAME:.metadata.name,CPU_REQ:.spec.containers[0].resources.requests.cpu,MEM_REQ:.spec.containers[0].resources.requests.memory" | while read line; do
            POD_NAME=$(echo $line | awk '{print $1}')
            CPU_REQ=$(echo $line | awk '{print $2}')
            MEM_REQ=$(echo $line | awk '{print $3}')
            
            if [[ $POD_NAME == *"trading"* ]]; then
                # Check if pod is using less than 50% of requested resources
                CPU_USAGE=$(kubectl top pods -n "$NAMESPACE" "$POD_NAME" 2>/dev/null | tail -1 | awk '{print $2}' | sed 's/m//' || echo "0")
                MEM_USAGE=$(kubectl top pods -n "$NAMESPACE" "$POD_NAME" 2>/dev/null | tail -1 | awk '{print $3}' | sed 's/Mi//' || echo "0")
                
                CPU_REQ_NUM=$(echo $CPU_REQ | sed 's/m//' || echo "0")
                MEM_REQ_NUM=$(echo $MEM_REQ | sed 's/Mi//' || echo "0")
                
                if [ "$CPU_USAGE" -lt $((CPU_REQ_NUM / 2)) ] 2>/dev/null && [ "$CPU_USAGE" != "0" ]; then
                    log_warning "Pod $POD_NAME is over-provisioned CPU (${CPU_USAGE}m used vs ${CPU_REQ_NUM}m requested)"
                fi
                
                if [ "$MEM_USAGE" -lt $((MEM_REQ_NUM / 2)) ] 2>/dev/null && [ "$MEM_USAGE" != "0" ]; then
                    log_warning "Pod $POD_NAME is over-provisioned Memory (${MEM_USAGE}Mi used vs ${MEM_REQ_NUM}Mi requested)"
                fi
            fi
        done
        
        # Check cluster utilization
        TOTAL_CPU=$(kubectl get nodes --no-headers -o custom-columns="CPU:.status.capacity.cpu" | awk '{sum += $1} END {print sum}')
        USED_CPU=$(kubectl get nodes --no-headers -o custom-columns="CPU:.status.allocatable.cpu" | awk '{sum += $1} END {print sum}' || echo "0")
        
        if [ "$USED_CPU" -gt 0 ] 2>/dev/null; then
            CPU_UTIL=$(( (TOTAL_CPU - USED_CPU) * 100 / TOTAL_CPU ))
            if [ "$CPU_UTIL" -gt 70 ]; then
                log_warning "Cluster CPU utilization is low (${CPU_UTIL}%), consider scaling down nodes"
            fi
        fi
    fi
}

# Main execution
main() {
    echo "🔍 ELASTIC INFRASTRUCTURE MONITORING"
    echo "===================================="
    echo "Timestamp: $(date)"
    echo ""
    
    get_cluster_usage
    analyze_agent_efficiency
    check_autoscaling
    cost_recommendations
    
    echo ""
    log_success "Monitoring complete. Run this script regularly to optimize resource usage."
}

# Run main function
main "$@"
