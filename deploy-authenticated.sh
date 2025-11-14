#!/bin/bash

echo "🔐 SAPPHIRE TRADE - FULLY AUTHENTICATED DEPLOYMENT"
echo "=================================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print status
print_status() {
    echo -e "${BLUE}[$1]${NC} $2"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# STEP 1: GCP Authentication
echo ""
print_status "STEP 1" "Authenticating with Google Cloud"
echo "Authenticating with GCP..."
if gcloud auth login --no-launch-browser; then
    print_success "GCP authentication successful"
else
    print_error "GCP authentication failed"
    echo "Please ensure you're logged in and have access to the sapphireinfinite project"
    exit 1
fi

# STEP 2: Set Project
echo ""
print_status "STEP 2" "Setting GCP project context"
echo "Setting project to sapphireinfinite..."
if gcloud config set project sapphireinfinite; then
    print_success "Project context set to sapphireinfinite"
else
    print_error "Failed to set project context"
    exit 1
fi

# STEP 3: Configure GKE Access
echo ""
print_status "STEP 3" "Configuring GKE cluster access"
echo "Getting GKE cluster credentials..."
if gcloud container clusters get-credentials hft-trading-cluster --zone us-central1-a --project sapphireinfinite; then
    print_success "GKE cluster credentials configured"
else
    print_error "Failed to get GKE cluster credentials"
    echo "Please check that the hft-trading-cluster exists in us-central1-a"
    exit 1
fi

# STEP 4: Verify Cluster Access
echo ""
print_status "STEP 4" "Verifying cluster access"
echo "Checking cluster connectivity..."
if kubectl cluster-info > /dev/null 2>&1; then
    print_success "Cluster connection established"
    echo "Cluster info:"
    kubectl cluster-info | head -3
    echo ""
    echo "Available nodes:"
    kubectl get nodes --no-headers | head -3
else
    print_error "Cluster connection failed"
    echo "Please check your GKE cluster and network configuration"
    exit 1
fi

# STEP 5: Run Deployment Script
echo ""
print_status "STEP 5" "Starting deployment and testing"
echo "Executing deployment script..."
if [[ -f "./deploy-and-test.sh" ]]; then
    chmod +x ./deploy-and-test.sh
    ./deploy-and-test.sh
else
    print_error "deploy-and-test.sh not found in current directory"
    exit 1
fi

echo ""
echo "🎉 FULLY AUTHENTICATED DEPLOYMENT COMPLETE!"
echo ""
echo "💎 SAPPHIRE TRADE AI SYSTEM IS NOW LIVE!"
echo ""
echo "📊 MONITORING COMMANDS:"
echo "kubectl get pods -n trading -w"
echo "kubectl logs -n trading deployment/trading-system-cloud-trader -f"
echo ""
echo "🚀 START TRADING:"
echo "kubectl exec -n trading deployment/trading-system-cloud-trader -- python -c \""
echo "import asyncio"
echo "from cloud_trader.service import TradingService"
echo "async def start():"
echo "    service = TradingService()"
echo "    await service.start()"
echo "    print('🎯 LIVE TRADING ACTIVE!')"
echo "asyncio.run(start())"
echo "\""
