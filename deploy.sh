#!/bin/bash
# =============================================================================
# Sapphire AI Trading System - Cloud Run Deployment Script
# =============================================================================
# Usage:
#   ./deploy.sh                    # Full deploy (build + push + deploy)
#   ./deploy.sh --build-only       # Just build the Docker image
#   ./deploy.sh --dry-run          # Show commands without executing
# =============================================================================

set -e

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-sapphire-479610}"
REGION="${GCP_REGION:-northamerica-northeast1}"
SERVICE_NAME="sapphire-cloud-trader"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"
CACHE_BUST=$(date +%Y%m%d_%H%M%S)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Sapphire AI Trading System - Deployment${NC}"
echo "================================================"
echo "Project: ${PROJECT_ID}"
echo "Region:  ${REGION}"
echo "Service: ${SERVICE_NAME}"
echo "================================================"

# Parse arguments
BUILD_ONLY=false
DRY_RUN=false
for arg in "$@"; do
    case $arg in
        --build-only)
            BUILD_ONLY=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
    esac
done

# ============================================================================
# PRE-DEPLOYMENT VALIDATION
# ============================================================================
echo ""
echo -e "${GREEN}🔍 Running pre-deployment validation...${NC}"
if ! python3 tools/validate_deployment.py; then
    echo -e "${RED}❌ Validation failed! Fix errors before deploying.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Validation passed!${NC}"
echo ""

run_cmd() {
    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}[DRY-RUN] $1${NC}"
    else
        echo -e "${GREEN}[RUNNING] $1${NC}"
        eval "$1"
    fi
}

# Step 1: Build frontend (if needed)
if [ -d "trading-dashboard" ]; then
    echo -e "\n${GREEN}📦 Building frontend...${NC}"
    if [ ! -d "trading-dashboard/dist" ] || [ "$1" == "--rebuild-frontend" ]; then
        run_cmd "cd trading-dashboard && npm install && npm run build && cd .."
    else
        echo "   ✓ Frontend dist exists, skipping build."
    fi
fi

# Step 2: Build Docker image via Cloud Build
echo -e "\n${GREEN}🐳 Building Docker image via Google Cloud Build...${NC}"
run_cmd "gcloud builds submit --tag ${IMAGE_NAME}:latest --tag ${IMAGE_NAME}:${CACHE_BUST} --project ${PROJECT_ID} ."

if [ "$BUILD_ONLY" = true ]; then
    echo -e "\n${GREEN}✅ Build complete! Image: ${IMAGE_NAME}:latest${NC}"
    exit 0
fi

# Step 3: Skip manual push (Builds Submit handles this)
echo -e "\n${GREEN}📤 Image pushed automatically by Cloud Build.${NC}"

# Step 4: Deploy to Cloud Run
echo -e "\n${GREEN}☁️ Deploying to Cloud Run...${NC}"

# Dynamic Secret Mapping
SECRETS_LIST=(
    "ASTER_API_KEY"
    "ASTER_SECRET_KEY"
    "SYMPHONY_API_KEY"
    "HL_SECRET_KEY"
    "HL_ACCOUNT_ADDRESS"
    "TELEGRAM_BOT_TOKEN"
    "TELEGRAM_CHAT_ID"
    "GEMINI_API_KEY"
    "GROK_API_KEY"
    "SOLANA_PRIVATE_KEY"
)

ACTIVE_SECRETS=""
for secret in "${SECRETS_LIST[@]}"; do
    if gcloud secrets describe "$secret" --project "$PROJECT_ID" &>/dev/null; then
        if [ -n "$ACTIVE_SECRETS" ]; then ACTIVE_SECRETS+=","; fi
        ACTIVE_SECRETS+="${secret}=${secret}:latest"
    else
        echo -e "${YELLOW}⚠️ Secret ${secret} not found in Secret Manager. Skipping mapping.${NC}"
    fi
done

# Features
ENABLE_ASTER="${ENABLE_ASTER:-False}"
ENABLE_TELEGRAM="${ENABLE_TELEGRAM:-True}"

run_cmd "gcloud run deploy ${SERVICE_NAME} \
    --image ${IMAGE_NAME}:${CACHE_BUST} \
    --region ${REGION} \
    --platform managed \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 3600 \
    --concurrency 80 \
    --min-instances 0 \
    --max-instances 10 \
    --set-env-vars=PYTHONUNBUFFERED=1,CACHE_BACKEND=memory,ENABLE_ASTER=${ENABLE_ASTER},ENABLE_TELEGRAM=${ENABLE_TELEGRAM} \
    --set-secrets=${ACTIVE_SECRETS}"

# Step 5: Get service URL
echo -e "\n${GREEN}🔗 Getting service URL...${NC}"
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region ${REGION} --format 'value(status.url)' 2>/dev/null || echo "")

if [ -n "$SERVICE_URL" ]; then
    echo -e "\n${GREEN}✅ Deployment Complete!${NC}"
    echo "================================================"
    echo -e "Service URL: ${GREEN}${SERVICE_URL}${NC}"
    echo -e "Health Check: ${SERVICE_URL}/healthz"
    echo -e "Dashboard: ${SERVICE_URL}/"
    echo "================================================"
else
    echo -e "\n${YELLOW}⚠️ Could not retrieve service URL. Check Cloud Console.${NC}"
fi
