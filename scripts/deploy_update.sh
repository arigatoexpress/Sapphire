#!/bin/bash
set -e

PROJECT_ID="sapphire-479610"
REGION="us-east1"

echo "🚀 Updating Cloud Run Services..."

# Update Cloud Trader
echo "🔵 Updating Cloud Trader..."
gcloud run services update sapphire-cloud-trader \
    --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/sapphire-repo/cloud-trader:latest \
    --region ${REGION} \
    --project ${PROJECT_ID}

# Update Hyperliquid Trader
echo "🟢 Updating Hyperliquid Trader..."
gcloud run services update sapphire-hyperliquid-trader \
    --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/sapphire-repo/hyperliquid-trader:latest \
    --region northamerica-northeast1 \
    --project ${PROJECT_ID}

# Update Dashboard
echo "🟣 Updating Dashboard..."
gcloud run services update sapphire-dashboard \
    --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/sapphire-repo/dashboard:latest \
    --region ${REGION} \
    --project ${PROJECT_ID}

echo "✅ All services updated successfully!"
