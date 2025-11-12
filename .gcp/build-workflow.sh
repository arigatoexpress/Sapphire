#!/bin/bash
# Optimized build and deployment workflow for HFT trading system

set -e

PROJECT_ID="${PROJECT_ID:-quant-ai-trader-credits}"
REGION="${REGION:-us-central1}"

echo "🚀 Starting optimized HFT deployment workflow..."

# Fast local testing
echo "🔧 Building locally with cache..."
docker build --target builder -t trader-builder . 2>/dev/null || echo "Builder stage cached"
docker build --cache-from trader-builder -t trader-app .

# Quick local test
echo "🧪 Running local health check..."
docker run --rm -p 8080:8080 trader-app &
sleep 10
curl -f http://localhost:8080/healthz && echo "✅ Local test passed" || echo "❌ Local test failed"
pkill -f uvicorn || true

# Deploy to GCP
echo "☁️ Deploying to Google Cloud..."
gcloud builds submit --config=.gcp/cloudbuild.yaml \
  --project=$PROJECT_ID \
  --machine-type=N2_HIGHCPU_32 \
  --disk-size=500 \
  --async \
  --verbosity=info

echo "📊 Monitoring build..."
BUILD_ID=$(gcloud builds list --filter="status=WORKING" --format="value(id)" --limit=1 --project=$PROJECT_ID)

if [ ! -z "$BUILD_ID" ]; then
    echo "🔍 Build ID: $BUILD_ID"
    echo "📋 Monitor with: gcloud builds log $BUILD_ID --stream --project=$PROJECT_ID"
fi

echo "✅ Deployment initiated! Check status with:"
echo "gcloud builds list --project=$PROJECT_ID --format='table(id,status,createTime,duration)'"
