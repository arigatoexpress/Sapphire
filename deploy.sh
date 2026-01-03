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

# Redis Config
REDIS_IP=$(gcloud redis instances list --region ${REGION} --filter="name:projects/${PROJECT_ID}/locations/${REGION}/instances/sapphire-cache" --format="value(host)" 2>/dev/null || echo "")
REDIS_URL_ENV=""

if [ -n "$REDIS_IP" ]; then
    echo -e "${GREEN}✅ Found Redis at ${REDIS_IP}${NC}"
    REDIS_URL_ENV="REDIS_URL=redis://${REDIS_IP}:6379,CACHE_BACKEND=redis"
else
    echo -e "${YELLOW}⚠️ Redis not found. Using memory cache.${NC}"
    REDIS_URL_ENV="CACHE_BACKEND=memory"
fi

# Database Config
DB_INSTANCE=$(gcloud sql instances list --project "${PROJECT_ID}" --filter="name:sapphire-db*" --format="value(name)" --limit=1 2>/dev/null || echo "")
DB_IP=""

if [ -n "$DB_INSTANCE" ]; then
    echo -e "${GREEN}🔍 Fetching Private IP for ${DB_INSTANCE}...${NC}"
    # Use jq for robust parsing
    DB_IP=$(gcloud sql instances describe "$DB_INSTANCE" --project "${PROJECT_ID}" --format="json" | jq -r '.ipAddresses[] | select(.type=="PRIVATE") | .ipAddress' | head -n 1)
fi

if [ -n "$DB_IP" ]; then
    echo -e "${GREEN}✅ Found Database at ${DB_IP}. Updating Secret Manager...${NC}"
    DB_URL="postgresql://trading_user:changeme123@${DB_IP}:5432/trading_db"
    # Update secret with -n to avoid trailing newline
    echo -n "$DB_URL" | gcloud secrets versions add DATABASE_URL --data-file=- --project="$PROJECT_ID" &>/dev/null
else
    echo -e "${RED}❌ Database instance not found! Storage will fail.${NC}"
fi

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
    "DATABASE_URL"
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

# Features and standard Env Vars
ENABLE_ASTER=${ENABLE_ASTER:-true}
ENABLE_TELEGRAM=${ENABLE_TELEGRAM:-true}
DATABASE_ENABLED=true

# Construct literal Env Vars string (minimal to avoid shell concatenation issues)
ENV_VARS_LIST="PYTHONUNBUFFERED=1,ENABLE_ASTER=${ENABLE_ASTER},ENABLE_TELEGRAM=${ENABLE_TELEGRAM},DATABASE_ENABLED=${DATABASE_ENABLED}"
if [ -n "$REDIS_URL_ENV" ]; then
    ENV_VARS_LIST="${ENV_VARS_LIST},${REDIS_URL_ENV}"
fi

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
    --vpc-connector sapphire-conn \
    --vpc-egress all-traffic \
    --set-env-vars=${ENV_VARS_LIST} \
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
