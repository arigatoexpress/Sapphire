#!/bin/bash

# Enhanced kubectl Build Progress Monitor
# Real-time monitoring of Kubernetes deployments with progress tracking

set -e

# Configuration
NAMESPACE="${NAMESPACE:-trading}"
MONITOR_INTERVAL="${MONITOR_INTERVAL:-5}"
MAX_WAIT_TIME="${MAX_WAIT_TIME:-1800}"  # 30 minutes
SHOW_RESOURCES="${SHOW_RESOURCES:-true}"
SHOW_LOGS="${SHOW_LOGS:-false}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# Progress bar function
progress_bar() {
    local current=$1
    local total=$2
    local width=50
    local percentage=$((current * 100 / total))
    local completed=$((current * width / total))

    printf "\r["
    for ((i=1; i<=completed; i++)); do printf "="; done
    for ((i=completed+1; i<=width; i++)); do printf " "; done
    printf "] %d%% (%d/%d)" "$percentage" "$current" "$total"
}

# Get deployment status
get_deployment_status() {
    local deployment=$1
    kubectl get deployment "$deployment" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}/{.spec.replicas}' 2>/dev/null || echo "0/0"
}

# Get pod status summary
get_pod_status() {
    kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | awk '
    BEGIN { total=0; pending=0; running=0; failed=0; succeeded=0 }
    {
        total++
        if ($3 == "Pending") pending++
        else if ($3 == "Running") running++
        else if ($3 == "Failed") failed++
        else if ($3 == "Succeeded") succeeded++
    }
    END {
        print total "," pending "," running "," failed "," succeeded
    }
    ' || echo "0,0,0,0,0"
}

# Get resource usage
get_resource_usage() {
    if [ "$SHOW_RESOURCES" = "true" ]; then
        echo ""
        echo -e "${CYAN}Resource Usage:${NC}"
        kubectl top pods -n "$NAMESPACE" --no-headers 2>/dev/null | head -10 | while read -r line; do
            echo "  $line"
        done || echo "  Resource metrics not available (metrics-server may not be installed)"
    fi
}

# Get deployment rollout status
get_rollout_status() {
    local deployment=$1
    kubectl rollout status "deployment/$deployment" -n "$NAMESPACE" --timeout=1s 2>/dev/null | grep -E "(successfully|failed|timed out)" || echo "in progress"
}

# Monitor single deployment
monitor_deployment() {
    local deployment=$1
    local start_time=$(date +%s)
    local last_status=""

    echo -e "${BLUE}Monitoring deployment: ${WHITE}$deployment${NC}"
    echo "Namespace: $NAMESPACE"
    echo "Started at: $(date)"
    echo ""

    while true; do
        current_time=$(date +%s)
        elapsed=$((current_time - start_time))

        if [ $elapsed -gt $MAX_WAIT_TIME ]; then
            echo -e "\n${RED}⏰ Timeout: Deployment monitoring exceeded $MAX_WAIT_TIME seconds${NC}"
            return 1
        fi

        # Get current status
        status=$(get_deployment_status "$deployment")
        ready=$(echo "$status" | cut -d'/' -f1)
        total=$(echo "$status" | cut -d'/' -f2)

        # Show progress if we have replica info
        if [ "$total" != "0" ] && [ "$ready" != "0/0" ]; then
            progress_bar "$ready" "$total"
            echo -ne " - ${deployment}"
        fi

        # Check if deployment is complete
        rollout_status=$(get_rollout_status "$deployment")
        if echo "$rollout_status" | grep -q "successfully"; then
            echo -e "\n${GREEN}✅ Deployment $deployment completed successfully!${NC}"
            return 0
        elif echo "$rollout_status" | grep -q "failed\|timed out"; then
            echo -e "\n${RED}❌ Deployment $deployment failed: $rollout_status${NC}"
            return 1
        fi

        # Show pod details if status changed
        if [ "$status" != "$last_status" ]; then
            echo ""
            echo -e "${YELLOW}Current Status:${NC}"
            echo "  Deployment: $status ready"
            last_status="$status"
        fi

        sleep "$MONITOR_INTERVAL"
    done
}

# Monitor all deployments in namespace
monitor_all_deployments() {
    local start_time=$(date +%s)
    local completed_deployments=()
    local failed_deployments=()

    echo -e "${BLUE}🚀 Monitoring All Deployments in Namespace: ${WHITE}$NAMESPACE${NC}"
    echo "Started at: $(date)"
    echo "Monitor interval: ${MONITOR_INTERVAL}s"
    echo "Max wait time: ${MAX_WAIT_TIME}s"
    echo ""

    # Get initial deployment list
    deployments=$(kubectl get deployments -n "$NAMESPACE" --no-headers -o custom-columns=":metadata.name" 2>/dev/null)
    if [ -z "$deployments" ]; then
        echo -e "${RED}❌ No deployments found in namespace $NAMESPACE${NC}"
        return 1
    fi

    deployment_array=($deployments)
    total_deployments=${#deployment_array[@]}

    echo -e "${CYAN}Found $total_deployments deployments:${NC}"
    printf '%s\n' "${deployment_array[@]}" | sed 's/^/  • /'
    echo ""

    while true; do
        current_time=$(date +%s)
        elapsed=$((current_time - start_time))

        if [ $elapsed -gt $MAX_WAIT_TIME ]; then
            echo -e "\n${RED}⏰ Timeout: Monitoring exceeded $MAX_WAIT_TIME seconds${NC}"
            break
        fi

        # Get overall pod status
        pod_status=$(get_pod_status)
        IFS=',' read -r total_pods pending running failed succeeded <<< "$pod_status"

        echo -e "${WHITE}Time elapsed: ${elapsed}s${NC}"
        echo -e "${CYAN}Pod Status: ${GREEN}${running}/${WHITE}${total_pods} running${NC} (${pending} pending, ${failed} failed, ${succeeded} succeeded)"

        # Check each deployment
        all_complete=true
        for deployment in "${deployment_array[@]}"; do
            # Skip if already completed or failed
            if [[ " ${completed_deployments[*]} " =~ " $deployment " ]] || [[ " ${failed_deployments[*]} " =~ " $deployment " ]]; then
                continue
            fi

            status=$(get_deployment_status "$deployment")
            ready=$(echo "$status" | cut -d'/' -f1)
            total=$(echo "$status" | cut -d'/' -f2)

            if [ "$ready" = "$total" ] && [ "$total" != "0" ]; then
                echo -e "${GREEN}✅ $deployment: $status (COMPLETE)${NC}"
                completed_deployments+=("$deployment")
            elif [ "$status" = "0/0" ]; then
                echo -e "${YELLOW}⏳ $deployment: Not found or scaling to 0${NC}"
            else
                echo -e "${YELLOW}⏳ $deployment: $status${NC}"
                all_complete=false
            fi
        done

        # Show resource usage
        get_resource_usage

        # Check if all deployments are complete
        if [ ${#completed_deployments[@]} -eq $total_deployments ]; then
            echo ""
            echo -e "${GREEN}🎉 ALL DEPLOYMENTS COMPLETED SUCCESSFULLY!${NC}"
            echo ""
            echo -e "${CYAN}Completed deployments:${NC}"
            printf '%s\n' "${completed_deployments[@]}" | sed 's/^/  ✅ /'
            echo ""
            echo -e "${WHITE}Total time: ${elapsed} seconds${NC}"
            return 0
        fi

        # Check for failures
        if [ "$failed" -gt 0 ]; then
            echo -e "\n${RED}⚠️  Detected $failed failed pods. Checking details...${NC}"
            kubectl get pods -n "$NAMESPACE" | grep -E "(Failed|Error|CrashLoopBackOff)"
        fi

        echo ""
        echo -e "${BLUE}Waiting ${MONITOR_INTERVAL}s before next check...${NC}"
        echo "Press Ctrl+C to stop monitoring"
        echo -e "${MAGENTA}$(printf '%.0s─' {1..60})${NC}"

        sleep "$MONITOR_INTERVAL"
        # Clear screen for next iteration
        tput cuu $(tput lines) 2>/dev/null || true
        tput ed 2>/dev/null || true
    done

    # Show final status
    echo ""
    echo -e "${YELLOW}📊 FINAL STATUS SUMMARY${NC}"
    echo "=========================="

    if [ ${#completed_deployments[@]} -gt 0 ]; then
        echo -e "${GREEN}✅ Completed: ${#completed_deployments[@]} deployments${NC}"
        printf '%s\n' "${completed_deployments[@]}" | sed 's/^/  • /'
    fi

    if [ ${#failed_deployments[@]} -gt 0 ]; then
        echo -e "${RED}❌ Failed: ${#failed_deployments[@]} deployments${NC}"
        printf '%s\n' "${failed_deployments[@]}" | sed 's/^/  • /'
    fi

    remaining=$((total_deployments - ${#completed_deployments[@]} - ${#failed_deployments[@]}))
    if [ $remaining -gt 0 ]; then
        echo -e "${YELLOW}⏳ Still in progress: $remaining deployments${NC}"
    fi

    return 0
}

# Show usage
show_usage() {
    echo "kubectl Build Progress Monitor"
    echo "=============================="
    echo ""
    echo "Usage:"
    echo "  $0 [options] [deployment-name]"
    echo ""
    echo "Options:"
    echo "  -n, --namespace NAMESPACE    Kubernetes namespace (default: trading)"
    echo "  -i, --interval SECONDS       Monitor interval in seconds (default: 5)"
    echo "  -t, --timeout SECONDS        Maximum wait time in seconds (default: 1800)"
    echo "  -r, --no-resources           Don't show resource usage"
    echo "  -l, --logs                   Show pod logs for debugging"
    echo "  -h, --help                   Show this help"
    echo ""
    echo "Examples:"
    echo "  $0                          Monitor all deployments in 'trading' namespace"
    echo "  $0 cloud-trader            Monitor specific deployment"
    echo "  $0 -n production -i 10     Monitor with 10s interval in production namespace"
    echo "  $0 --no-resources          Monitor without resource usage display"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -i|--interval)
            MONITOR_INTERVAL="$2"
            shift 2
            ;;
        -t|--timeout)
            MAX_WAIT_TIME="$2"
            shift 2
            ;;
        -r|--no-resources)
            SHOW_RESOURCES=false
            shift
            ;;
        -l|--logs)
            SHOW_LOGS=true
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            DEPLOYMENT_NAME="$1"
            shift
            ;;
    esac
done

# Validate kubectl access
if ! kubectl cluster-info >/dev/null 2>&1; then
    echo -e "${RED}❌ Cannot access Kubernetes cluster. Please check your kubeconfig.${NC}"
    exit 1
fi

# Check namespace exists
if ! kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
    echo -e "${RED}❌ Namespace '$NAMESPACE' does not exist.${NC}"
    exit 1
fi

# Main execution
if [ -n "$DEPLOYMENT_NAME" ]; then
    # Monitor specific deployment
    if ! kubectl get deployment "$DEPLOYMENT_NAME" -n "$NAMESPACE" >/dev/null 2>&1; then
        echo -e "${RED}❌ Deployment '$DEPLOYMENT_NAME' not found in namespace '$NAMESPACE'.${NC}"
        exit 1
    fi
    monitor_deployment "$DEPLOYMENT_NAME"
else
    # Monitor all deployments
    monitor_all_deployments
fi
