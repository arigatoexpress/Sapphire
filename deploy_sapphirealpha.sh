#!/bin/bash
# =============================================================================
# Sapphire Alpha Deployment Script
# Deploys to sapphirealpha.xyz with full frontend and backend
# =============================================================================

set -e

echo "=============================================="
echo "  SAPPHIRE ALPHA DEPLOYMENT"
echo "  Target: sapphirealpha.xyz"
echo "=============================================="

# Configuration
PROJECT_ID="sapphire-479610"
REGION="us-central1"
SERVICE_NAME="sapphire-v2"
VPC_CONNECTOR="sapphire-conn-us"
DOMAIN="sapphirealpha.xyz"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Step 1: Build Frontend
log_info "Step 1: Building Vue Frontend..."
cd sapphire-web
npm install
npm run build
cd ..
log_info "Frontend build complete!"

# Step 2: Build Docker Image
log_info "Step 2: Building Docker Image..."
docker build -t gcr.io/${PROJECT_ID}/sapphire-trader:latest .

# Step 3: Push to Container Registry
log_info "Step 3: Pushing to GCR..."
docker push gcr.io/${PROJECT_ID}/sapphire-trader:latest

# Step 4: Deploy to Cloud Run
log_info "Step 4: Deploying to Cloud Run..."
gcloud run deploy ${SERVICE_NAME} \
    --image gcr.io/${PROJECT_ID}/sapphire-trader:latest \
    --region ${REGION} \
    --platform managed \
    --allow-unauthenticated \
    --memory 8Gi \
    --cpu 4 \
    --min-instances 1 \
    --max-instances 10 \
    --vpc-connector ${VPC_CONNECTOR} \
    --vpc-egress all-traffic \
    --set-env-vars "ENVIRONMENT=production,LOG_LEVEL=INFO,ENABLE_JUPITER=true,ENABLE_DRIFT=true,ENABLE_ASTER=true,ENABLE_HYPERLIQUID=true,ENABLE_LIGHTER=true,ENABLE_SYMPHONY=true,ENABLE_PUBSUB=true,GCP_PROJECT_ID=${PROJECT_ID}"

# Step 5: Get Cloud Run URL
log_info "Step 5: Getting Cloud Run URL..."
CLOUD_RUN_URL=$(gcloud run services describe ${SERVICE_NAME} --region ${REGION} --format='value(status.url)')
log_info "Cloud Run URL: ${CLOUD_RUN_URL}"

# Step 6: Map Custom Domain (if not already mapped)
log_info "Step 6: Checking domain mapping for ${DOMAIN}..."
if gcloud run domain-mappings describe --domain=${DOMAIN} --region=${REGION} 2>/dev/null; then
    log_info "Domain ${DOMAIN} already mapped"
else
    log_info "Creating domain mapping for ${DOMAIN}..."
    gcloud run domain-mappings create \
        --service=${SERVICE_NAME} \
        --domain=${DOMAIN} \
        --region=${REGION} || log_warn "Domain mapping may need manual setup"
fi

# Step 7: Deploy Firebase Hosting (optional backup)
log_info "Step 7: Deploying to Firebase Hosting..."
firebase deploy --only hosting --project ${PROJECT_ID} || log_warn "Firebase deploy skipped"

echo ""
echo "=============================================="
echo "  DEPLOYMENT COMPLETE!"
echo "=============================================="
echo ""
echo "Cloud Run URL: ${CLOUD_RUN_URL}"
echo "Custom Domain: https://${DOMAIN}"
echo ""
echo "DNS Configuration Required:"
echo "  Add an A record pointing ${DOMAIN} to your Cloud Run IP"
echo "  Or use Cloud Run domain mapping DNS records"
echo ""
log_info "Deployment finished successfully!"
