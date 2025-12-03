#!/bin/bash
set -e

PROJECT_ID="sapphire-479610"
REGION="us-east1"
REPO="sapphire-repo"
IMAGE="cloud-trader"
TAG="latest"
FULL_IMAGE_PATH="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$IMAGE:$TAG"

echo "🚀 Starting Local Debug Build for $IMAGE..."

# Build for AMD64 (required for Cloud Run)
echo "🔨 Building image for linux/amd64..."
docker build --platform linux/amd64 -t $FULL_IMAGE_PATH -f Dockerfile .

# Push to Artifact Registry
echo "mw Push to Artifact Registry..."
docker push $FULL_IMAGE_PATH

# Deploy to Cloud Run
echo "🚀 Deploying to Cloud Run..."
gcloud run services update sapphire-cloud-trader \
  --image $FULL_IMAGE_PATH \
  --region $REGION \
  --project $PROJECT_ID

echo "✅ Deployment Complete!"
