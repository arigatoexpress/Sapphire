#!/bin/bash
# ==============================================================================
# Sapphire V2 Deployment Script
# ==============================================================================

set -e

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-sapphire-trading}"
REGION="${GCP_REGION:-us-east1}"
SERVICE_NAME="sapphire-cloud-trader"
IMAGE_TAG="${IMAGE_TAG:-latest}"

echo "🚀 Sapphire V2 Deployment Script"
echo "================================"
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Service: $SERVICE_NAME"
echo ""

# Check prerequisites
command -v gcloud >/dev/null 2>&1 || { echo "❌ gcloud CLI required"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "❌ docker required"; exit 1; }

# Authenticate
echo "🔐 Authenticating with GCP..."
gcloud auth configure-docker gcr.io --quiet

# Run tests first
echo "🧪 Running tests..."
python -m pytest tests/ -v --tb=short || { echo "❌ Tests failed"; exit 1; }

# Build Docker image
echo "🐳 Building Docker image..."
docker build -t gcr.io/$PROJECT_ID/$SERVICE_NAME:$IMAGE_TAG .

# Push to Container Registry
echo "📤 Pushing to Container Registry..."
docker push gcr.io/$PROJECT_ID/$SERVICE_NAME:$IMAGE_TAG

# Deploy to Cloud Run
echo "☁️ Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
    --image gcr.io/$PROJECT_ID/$SERVICE_NAME:$IMAGE_TAG \
    --region $REGION \
    --platform managed \
    --no-allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --min-instances 1 \
    --max-instances 10 \
    --set-env-vars "ENVIRONMENT=production" \
    --quiet

# Get service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region $REGION --format='value(status.url)')
echo ""
echo "✅ Deployment complete!"
echo "🌐 Service URL: $SERVICE_URL"

# Deploy Terraform infrastructure (if needed)
if [ "$DEPLOY_INFRA" = "true" ]; then
    echo ""
    echo "📦 Applying Terraform..."
    cd terraform
    terraform init
    terraform plan -out=tfplan
    terraform apply tfplan
    cd ..
fi

echo ""
echo "🎉 Sapphire V2 is live!"
