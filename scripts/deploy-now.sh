#!/bin/bash
# =============================================================================
# Sapphire V2 - Quick Deploy (Non-Interactive)
# Deploys all microservices via Cloud Build in one command.
#
# Usage:
#   bash scripts/deploy-now.sh                    # Deploy all services
#   bash scripts/deploy-now.sh aster lighter      # Deploy specific services only
#   PROJECT=sapphire-479610 bash scripts/deploy-now.sh  # Override project
# =============================================================================

set -euo pipefail

PROJECT="${PROJECT:-sapphire-479610}"
REGION="${REGION:-europe-west1}"
CONFIG="cloudbuild_microservices.yaml"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check gcloud is authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | head -1 | grep -q .; then
    echo -e "${RED}ERROR: No active gcloud account. Run: gcloud auth login${NC}"
    exit 1
fi

echo -e "${GREEN}Sapphire V2 - Deploying to ${PROJECT} (${REGION})${NC}"
echo ""

# If specific services requested, build a filtered cloudbuild config
SERVICES_FILTER=("$@")

if [ ${#SERVICES_FILTER[@]} -eq 0 ]; then
    echo "Deploying ALL services via ${CONFIG}..."
    echo "  - sapphire-hl (Hyperliquid)"
    echo "  - sapphire-lighter (Lighter)"
    echo "  - sapphire-drift (Drift)"
    echo "  - sapphire-aster (Aster)"
    echo "  - sapphire-symphony (Symphony)"
    echo "  - sapphire-web (Dashboard)"
    echo ""

    gcloud builds submit \
        --config="${CONFIG}" \
        --project="${PROJECT}" \
        --substitutions="_REGION=${REGION}" \
        --async

    echo ""
    echo -e "${GREEN}Cloud Build submitted! Monitor at:${NC}"
    echo "  https://console.cloud.google.com/cloud-build/builds?project=${PROJECT}"
else
    echo "Deploying specific services: ${SERVICES_FILTER[*]}"
    echo ""

    # Full deployment first (build + push), then selective service deploy
    gcloud builds submit \
        --config="${CONFIG}" \
        --project="${PROJECT}" \
        --substitutions="_REGION=${REGION}" \
        --async

    echo ""
    echo -e "${GREEN}Cloud Build submitted! Monitor at:${NC}"
    echo "  https://console.cloud.google.com/cloud-build/builds?project=${PROJECT}"
fi

echo ""
echo -e "${GREEN}Useful commands:${NC}"
echo "  # Watch build progress:"
echo "  gcloud builds list --project=${PROJECT} --limit=1"
echo ""
echo "  # Stream logs of latest build:"
echo "  gcloud builds log \$(gcloud builds list --project=${PROJECT} --limit=1 --format='value(id)') --stream"
echo ""
echo "  # Check service status after deploy:"
echo "  gcloud run services list --project=${PROJECT} --region=${REGION}"
echo ""
echo "  # View service logs:"
echo "  gcloud run services logs read sapphire-aster --project=${PROJECT} --region=${REGION} --limit=50"
echo ""
