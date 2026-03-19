#!/bin/bash
# Deploy Log Viewer Dashboard to Cloud Run

set -e

SERVICE_NAME="sapphire-log-viewer"
PROJECT_ID="sapphire-479610"
REGION="us-central1"

echo "=============================================="
echo "Sapphire OS - Log Dashboard Deployment"
echo "=============================================="
echo ""

cd "$(dirname "$0")/.."

echo "[1/4] Building container image..."
cd services/workbench/dashboard
gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME \
    --project $PROJECT_ID
cd -

echo "[2/4] Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
    --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
    --platform managed \
    --region $REGION \
    --project $PROJECT_ID \
    --allow-unauthenticated \
    --set-env-vars GCP_PROJECT=$PROJECT_ID \
    --memory 512Mi \
    --cpu 1 \
    --concurrency 100 \
    --max-instances 2

echo "[3/4] Getting service URL..."
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
    --region $REGION \
    --project $PROJECT_ID \
    --format 'value(status.url)')

echo ""
echo "=============================================="
echo "Deployment Complete!"
echo "=============================================="
echo ""
echo "Log Viewer URL: $SERVICE_URL"
echo ""
echo "Features:"
echo "  - Real-time log streaming (30s refresh)"
echo "  - Filter by service, level, time range"
echo "  - Search logs by message content"
echo "  - Stats dashboard"
echo ""
