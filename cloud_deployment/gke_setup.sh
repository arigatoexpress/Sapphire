#!/bin/bash
set -e

# --- Configuration ---
PROJECT_ID="sapphireinfinite"
REGION="us-central1"
ZONE="us-central1-a"
CLUSTER_NAME="hft-trading-cluster"
NODE_POOL_NAME="gpu-node-pool"
MACHINE_TYPE="g2-standard-4"
GPU_TYPE="nvidia-l4"
GPU_COUNT=1

# --- Color Definitions ---
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# --- Functions ---
print_step() {
    echo -e "${BLUE}==> $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# --- GKE Cluster Setup ---
setup_gke() {
    print_step "Starting GKE Cluster Setup for HFT Aster Trader"

    # Configure gcloud
    print_step "Configuring gcloud for project $PROJECT_ID in $REGION"
    gcloud config set project $PROJECT_ID
    gcloud config set compute/region $REGION
    gcloud config set compute/zone $ZONE
    print_success "gcloud configured"

    # Create GKE cluster
    print_step "Creating GKE cluster '$CLUSTER_NAME' (this may take several minutes)..."
    if ! gcloud container clusters describe ${CLUSTER_NAME} --zone=${ZONE} &> /dev/null; then
        gcloud container clusters create ${CLUSTER_NAME} \
            --zone=${ZONE} \
            --num-nodes=1 \
            --machine-type="e2-medium" \
            --workload-pool=${PROJECT_ID}.svc.id.goog \
            --enable-ip-alias \
            --cluster-ipv4-cidr="10.0.0.0/16" \
            --services-ipv4-cidr="10.1.0.0/16"
        print_success "GKE cluster '$CLUSTER_NAME' created"
    else
        print_success "GKE cluster '$CLUSTER_NAME' already exists"
    fi

    # Connect kubectl
    print_step "Connecting kubectl to the cluster"
    gcloud container clusters get-credentials ${CLUSTER_NAME} --zone=${ZONE}
    print_success "kubectl configured"

    # Create GPU node pool
    print_step "Creating GPU node pool '$NODE_POOL_NAME' with $GPU_COUNT $GPU_TYPE GPU(s)..."
    if ! gcloud container node-pools describe ${NODE_POOL_NAME} --cluster=${CLUSTER_NAME} --zone=${ZONE} &> /dev/null; then
        gcloud container node-pools create ${NODE_POOL_NAME} \
            --cluster=${CLUSTER_NAME} \
            --zone=${ZONE} \
            --machine-type=${MACHINE_TYPE} \
            --accelerator="type=${GPU_TYPE},count=${GPU_COUNT}" \
            --num-nodes=1 \
            --enable-autoscaling \
            --min-nodes=0 \
            --max-nodes=3
        print_success "GPU node pool '$NODE_POOL_NAME' created"
    else
        print_success "GPU node pool '$NODE_POOL_NAME' already exists"
    fi

    print_success "GKE infrastructure setup complete"
}

main() {
    setup_gke
}

main "$@"
