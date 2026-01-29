#!/bin/bash
# Pre-Deployment Validation Script for Jupiter Integration

set -e

echo "🔍 Pre-Deployment Validation for Jupiter Integration"
echo "=================================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PROJECT_ID="sapphire-479610"
REGION="us-central1"
SERVICE_NAME="sapphire-v2"

# Check GCP project
echo "1. Checking GCP Project..."
CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null)
if [ "$CURRENT_PROJECT" = "$PROJECT_ID" ]; then
    echo -e "${GREEN}✅ GCP Project: $CURRENT_PROJECT${NC}"
else
    echo -e "${RED}❌ Wrong project! Current: $CURRENT_PROJECT, Expected: $PROJECT_ID${NC}"
    exit 1
fi
echo ""

# Check required secrets
echo "2. Checking Required Secrets..."
REQUIRED_SECRETS=(
    "JUPITER_API_KEY"
    "DRIFT_SOLANA_PRIVATE_KEY"
    "TELEGRAM_BOT_TOKEN"
    "TELEGRAM_CHAT_ID"
    "ASTER_API_KEY"
    "ASTER_SECRET_KEY"
)

ALL_SECRETS_OK=true
for secret in "${REQUIRED_SECRETS[@]}"; do
    if gcloud secrets describe "$secret" --project="$PROJECT_ID" >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Secret exists: $secret${NC}"
    else
        echo -e "${RED}❌ Secret missing: $secret${NC}"
        ALL_SECRETS_OK=false
    fi
done

if [ "$ALL_SECRETS_OK" = false ]; then
    echo -e "${RED}❌ Some secrets are missing. Please create them before deploying.${NC}"
    exit 1
fi
echo ""

# Check cloudbuild.yaml
echo "3. Checking cloudbuild.yaml..."
if [ -f "cloudbuild.yaml" ]; then
    echo -e "${GREEN}✅ cloudbuild.yaml exists${NC}"
    
    # Check for Jupiter configuration
    if grep -q "ENABLE_JUPITER=true" cloudbuild.yaml; then
        echo -e "${GREEN}✅ ENABLE_JUPITER=true found${NC}"
    else
        echo -e "${YELLOW}⚠️  ENABLE_JUPITER not set in cloudbuild.yaml${NC}"
    fi
    
    if grep -q "ENABLE_DRIFT=false" cloudbuild.yaml; then
        echo -e "${GREEN}✅ ENABLE_DRIFT=false found${NC}"
    else
        echo -e "${YELLOW}⚠️  ENABLE_DRIFT not set to false${NC}"
    fi
else
    echo -e "${RED}❌ cloudbuild.yaml not found${NC}"
    exit 1
fi
echo ""

# Check Dockerfile
echo "4. Checking Dockerfile..."
if [ -f "Dockerfile" ]; then
    echo -e "${GREEN}✅ Dockerfile exists${NC}"
else
    echo -e "${RED}❌ Dockerfile not found${NC}"
    exit 1
fi
echo ""

# Check Jupiter integration files
echo "5. Checking Jupiter Integration Files..."
JUPITER_FILES=(
    "cloud_trader/jupiter_trader_unified.py"
    "cloud_trader/trade_verification.py"
    "cloud_trader/definitions.py"
    "services/bot-jupiter/jupiter_client.py"
)

for file in "${JUPITER_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✅ File exists: $file${NC}"
    else
        echo -e "${RED}❌ File missing: $file${NC}"
        exit 1
    fi
done
echo ""

# Check requirements.txt for Solana dependencies
echo "6. Checking Python Dependencies..."
if grep -q "solders" requirements.txt && grep -q "solana" requirements.txt; then
    echo -e "${GREEN}✅ Solana dependencies found in requirements.txt${NC}"
else
    echo -e "${YELLOW}⚠️  Solana dependencies might be missing from requirements.txt${NC}"
fi
echo ""

# Check VPC connector
echo "7. Checking VPC Connector..."
VPC_CONNECTOR="sapphire-conn-us"
if gcloud compute networks vpc-access connectors describe "$VPC_CONNECTOR" --region="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo -e "${GREEN}✅ VPC Connector exists: $VPC_CONNECTOR${NC}"
else
    echo -e "${YELLOW}⚠️  VPC Connector not found: $VPC_CONNECTOR${NC}"
    echo "   Deployment will continue but may fail if VPC connector is required"
fi
echo ""

# Summary
echo "=================================================="
echo -e "${GREEN}🎉 Pre-Deployment Validation PASSED!${NC}"
echo ""
echo "Ready to deploy with:"
echo "  • Jupiter: ENABLED"
echo "  • Drift: DISABLED"
echo "  • Wallet: Configured via DRIFT_SOLANA_PRIVATE_KEY secret"
echo ""
echo "To deploy, run:"
echo "  gcloud builds submit --config=cloudbuild.yaml"
echo ""
