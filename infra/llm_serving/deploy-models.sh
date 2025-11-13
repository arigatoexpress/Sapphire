#!/bin/bash

set -e

echo "🚀 Deploying Multi-Model LLM Trading System"
echo "=========================================="

PROJECT_ID="sapphireinfinite"
REGION="us-central1"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if gcloud is authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -1 > /dev/null; then
    log_error "Please authenticate with gcloud first:"
    echo "gcloud auth login"
    exit 1
fi

# Set project
log_info "Setting project to $PROJECT_ID..."
gcloud config set project $PROJECT_ID

# Enable required APIs
log_info "Enabling required APIs..."
gcloud services enable tpu.googleapis.com --quiet
gcloud services enable run.googleapis.com --quiet

# Deploy DeepSeek (already deployed, but ensure it's up)
log_info "Checking DeepSeek deployment..."
if gcloud run services describe deepseek-trader --region=$REGION --quiet 2>/dev/null; then
    log_success "DeepSeek already deployed"
else
    log_info "Deploying DeepSeek..."
    gcloud builds submit . --config infra/llm_serving/cloudbuild.yaml --project=$PROJECT_ID --quiet
fi

# Deploy Qwen
log_info "Deploying Qwen2.5-Coder..."
gcloud builds submit . --config infra/llm_serving/cloudbuild-qwen.yaml --project=$PROJECT_ID --quiet
log_success "Qwen deployed"

# Deploy FinGPT
log_info "Deploying FinGPT..."
gcloud builds submit . --config infra/llm_serving/cloudbuild-fingpt.yaml --project=$PROJECT_ID --quiet
log_success "FinGPT deployed"

# Deploy Phi-3
log_info "Deploying Phi-3..."
gcloud builds submit . --config infra/llm_serving/cloudbuild-phi3.yaml --project=$PROJECT_ID --quiet
log_success "Phi-3 deployed"

# Deploy Model Router
log_info "Deploying Model Router..."
gcloud builds submit . --config infra/llm_serving/cloudbuild-router.yaml --project=$PROJECT_ID --quiet
log_success "Model Router deployed"

# Wait for services to be ready
log_info "Waiting for services to be ready..."
sleep 30

# Check service status
log_info "Checking service status..."
SERVICES=("deepseek-trader" "qwen-trader" "fingpt-trader" "phi3-trader" "model-router")

for service in "${SERVICES[@]}"; do
    if curl -s "https://$service-880429861698.us-central1.run.app/health" > /dev/null; then
        log_success "$service is healthy"
    else
        log_warning "$service may not be ready yet"
    fi
done

log_success "🎉 Multi-Model LLM System Deployment Complete!"
echo ""
echo "📍 Service Endpoints:"
echo "  🔹 DeepSeek: https://deepseek-trader-880429861698.us-central1.run.app"
echo "  🔹 Qwen: https://qwen-trader-880429861698.us-central1.run.app"
echo "  🔹 FinGPT: https://fingpt-trader-880429861698.us-central1.run.app"
echo "  🔹 Phi-3: https://phi3-trader-880429861698.us-central1.run.app"
echo "  🔹 Router: https://model-router-880429861698.us-central1.run.app"
echo ""
echo "🎯 Next Steps:"
echo "  1. Update cloud trader LLM_ENDPOINT to router URL"
echo "  2. Enable LLM trading: ENABLE_LLM_TRADING=true"
echo "  3. Monitor performance in Grafana dashboard"
echo "  4. Test different models with model_preference parameter"
