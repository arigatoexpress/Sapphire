#!/usr/bin/env bash

set -euo pipefail

# Canary deployment script for gradual traffic migration
# This script deploys a new revision and gradually shifts traffic

PROJECT_ID=${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}
REGION=${REGION:-us-central1}
SERVICE_NAME=${SERVICE_NAME:-cloud-trader}
CANARY_PERCENTAGE=${1:-10}  # Default 10% traffic to canary

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "PROJECT_ID is not set and no gcloud default project found." >&2
  exit 1
fi

if ! [[ "$CANARY_PERCENTAGE" =~ ^[0-9]+$ ]] || [ "$CANARY_PERCENTAGE" -lt 1 ] || [ "$CANARY_PERCENTAGE" -gt 100 ]; then
  echo "Invalid canary percentage: ${CANARY_PERCENTAGE}. Must be 1-100." >&2
  exit 1
fi

echo "🚀 Starting canary deployment"
echo "Service: ${SERVICE_NAME}"
echo "Canary traffic: ${CANARY_PERCENTAGE}%"
echo "Project: ${PROJECT_ID}"

# Get current revision
CURRENT_REVISION=$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" \
  --format="value(status.latestReadyRevisionName)" 2>/dev/null || echo "")

if [[ -z "${CURRENT_REVISION}" ]]; then
  echo "❌ Could not find current revision. Service may not exist." >&2
  exit 1
fi

echo "Current revision: ${CURRENT_REVISION}"

# Build new image
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}:canary-$(date +%s)"
echo "📦 Building new container image: ${IMAGE}"
gcloud builds submit --tag "${IMAGE}" --timeout=1800s

# Deploy new revision with no traffic
echo "🚀 Deploying new revision with no traffic..."
gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE}" \
  --platform managed \
  --region "${REGION}" \
  --no-traffic \
  --tag canary

# Get new revision name
NEW_REVISION=$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" \
  --format="value(status.latestReadyRevisionName)")

echo "New revision: ${NEW_REVISION}"

# Wait for new revision to be ready
echo "⏳ Waiting for new revision to be ready..."
sleep 10

# Test new revision directly
CANARY_URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" \
  --platform managed \
  --format="value(status.url)")

if [[ -n "${CANARY_URL}" ]]; then
  echo "🧪 Testing new revision..."
  if curl -f -s "${CANARY_URL}/healthz" -H "Host: ${NEW_REVISION}-${SERVICE_NAME}-${PROJECT_ID}.a.run.app" > /dev/null; then
    echo "✅ New revision health check passed"
  else
    echo "❌ New revision health check failed. Aborting canary deployment." >&2
    exit 1
  fi
fi

# Shift traffic gradually
STABLE_PERCENTAGE=$((100 - CANARY_PERCENTAGE))
echo "🔄 Shifting ${CANARY_PERCENTAGE}% traffic to canary revision..."
gcloud run services update-traffic "${SERVICE_NAME}" \
  --region="${REGION}" \
  --to-revisions="${NEW_REVISION}=${CANARY_PERCENTAGE},${CURRENT_REVISION}=${STABLE_PERCENTAGE}"

echo ""
echo "✅ Canary deployment initiated!"
echo "Traffic distribution:"
echo "  - Canary (${NEW_REVISION}): ${CANARY_PERCENTAGE}%"
echo "  - Stable (${CURRENT_REVISION}): ${STABLE_PERCENTAGE}%"
echo ""
echo "📊 Monitor metrics:"
echo "  gcloud run services describe ${SERVICE_NAME} --region=${REGION} --format='value(status.traffic)'"
echo ""
echo "⏰ Waiting 1 hour before checking if canary is healthy..."
echo "   If metrics look good, increase traffic gradually:"
echo "   ./deploy-canary.sh 25  # 25%"
echo "   ./deploy-canary.sh 50  # 50%"
echo "   ./deploy-canary.sh 100 # 100% (full rollout)"
echo ""
echo "🔄 To rollback immediately:"
echo "   gcloud run services update-traffic ${SERVICE_NAME} --region=${REGION} --to-revisions=${CURRENT_REVISION}=100"

