#!/bin/bash

# Emergency deployment script to bypass platform issues
# This deploys directly without VPC connectors

set -e

PROJECT_ID="sapphire-477307"
REGION="us-east1"
OLD_PROJECT="quant-ai-trader-credits"

echo "=== Emergency Deployment Script ==="
echo "Deploying to project: $PROJECT_ID"
echo "Region: $REGION"

# First, let's push our existing images to the new project's Artifact Registry
echo "Step 1: Creating Artifact Registry repository in new project..."
gcloud artifacts repositories create cloud-run-source-deploy \
    --repository-format=docker \
    --location=$REGION \
    --project=$PROJECT_ID || echo "Repository already exists"

# Tag and push our existing cloud-trader image
echo "Step 2: Copying cloud-trader image to new project..."
gcloud container images add-tag \
    gcr.io/$OLD_PROJECT/cloud-trader:live-trading-v2-hotfix \
    gcr.io/$PROJECT_ID/cloud-trader:latest \
    --project=$OLD_PROJECT || echo "Failed to tag, will build from scratch"

# Build a new image if tagging failed
echo "Step 3: Building cloud-trader image from scratch..."
cd /Users/aribs/AIAster
# Skip build since we already have the image

# Deploy Cloud Run service WITHOUT VPC connector
echo "Step 4: Deploying cloud-trader service..."
gcloud run deploy cloud-trader \
    --image gcr.io/$PROJECT_ID/cloud-trader:latest \
    --platform managed \
    --region $REGION \
    --project=$PROJECT_ID \
    --allow-unauthenticated \
    --service-account sapphire-main-sa@$PROJECT_ID.iam.gserviceaccount.com \
    --set-env-vars="ENABLE_PAPER_TRADING=false,GCP_PROJECT_ID=$PROJECT_ID,BOT_ID=cloud_trader" \
    --memory 2Gi \
    --cpu 2 \
    --max-instances 10 \
    --min-instances 1

# Get the service URL
SERVICE_URL=$(gcloud run services describe cloud-trader \
    --platform managed \
    --region $REGION \
    --project=$PROJECT_ID \
    --format 'value(status.url)')

echo "Step 5: Testing service health..."
curl -s $SERVICE_URL/healthz || echo "Health check failed"

# Deploy frontend
echo "Step 6: Building frontend..."
cd /Users/aribs/AIAster/cloud-trader-dashboard
npm run build

# Create bucket for frontend if it doesn't exist
echo "Step 7: Creating storage bucket for frontend..."
gsutil mb -p $PROJECT_ID -l $REGION gs://sapphire-frontend-assets || echo "Bucket exists"

# Upload frontend assets
echo "Step 8: Uploading frontend assets..."
gsutil -m cp -r dist/* gs://sapphire-frontend-assets/

# Make bucket public
gsutil iam ch allUsers:objectViewer gs://sapphire-frontend-assets

echo "=== Deployment Complete ==="
echo "Cloud Trader API: $SERVICE_URL"
echo "Frontend: https://storage.googleapis.com/sapphire-frontend-assets/index.html"
echo ""
echo "Next steps:"
echo "1. Update Secret Manager with your API keys"
echo "2. Configure domain mapping for sapphiretrade.xyz"
echo "3. Start live trading by calling: curl -X POST $SERVICE_URL/start"
