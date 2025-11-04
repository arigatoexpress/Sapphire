#!/usr/bin/env bash

set -euo pipefail

# Staging environment deployment script
# This deploys to a staging environment for testing before production

PROJECT_ID=${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}
REGION=${REGION:-us-central1}
SERVICE_NAME=${SERVICE_NAME:-cloud-trader-staging}
ENVIRONMENT=${ENVIRONMENT:-staging}

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "PROJECT_ID is not set and no gcloud default project found." >&2
  exit 1
fi

echo "🚀 Deploying to staging environment: ${ENVIRONMENT}"
echo "Project: ${PROJECT_ID}"
echo "Service: ${SERVICE_NAME}"
echo "Region: ${REGION}"

# Build image
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}:${ENVIRONMENT}-latest"
echo "📦 Building container image: ${IMAGE}"
gcloud builds submit --tag "${IMAGE}" --timeout=1800s

# Deploy with staging-specific settings
echo "🚀 Deploying to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE}" \
  --platform managed \
  --region "${REGION}" \
  --allow-unauthenticated \
  --set-env-vars "ENABLE_PAPER_TRADING=true,ENVIRONMENT=${ENVIRONMENT}" \
  --set-secrets "ASTER_API_KEY=ASTER_API_KEY:latest,ASTER_SECRET_KEY=ASTER_SECRET_KEY:latest,TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest,TELEGRAM_CHAT_ID=TELEGRAM_CHAT_ID:latest" \
  --cpu-boost \
  --cpu-throttling \
  --startup-probe=httpGet.path=/healthz,httpGet.port=8080,timeoutSeconds=10,periodSeconds=30,failureThreshold=30 \
  --liveness-probe=httpGet.path=/healthz,httpGet.port=8080,timeoutSeconds=10,periodSeconds=10,initialDelaySeconds=5 \
  --memory=1Gi \
  --cpu=1 \
  --max-instances=3 \
  --concurrency=80 \
  --timeout=300

echo "✅ Staging deployment complete"
echo "Service URL: https://${SERVICE_NAME}-${PROJECT_ID}.${REGION}.run.app"

# Run smoke tests
echo "🧪 Running smoke tests..."
SERVICE_URL="https://${SERVICE_NAME}-${PROJECT_ID}.${REGION}.run.app"

# Test health endpoint
if curl -f -s "${SERVICE_URL}/healthz" > /dev/null; then
  echo "✅ Health check passed"
else
  echo "❌ Health check failed" >&2
  exit 1
fi

# Test root endpoint
if curl -f -s "${SERVICE_URL}/" > /dev/null; then
  echo "✅ Root endpoint check passed"
else
  echo "❌ Root endpoint check failed" >&2
  exit 1
fi

echo ""
echo "📊 Staging deployment successful!"
echo "Next steps:"
echo "1. Monitor logs: gcloud logging read 'resource.type=cloud_run_revision AND resource.labels.service_name=${SERVICE_NAME}' --limit 50"
echo "2. Run 24h soak test: ./run-soak-test.sh ${SERVICE_URL}"
echo "3. If tests pass, deploy to production: ./deploy-canary.sh"

