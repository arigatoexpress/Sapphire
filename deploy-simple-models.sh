#!/bin/bash

set -e

echo "🚀 Deploying Simple AI Model Services"
echo "====================================="

PROJECT_ID="quant-ai-trader-credits"
REGION="us-central1"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Set project
log_info "Setting project to $PROJECT_ID..."
gcloud config set project $PROJECT_ID

# Deploy each model
models=("deepseek-trader" "qwen-trader" "fingpt-trader" "phi3-trader")

for model in "${models[@]}"; do
    log_info "Deploying $model..."
    gcloud run deploy "$model" \
        --source infra/llm_serving \
        --dockerfile=Dockerfile.simple \
        --platform managed \
        --region $REGION \
        --allow-unauthenticated \
        --port 8080 \
        --memory 512Mi \
        --cpu 1 \
        --max-instances 3 \
        --concurrency 10 \
        --timeout 300 \
        --set-env-vars "REDIS_URL=redis://10.161.118.219:6379,ORCHESTRATOR_URL=https://wallet-orchestrator-880429861698.us-central1.run.app" \
        --project=$PROJECT_ID \
        --quiet

    log_success "$model deployed"
done

# Deploy Model Router (simplified version)
log_info "Deploying Model Router..."
gcloud run deploy "model-router" \
    --source infra/llm_serving \
    --dockerfile=Dockerfile.simple \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --port 8080 \
    --memory 512Mi \
    --cpu 1 \
    --max-instances 3 \
    --concurrency 10 \
    --timeout 300 \
    --set-env-vars "REDIS_URL=redis://10.161.118.219:6379,ORCHESTRATOR_URL=https://wallet-orchestrator-880429861698.us-central1.run.app" \
    --project=$PROJECT_ID \
    --quiet

log_success "Model Router deployed"

# Wait for services
log_info "Waiting for services to be ready..."
sleep 15

# Check service status
log_info "Checking service status..."
SERVICES=("deepseek-trader" "qwen-trader" "fingpt-trader" "phi3-trader" "model-router")

for service in "${SERVICES[@]}"; do
    if curl -s --max-time 5 "https://$service-880429861698.us-central1.run.app/health" > /dev/null; then
        log_success "$service is healthy"
    else
        echo "⚠️ $service may not be ready yet"
    fi
done

log_success "🎉 Simple AI Model System Deployment Complete!"
echo ""
echo "📍 Service Endpoints:"
echo "  🔹 DeepSeek: https://deepseek-trader-880429861698.us-central1.run.app"
echo "  🔹 Qwen: https://qwen-trader-880429861698.us-central1.run.app"
echo "  🔹 FinGPT: https://fingpt-trader-880429861698.us-central1.run.app"
echo "  🔹 Phi-3: https://phi3-trader-880429861698.us-central1.run.app"
echo "  🔹 Router: https://model-router-880429861698.us-central1.run.app"
echo ""
echo "🎯 Next Steps:"
echo "  1. Enable LLM trading: ENABLE_LLM_TRADING=true"
echo "  2. Test model inference with dashboard"
echo "  3. Monitor performance and upgrade to real LLMs"
