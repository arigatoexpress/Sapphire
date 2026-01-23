#!/bin/bash
# Deployment Script for Sapphire V2 with Jupiter Integration

set -e

echo "🚀 Deploying Sapphire V2 with Jupiter Integration"
echo "=================================================="
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Run pre-deployment checks
echo -e "${BLUE}Running pre-deployment validation...${NC}"
if bash pre-deploy-check.sh; then
    echo -e "${GREEN}✅ Pre-deployment checks passed${NC}"
    echo ""
else
    echo "❌ Pre-deployment checks failed. Please fix issues before deploying."
    exit 1
fi

# Confirm deployment
echo -e "${YELLOW}Ready to deploy with:${NC}"
echo "  • Project: sapphire-479610"
echo "  • Service: sapphire-v2"
echo "  • Region: us-central1"
echo "  • Jupiter: ENABLED"
echo "  • Drift: DISABLED"
echo ""
echo -e "${YELLOW}This will:${NC}"
echo "  1. Run tests"
echo "  2. Build Docker image"
echo "  3. Push to GCR"
echo "  4. Deploy to Cloud Run"
echo "  5. Configure environment variables"
echo ""

read -p "Continue with deployment? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled."
    exit 0
fi

# Start deployment
echo ""
echo -e "${BLUE}Starting Cloud Build deployment...${NC}"
echo ""

gcloud builds submit \
  --config=cloudbuild.yaml \
  --project=sapphire-479610

if [ $? -eq 0 ]; then
    echo ""
    echo "=================================================="
    echo -e "${GREEN}🎉 Deployment Successful!${NC}"
    echo "=================================================="
    echo ""
    echo "Next steps:"
    echo "1. Check service status:"
    echo "   gcloud run services describe sapphire-v2 --region us-central1"
    echo ""
    echo "2. View logs:"
    echo "   gcloud run services logs read sapphire-v2 --region us-central1 --limit 50"
    echo ""
    echo "3. Check for Jupiter initialization:"
    echo "   gcloud run services logs read sapphire-v2 --region us-central1 --filter='Jupiter Trader initialized'"
    echo ""
    echo "4. Get service URL:"
    echo "   gcloud run services describe sapphire-v2 --region us-central1 --format='value(status.url)'"
    echo ""
    echo "5. Test health endpoint:"
    echo "   curl \$(gcloud run services describe sapphire-v2 --region us-central1 --format='value(status.url)')/health"
    echo ""
    echo "Your Jupiter wallet: 4jnvRT5uk7MzXp1swJpbcXStKVecnuDCLjxe6ccsVTik"
    echo "Explorer: https://solscan.io/account/4jnvRT5uk7MzXp1swJpbcXStKVecnuDCLjxe6ccsVTik"
    echo ""
else
    echo ""
    echo "❌ Deployment failed. Check the logs above for errors."
    exit 1
fi
