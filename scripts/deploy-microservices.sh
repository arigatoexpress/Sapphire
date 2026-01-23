#!/bin/bash
# Sapphire V2 Microservices - Complete Deployment Script
# This script handles the full deployment pipeline

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Sapphire V2 Microservices Deployment Script         ║${NC}"
echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo ""

# ============================================================================
# STEP 1: Configuration
# ============================================================================

echo -e "${YELLOW}📋 Step 1: Configuration${NC}"

# Get current project
CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null)

if [ -z "$CURRENT_PROJECT" ]; then
    echo -e "${RED}❌ No GCP project configured!${NC}"
    echo "Please run: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

echo -e "${GREEN}✅ Current GCP Project: $CURRENT_PROJECT${NC}"

# Confirm project
echo ""
read -p "Deploy to project '$CURRENT_PROJECT'? (yes/no): " CONFIRM_PROJECT

if [ "$CONFIRM_PROJECT" != "yes" ]; then
    echo -e "${YELLOW}⚠️  Deployment cancelled${NC}"
    echo "To change project, run: gcloud config set project YOUR_PROJECT_ID"
    exit 0
fi

export GCP_PROJECT_ID="$CURRENT_PROJECT"

# Configuration
export REGION="europe-west1"
export TOPIC_NAME="sapphire-service-events"
export SUBSCRIPTION_NAME="sapphire-web-events"

echo ""
echo -e "${GREEN}Configuration:${NC}"
echo "  Project ID: $GCP_PROJECT_ID"
echo "  Region: $REGION"
echo "  PubSub Topic: $TOPIC_NAME"
echo "  PubSub Subscription: $SUBSCRIPTION_NAME"
echo ""

# ============================================================================
# STEP 2: Enable Required APIs
# ============================================================================

echo -e "${YELLOW}📡 Step 2: Enabling Required GCP APIs${NC}"

REQUIRED_APIS=(
    "cloudbuild.googleapis.com"
    "run.googleapis.com"
    "pubsub.googleapis.com"
    "firestore.googleapis.com"
    "containerregistry.googleapis.com"
    "secretmanager.googleapis.com"
)

for API in "${REQUIRED_APIS[@]}"; do
    echo -n "  Enabling $API... "
    if gcloud services enable "$API" --project="$GCP_PROJECT_ID" 2>/dev/null; then
        echo -e "${GREEN}✅${NC}"
    else
        echo -e "${YELLOW}(already enabled)${NC}"
    fi
done

echo ""

# ============================================================================
# STEP 3: Setup PubSub Infrastructure
# ============================================================================

echo -e "${YELLOW}📨 Step 3: Setting up PubSub Infrastructure${NC}"

# Create topic
echo -n "  Creating PubSub topic '$TOPIC_NAME'... "
if gcloud pubsub topics describe "$TOPIC_NAME" --project="$GCP_PROJECT_ID" &>/dev/null; then
    echo -e "${YELLOW}(already exists)${NC}"
else
    gcloud pubsub topics create "$TOPIC_NAME" \
        --project="$GCP_PROJECT_ID" \
        --message-retention-duration=7d \
        --quiet
    echo -e "${GREEN}✅${NC}"
fi

# Create subscription
echo -n "  Creating PubSub subscription '$SUBSCRIPTION_NAME'... "
if gcloud pubsub subscriptions describe "$SUBSCRIPTION_NAME" --project="$GCP_PROJECT_ID" &>/dev/null; then
    echo -e "${YELLOW}(already exists)${NC}"
else
    gcloud pubsub subscriptions create "$SUBSCRIPTION_NAME" \
        --topic="$TOPIC_NAME" \
        --project="$GCP_PROJECT_ID" \
        --ack-deadline=60 \
        --message-retention-duration=7d \
        --expiration-period=never \
        --quiet
    echo -e "${GREEN}✅${NC}"
fi

echo ""

# ============================================================================
# STEP 4: Verify Secrets (Optional Check)
# ============================================================================

echo -e "${YELLOW}🔐 Step 4: Checking for Required Secrets${NC}"

echo -e "${BLUE}Note: Secrets should be configured in Secret Manager or as environment variables${NC}"
echo ""

REQUIRED_SECRETS=(
    "ASTER_API_KEY"
    "ASTER_SECRET_KEY"
    "HL_SECRET_KEY"
    "HL_ACCOUNT_ADDRESS"
    "SOLANA_PRIVATE_KEY"
)

echo "Required secrets for trading:"
for SECRET in "${REQUIRED_SECRETS[@]}"; do
    echo "  - $SECRET"
done

echo ""
read -p "Have you configured all required secrets? (yes/no): " CONFIRM_SECRETS

if [ "$CONFIRM_SECRETS" != "yes" ]; then
    echo -e "${YELLOW}⚠️  Warning: Deployment will continue, but services may fail without secrets${NC}"
    read -p "Continue anyway? (yes/no): " CONTINUE_ANYWAY
    if [ "$CONTINUE_ANYWAY" != "yes" ]; then
        echo -e "${YELLOW}⚠️  Deployment cancelled${NC}"
        exit 0
    fi
fi

echo ""

# ============================================================================
# STEP 5: Build and Deploy Services
# ============================================================================

echo -e "${YELLOW}🚀 Step 5: Submitting Cloud Build${NC}"
echo ""

echo -e "${BLUE}This will:${NC}"
echo "  1. Build unified Docker image"
echo "  2. Push to GCR: gcr.io/$GCP_PROJECT_ID/sapphire-unified:latest"
echo "  3. Deploy 6 Cloud Run services in parallel:"
echo "     - sapphire-hl (Hyperliquid)"
echo "     - sapphire-lighter (Lighter.xyz)"
echo "     - sapphire-drift (Drift Protocol)"
echo "     - sapphire-aster (AsterDEX)"
echo "     - sapphire-symphony (Orchestration)"
echo "     - sapphire-web (Dashboard)"
echo ""
echo -e "${YELLOW}⏱️  Estimated time: 10-15 minutes${NC}"
echo ""

read -p "Submit Cloud Build now? (yes/no): " CONFIRM_BUILD

if [ "$CONFIRM_BUILD" != "yes" ]; then
    echo -e "${YELLOW}⚠️  Deployment cancelled${NC}"
    exit 0
fi

echo ""
echo -e "${GREEN}🏗️  Submitting Cloud Build...${NC}"
echo ""

# Submit build
gcloud builds submit \
    --config=cloudbuild_microservices.yaml \
    --project="$GCP_PROJECT_ID" \
    --substitutions=_REGION="$REGION"

BUILD_EXIT_CODE=$?

echo ""

if [ $BUILD_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ Cloud Build completed successfully!${NC}"
else
    echo -e "${RED}❌ Cloud Build failed with exit code $BUILD_EXIT_CODE${NC}"
    echo ""
    echo "To view logs:"
    echo "  gcloud builds list --limit=1"
    echo "  gcloud builds log \$(gcloud builds list --limit=1 --format='value(id)')"
    exit 1
fi

echo ""

# ============================================================================
# STEP 6: Verify Deployment
# ============================================================================

echo -e "${YELLOW}🔍 Step 6: Verifying Deployment${NC}"
echo ""

echo "Checking deployed services..."
gcloud run services list --region="$REGION" --project="$GCP_PROJECT_ID"

echo ""
echo -e "${GREEN}✅ Deployment verification:${NC}"

# Get service URLs
echo ""
echo "Service URLs:"

SERVICES=(
    "sapphire-hl"
    "sapphire-lighter"
    "sapphire-drift"
    "sapphire-aster"
    "sapphire-symphony"
    "sapphire-web"
)

for SERVICE in "${SERVICES[@]}"; do
    URL=$(gcloud run services describe "$SERVICE" \
        --region="$REGION" \
        --project="$GCP_PROJECT_ID" \
        --format="value(status.url)" 2>/dev/null || echo "NOT DEPLOYED")

    if [ "$URL" != "NOT DEPLOYED" ]; then
        echo -e "  ${GREEN}✅${NC} $SERVICE: $URL"
    else
        echo -e "  ${RED}❌${NC} $SERVICE: NOT DEPLOYED"
    fi
done

echo ""

# Get sapphire-web URL for dashboard
WEB_URL=$(gcloud run services describe sapphire-web \
    --region="$REGION" \
    --project="$GCP_PROJECT_ID" \
    --format="value(status.url)" 2>/dev/null || echo "")

if [ -n "$WEB_URL" ]; then
    echo -e "${GREEN}🌐 Dashboard URL: $WEB_URL${NC}"
    echo ""
    echo "Open dashboard:"
    echo -e "${BLUE}  $WEB_URL${NC}"
    echo ""
fi

# ============================================================================
# STEP 7: Health Check
# ============================================================================

echo -e "${YELLOW}💓 Step 7: Health Check${NC}"
echo ""

echo "Waiting 60 seconds for services to start and send heartbeats..."
sleep 60

echo ""
echo "Checking for PubSub events..."

MESSAGES=$(gcloud pubsub subscriptions pull "$SUBSCRIPTION_NAME" \
    --project="$GCP_PROJECT_ID" \
    --limit=5 \
    --auto-ack 2>/dev/null || echo "")

if [ -n "$MESSAGES" ]; then
    echo -e "${GREEN}✅ PubSub events detected!${NC}"
    echo "$MESSAGES"
else
    echo -e "${YELLOW}⚠️  No PubSub messages yet (this is normal for new deployments)${NC}"
    echo "Services may take a few minutes to initialize and send heartbeats"
fi

echo ""

# ============================================================================
# STEP 8: Next Steps
# ============================================================================

echo -e "${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           Deployment Complete! 🎉                      ║${NC}"
echo -e "${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
echo ""

echo -e "${BLUE}Next Steps:${NC}"
echo ""
echo "1. Open the dashboard:"
if [ -n "$WEB_URL" ]; then
    echo -e "   ${BLUE}$WEB_URL${NC}"
else
    echo "   (run: gcloud run services describe sapphire-web --region=$REGION --format='value(status.url)')"
fi
echo ""

echo "2. Monitor logs:"
echo "   gcloud logging read 'resource.labels.service_name=sapphire-web' --limit=50"
echo ""

echo "3. Check fleet health:"
if [ -n "$WEB_URL" ]; then
    echo "   curl $WEB_URL/api/fleet/health"
else
    echo "   curl \$WEB_URL/api/fleet/health"
fi
echo ""

echo "4. View PubSub events:"
echo "   gcloud pubsub subscriptions pull $SUBSCRIPTION_NAME --limit=10"
echo ""

echo "5. Monitor Cloud Run metrics:"
echo "   https://console.cloud.google.com/run?project=$GCP_PROJECT_ID"
echo ""

echo -e "${YELLOW}📚 Documentation:${NC}"
echo "  - Architecture: MICROSERVICES_ARCHITECTURE.md"
echo "  - Quick Start: QUICKSTART_MICROSERVICES.md"
echo "  - Refactoring Summary: REFACTORING_SUMMARY.md"
echo ""

echo -e "${GREEN}🚀 Sapphire V2 Microservices is now live!${NC}"
echo ""
