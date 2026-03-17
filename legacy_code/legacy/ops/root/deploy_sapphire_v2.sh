#!/bin/bash
# Complete Deployment Script for Sapphire V2
# Configures secrets, Cloud NAT, and deploys to Cloud Run

set -e

PROJECT_ID="sapphire-479610"
REGION="us-central1"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 Sapphire V2 Deployment Script"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ Error: gcloud CLI is not installed"
    echo "Please install it from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Set the project
echo "🔧 Setting GCP project..."
gcloud config set project $PROJECT_ID

# Step 1: Configure Vertex API Key Secret
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📝 Step 1: Configuring Vertex AI API Key"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

VERTEX_API_KEY="AQ.Ab8RN6I597VxAgJeuNe7zinjSZTYktpb536gjZCFQwsS4Z1_LQ"

if gcloud secrets describe vertex_api_key_v1 --project=$PROJECT_ID &>/dev/null; then
    echo "Secret exists, adding new version..."
    echo -n "$VERTEX_API_KEY" | gcloud secrets versions add vertex_api_key_v1 \
        --project=$PROJECT_ID \
        --data-file=-
else
    echo "Creating new secret..."
    echo -n "$VERTEX_API_KEY" | gcloud secrets create vertex_api_key_v1 \
        --project=$PROJECT_ID \
        --data-file=- \
        --replication-policy="automatic"
fi

echo "✅ Vertex API key configured"

# Step 2: Set up Cloud NAT with Static IP
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🌍 Step 2: Setting up Cloud NAT with Static IP"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Run the Cloud NAT setup script
bash ./setup_cloud_nat.sh

# Get the static IP for display
STATIC_IP=$(gcloud compute addresses describe sapphire-static-ip --region=$REGION --project=$PROJECT_ID --format="get(address)" 2>/dev/null || echo "Not yet created")

# Step 3: Build and Deploy
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🏗️  Step 3: Building and Deploying to Cloud Run"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Trigger Cloud Build
gcloud builds submit \
    --config=cloudbuild.yaml \
    --project=$PROJECT_ID

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Deployment Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📌 Your Static IP: $STATIC_IP"
echo ""
echo "🔍 Next Steps:"
echo "   1. Whitelist IP $STATIC_IP in Aster API settings"
echo "   2. Check deployment status:"
echo "      gcloud run services describe sapphire-v2 --region=$REGION --project=$PROJECT_ID"
echo ""
echo "   3. View logs:"
echo "      gcloud logging read 'resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"sapphire-v2\"' --limit=50 --project=$PROJECT_ID"
echo ""
echo "   4. Get service URL:"
SERVICE_URL=$(gcloud run services describe sapphire-v2 --region=$REGION --project=$PROJECT_ID --format="get(status.url)" 2>/dev/null || echo "Not yet available")
echo "      $SERVICE_URL"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
