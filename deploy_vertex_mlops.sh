#!/bin/bash
# Vertex AI MLOps Deployment Script for Sapphire Trading System

PROJECT_ID="sapphireinfinite"
LOCATION="us-central1"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

echo "🚀 Setting up Vertex AI MLOps for Sapphire Trading System"
echo "========================================================="

# Set project
gcloud config set project $PROJECT_ID

# Enable required APIs
echo "📦 Enabling Vertex AI APIs..."
gcloud services enable aiplatform.googleapis.com
gcloud services enable ml.googleapis.com
gcloud services enable notebooks.googleapis.com

# Create Vertex AI metadata store
echo "🏪 Creating Vertex AI Metadata Store..."
gcloud ai metadata-stores create sapphire-metadata-store \
  --description="Metadata store for Sapphire Trading AI models" \
  --location=$LOCATION

# Create experiment tracking
echo "🧪 Setting up Experiment Tracking..."
gcloud ai experiments create momentum-analysis-experiment \
  --display-name="DeepSeek Momentum Analysis Optimization" \
  --description="Experiment tracking for momentum prediction optimization" \
  --location=$LOCATION

gcloud ai experiments create strategy-optimization-experiment \
  --display-name="Qwen Strategy Optimization" \
  --description="Multi-armed bandit and reinforcement learning optimization" \
  --location=$LOCATION

gcloud ai experiments create vpin-hft-experiment \
  --display-name="VPIN High-Frequency Trading Optimization" \
  --description="Real-time volume synchronized probability optimization" \
  --location=$LOCATION

# Create feature store
echo "🗄️  Setting up Feature Store..."
gcloud ai feature-stores create sapphire-feature-store \
  --display-name="Sapphire Trading Feature Store" \
  --description="Real-time and historical features for trading models" \
  --location=$LOCATION \
  --online-serving-config-fixed-node-count=3 \
  --encryption-spec-key-name=""

# Create entity types
gcloud ai feature-stores entity-types create market-data \
  --feature-store=sapphire-feature-store \
  --description="Real-time market data features" \
  --location=$LOCATION

gcloud ai feature-stores entity-types create trading-signals \
  --feature-store=sapphire-feature-store \
  --description="Generated trading signals and predictions" \
  --location=$LOCATION

# Create model monitoring jobs (would be done after model deployment)
echo "📊 Model monitoring jobs will be created after model deployment..."
echo "   - Drift detection for all deployed models"
echo "   - Performance monitoring with custom metrics"
echo "   - Automated alerts and retraining triggers"

# Create Vertex AI Workbench instance for development
echo "💻 Creating Vertex AI Workbench instance..."
gcloud notebooks instances create sapphire-ml-workbench \
  --vm-image-project=deeplearning-platform-release \
  --vm-image-name=tf2-2-11-cu113-notebooks-v20221206-debian-10-py310 \
  --machine-type=n1-standard-8 \
  --location=$LOCATION \
  --network=default \
  --subnet=default

echo ""
echo "✅ Vertex AI MLOps Setup Complete!"
echo "=================================="
echo ""
echo "🎯 Configured Components:"
echo "   ✅ Vertex AI Metadata Store"
echo "   ✅ Experiment Tracking (3 experiments)"
echo "   ✅ Feature Store with entity types"
echo "   ✅ Vertex AI Workbench instance"
echo "   ✅ API enablements"
echo ""
echo "📋 Next Steps:"
echo "1. Deploy models to Vertex AI Endpoints"
echo "2. Create model monitoring jobs"
echo "3. Set up CI/CD pipelines"
echo "4. Configure automated retraining"
echo ""
echo "🔍 Access URLs:"
echo "   - Vertex AI Console: https://console.cloud.google.com/vertex-ai"
echo "   - Workbench: https://console.cloud.google.com/vertex-ai/workbench"
echo "   - Feature Store: https://console.cloud.google.com/vertex-ai/feature-store"
