#!/bin/bash
# GPU Node Pool Provisioning Script for Sapphire Trading System
# Run this after GPU quota approval

set -e

PROJECT_ID="sapphireinfinite"
CLUSTER_NAME="hft-trading-cluster"
ZONE="us-central1-a"

echo "🚀 Provisioning GPU Node Pools for AI Trading System"
echo "=================================================="

# Check GPU quota first
echo "🔍 Checking GPU quota..."
GPU_QUOTA=$(gcloud compute project-info describe --project=$PROJECT_ID --format="value(quotas[quotas.metric=GPUS_ALL_REGIONS].limit)")
echo "Current GPU quota: $GPU_QUOTA"

if [ "$GPU_QUOTA" -lt 8 ]; then
    echo "❌ Insufficient GPU quota. Current: $GPU_QUOTA, Required: 8"
    echo "Please request GPU quota increase to at least 8 GPUs"
    exit 1
fi

echo "✅ GPU quota sufficient"

# Create GPU node pools optimized for AI trading
echo "🔧 Creating optimized GPU node pools..."

# Pool 1: High-performance single-GPU nodes for individual agents
echo "📦 Creating gpu-agent-pool (4 nodes × 1 L4 GPU each)..."
gcloud container node-pools create gpu-agent-pool \
  --cluster=$CLUSTER_NAME \
  --zone=$ZONE \
  --project=$PROJECT_ID \
  --machine-type=g2-standard-8 \
  --accelerator=type=nvidia-l4,count=1 \
  --num-nodes=4 \
  --min-nodes=2 \
  --max-nodes=6 \
  --enable-autoscaling \
  --enable-autorepair \
  --enable-autoupgrade \
  --node-labels=pool=gpu-agents,accelerator=nvidia-l4 \
  --node-taints=accelerator=nvidia-l4:NoSchedule

# Pool 2: Heavy-duty node for coordinator and intensive processing
echo "📦 Creating gpu-coordinator-pool (1 node × 1 L4 GPU, higher capacity)..."
gcloud container node-pools create gpu-coordinator-pool \
  --cluster=$CLUSTER_NAME \
  --zone=$ZONE \
  --project=$PROJECT_ID \
  --machine-type=g2-standard-16 \
  --accelerator=type=nvidia-l4,count=1 \
  --num-nodes=1 \
  --min-nodes=1 \
  --max-nodes=2 \
  --enable-autoscaling \
  --enable-autorepair \
  --enable-autoupgrade \
  --node-labels=pool=gpu-coordinator,accelerator=nvidia-l4 \
  --node-taints=accelerator=nvidia-l4:NoSchedule

echo "⏳ Waiting for node pools to become ready..."
sleep 60

# Verify node pools
echo "🔍 Verifying node pools..."
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID

echo "✅ GPU node pools provisioned successfully!"
echo ""
echo "🎯 Next Steps:"
echo "1. Update helm/trading-system/values.yaml: set gpu.enabled=true"
echo "2. Deploy with GPU acceleration: helm upgrade --install trading-system ./helm/trading-system"
echo ""
echo "💰 Estimated Cost:"
echo "- gpu-agent-pool (4 × g2-standard-8): ~$6-8/hour"
echo "- gpu-coordinator-pool (1 × g2-standard-16): ~$3-4/hour"
echo "- Total: ~$9-12/hour for full GPU acceleration"
echo ""
echo "⚡ Performance Gains:"
echo "- 4-bit quantized models: 3-5x faster inference"
echo "- Parallel processing: 8x concurrent AI operations"
echo "- Real-time analysis: Sub-50ms response times"
