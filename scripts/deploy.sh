#!/bin/bash
set -e

# SAPPHIRE AI DEPLOYMENT SCRIPT 🚀
# =================================

PROJECT_ID="sapphire-479610"
APP_NAME="aster-trading-system"
REGION="us-central1"

echo "💎 SAPPHIRE AI: CLOUD DEPLOYMENT"
echo "---------------------------------"
echo "Target Project: $PROJECT_ID"
echo "Target Region:  $REGION"
echo ""

# 1. Verification
echo "🔍 Verifying Environment..."
if [ ! -f ".env" ]; then
    echo "❌ Error: .env file missing! Please verify configuration."
    exit 1
fi

# Load Secrets for Injection (Be careful not to print them)
# We will read them into variables to pass to gcloud
source .env

if [ -z "$SYMPHONY_API_KEY" ] || [ -z "$SOLANA_PRIVATE_KEY" ]; then
    echo "❌ Error: Keys missing in .env."
    exit 1
fi

echo "✅ Environment Verified."

# 2. Build Container
echo "🏗️  Building Container Image..."
gcloud builds submit --tag gcr.io/$PROJECT_ID/$APP_NAME

# 3. Deploy to Cloud Run
echo "☁️  Deploying to Cloud Run..."
gcloud run deploy $APP_NAME \
  --image gcr.io/$PROJECT_ID/$APP_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars="SYMPHONY_API_KEY=$SYMPHONY_API_KEY" \
  --set-env-vars="SOLANA_PRIVATE_KEY=$SOLANA_PRIVATE_KEY" \
  --set-env-vars="JUPITER_API_KEY=$JUPITER_API_KEY" \
  --set-env-vars="SYMPHONY_BASE_URL=$SYMPHONY_BASE_URL" \
  --min-instances=1 \
  --max-instances=10 \
  --memory=1Gi \
  --cpu=1

echo ""
echo "✅ DEPLOYMENT SUCCESSFUL!"
echo "Aster is now live in the cloud. 🚀"
