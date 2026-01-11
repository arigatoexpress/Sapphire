#!/bin/bash
# deploy_all.sh - Deploy all services to Cloud Run
# Usage: ./deploy_all.sh [project_id] [region]

set -e

PROJECT_ID="${1:-sapphire-479610}"
REGION="${2:-us-central1}"

echo "🚀 Deploying Sapphire Trading Platform"
echo "   Project: $PROJECT_ID"
echo "   Region: $REGION"
echo ""

# Create Pub/Sub topics if they don't exist
echo "📡 Setting up Pub/Sub topics..."
for topic in trading-signals trade-executed position-updates balance-updates risk-alerts; do
    gcloud pubsub topics create $topic --project=$PROJECT_ID 2>/dev/null || true
    gcloud pubsub topics create $topic --project=$PROJECT_ID 2>/dev/null || true
done

# Prepare Shared Library (Copy to each service context)
echo "📦 Syncing shared library to services..."
for service in bot-aster bot-drift bot-hyperliquid bot-symphony api-gateway alpha-engine; do
    rm -rf "services/$service/shared"
    cp -r "services/shared" "services/$service/"
done

echo "🌐 Deploying API Gateway..."
gcloud run deploy sapphire-api-gateway \
    --source services/api-gateway \
    --project $PROJECT_ID \
    --region $REGION \
    --allow-unauthenticated \
    --min-instances 1 \
    --max-instances 10 \
    --memory 512Mi \
    --quiet

# Deploy Market Scanner
echo "🔍 Deploying Market Scanner..."
gcloud run deploy sapphire-market-scanner \
    --source services/market-scanner \
    --project $PROJECT_ID \
    --region $REGION \
    --min-instances 1 \
    --memory 512Mi \
    --quiet

# Deploy Symphony Bot (Base - Perps)
echo "🎵 Deploying Symphony Bot (Base/Perps)..."
gcloud run deploy sapphire-bot-symphony \
    --source services/bot-symphony \
    --project $PROJECT_ID \
    --region $REGION \
    --min-instances 1 \
    --update-secrets SYMPHONY_API_KEY=SYMPHONY_API_KEY:latest \
    --set-env-vars TRADING_MODE=PERPS,SYMPHONY_AGENT_ID=01b8c2b7-b210-493f-8c76-dafd97663e2c,PYTHONUNBUFFERED=1 \
    --memory 512Mi \
    --quiet

# Deploy Symphony Bot (Monad - Spot)
echo "🎵 Deploying Symphony Bot (Monad/Spot)..."
gcloud run deploy sapphire-bot-symphony-monad \
    --source services/bot-symphony \
    --project $PROJECT_ID \
    --region $REGION \
    --min-instances 1 \
    --update-secrets SYMPHONY_API_KEY=SYMPHONY_API_KEY:latest \
    --set-env-vars TRADING_MODE=SPOT,SYMPHONY_AGENT_ID=f6cc5590-ff96-4077-ac80-9775c7f805cc,PYTHONUNBUFFERED=1 \
    --memory 512Mi \
    --quiet

# Deploy Drift Bot
echo "🌀 Deploying Drift Bot..."
gcloud run deploy sapphire-bot-drift \
    --source services/bot-drift \
    --project $PROJECT_ID \
    --region $REGION \
    --min-instances 1 \
    --update-secrets SOLANA_PRIVATE_KEY=SOLANA_PRIVATE_KEY:latest \
    --set-env-vars PYTHONUNBUFFERED=1 \
    --memory 1Gi \
    --quiet

# Deploy Hyperliquid Bot
echo "🌊 Deploying Hyperliquid Bot..."
gcloud run deploy sapphire-bot-hyperliquid \
    --source services/bot-hyperliquid \
    --project $PROJECT_ID \
    --region $REGION \
    --min-instances 1 \
    --update-secrets HL_SECRET_KEY=HL_SECRET_KEY:latest,HL_ACCOUNT_ADDRESS=HL_ACCOUNT_ADDRESS:latest \
    --set-env-vars PYTHONUNBUFFERED=1 \
    --memory 512Mi \
    --quiet

# Deploy Aster Bot
echo "⭐ Deploying Aster Bot..."
gcloud run deploy sapphire-bot-aster \
    --source services/bot-aster \
    --project $PROJECT_ID \
    --region $REGION \
    --min-instances 1 \
    --update-secrets ASTER_API_KEY=ASTER_API_KEY:latest,ASTER_API_SECRET=ASTER_SECRET_KEY:latest \
    --set-env-vars PYTHONUNBUFFERED=1 \
    --memory 512Mi \
    --quiet
ASTER_URL=$(gcloud run services describe sapphire-bot-aster --project $PROJECT_ID --region $REGION --format 'value(status.url)')

# Deploy Drift Bot (Capture URL)
DRIFT_URL=$(gcloud run services describe sapphire-bot-drift --project $PROJECT_ID --region $REGION --format 'value(status.url)')
# Deploy HL Bot (Capture URL)
HL_URL=$(gcloud run services describe sapphire-bot-hyperliquid --project $PROJECT_ID --region $REGION --format 'value(status.url)')
# Deploy Symphony Bot (Capture URL)
SYMPHONY_URL=$(gcloud run services describe sapphire-bot-symphony --project $PROJECT_ID --region $REGION --format 'value(status.url)')

# Deploy Alpha Engine (The Hub) with Dynamic Service Discovery
echo "🧠 Deploying Alpha Engine (Linked to Bots)..."
echo "   Drift: $DRIFT_URL"
echo "   Hyperliquid: $HL_URL"
gcloud run deploy sapphire-alpha \
    --source services/alpha-engine \
    --project $PROJECT_ID \
    --region $REGION \
    --min-instances 1 \
    --memory 1Gi \
    --set-env-vars BOT_DRIFT_URL=$DRIFT_URL,BOT_HYPERLIQUID_URL=$HL_URL,BOT_ASTER_URL=$ASTER_URL,BOT_SYMPHONY_URL=$SYMPHONY_URL,PYTHONUNBUFFERED=1 \
    --update-secrets TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest,TELEGRAM_CHAT_ID=TELEGRAM_CHAT_ID:latest \
    --quiet

# Deploy Frontend (Trading Dashboard)
echo "💻 Deploying Frontend (Trading Dashboard)..."
if [ -d "trading-dashboard" ]; then
    echo "   Building React App..."
    cd trading-dashboard
    npm install
    npm run build

    echo "   Deploying to Firebase..."
    # Check if firebase CLI is available
    if command -v firebase &> /dev/null; then
        firebase deploy --only hosting --project $PROJECT_ID
    else
        echo "⚠️ Firebase CLI not found. Skipping frontend deployment."
        echo "   Please run 'npm install -g firebase-tools' and try again."
    fi
    cd ..
else
    echo "⚠️ trading-dashboard directory not found. Skipping frontend deployment."
fi



echo ""
echo "✅ All services deployed successfully!"
echo ""
echo "📊 Service URLs:"
gcloud run services list --project $PROJECT_ID --region $REGION
