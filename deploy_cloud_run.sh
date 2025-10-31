#!/usr/bin/env bash

set -euo pipefail

PROJECT_ID=${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}
REGION=${REGION:-us-central1}
SERVICE_NAME=${SERVICE_NAME:-cloud-trader}

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "PROJECT_ID is not set and no gcloud default project found." >&2
  exit 1
fi

IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "📦 Building container image: ${IMAGE}"
gcloud builds submit --tag "${IMAGE}"

echo "🚀 Deploying to Cloud Run service '${SERVICE_NAME}' in region '${REGION}'"
gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE}" \
  --platform managed \
  --region "${REGION}" \
  --allow-unauthenticated \
  --set-secrets ASTER_API_KEY=ASTER_API_KEY:latest,ASTER_SECRET_KEY=ASTER_SECRET_KEY:latest

echo "✅ Deployment complete"

