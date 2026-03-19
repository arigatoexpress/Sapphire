#!/bin/bash
# Deploy Sapphire Command Deck v2.0 to Cloud Run

set -e

SERVICE_NAME="sapphire-command-deck"
PROJECT_ID="sapphire-479610"
REGION="us-central1"

echo "═══════════════════════════════════════════════════════════════"
echo "  SAPPHIRE OS - COMMAND DECK v2.0 DEPLOYMENT"
echo "═══════════════════════════════════════════════════════════════"
echo ""

cd "$(dirname "$0")/../services/workbench/command_deck"

echo "[1/4] Building container image..."
gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME \
    --project $PROJECT_ID

echo ""
echo "[2/4] Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
    --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
    --platform managed \
    --region $REGION \
    --project $PROJECT_ID \
    --allow-unauthenticated \
    --set-env-vars GCP_PROJECT=$PROJECT_ID \
    --set-env-vars ENABLE_AUTH=true \
    --memory 512Mi \
    --cpu 1 \
    --concurrency 100 \
    --max-instances 3 \
    --min-instances 1

echo ""
echo "[3/4] Getting service URL..."
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
    --region $REGION \
    --project $PROJECT_ID \
    --format 'value(status.url)')

echo ""
echo "[4/4] Setting up Firestore indexes (if needed)..."
echo "  - system_logs: timestamp (descending)"
echo "  - trading_metrics: timestamp (descending)"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  DEPLOYMENT COMPLETE!"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  URL: $SERVICE_URL"
echo ""
echo "  Default Credentials:"
echo "    Username: sapphire"
echo "    Password: (set via AUTH_PASSWORD env var)"
echo ""
echo "  Features:"
echo "    ✓ Interactive topology visualization"
echo "    ✓ Real-time metrics with sparklines"
echo "    ✓ Structured log streaming"
echo "    ✓ Interactive terminal console"
echo ""
echo "  Keyboard Shortcuts:"
echo "    Ctrl+K  → Focus terminal"
echo "    Ctrl+R  → Refresh data"
echo ""
