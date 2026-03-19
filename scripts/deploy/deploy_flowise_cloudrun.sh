#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-sapphire-flowise-studio}"
IMAGE="${IMAGE:-flowiseai/flowise:3.0.6}"
ALLOW_UNAUTHENTICATED="${ALLOW_UNAUTHENTICATED:-false}"
CPU="${CPU:-1}"
MEMORY="${MEMORY:-2Gi}"
MIN_INSTANCES="${MIN_INSTANCES:-0}"
MAX_INSTANCES="${MAX_INSTANCES:-1}"
FLOWISE_USERNAME_SECRET="${FLOWISE_USERNAME_SECRET:-SAPPHIRE_FLOWISE_USERNAME}"
FLOWISE_PASSWORD_SECRET="${FLOWISE_PASSWORD_SECRET:-SAPPHIRE_FLOWISE_PASSWORD}"
FLOWISE_SECRETKEY_SECRET="${FLOWISE_SECRETKEY_SECRET:-SAPPHIRE_FLOWISE_SECRETKEY}"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "ERROR: gcloud not installed" >&2
  exit 1
fi

echo "Deploying ${SERVICE_NAME} to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --image "${IMAGE}" \
  --cpu "${CPU}" \
  --memory "${MEMORY}" \
  --min-instances "${MIN_INSTANCES}" \
  --max-instances "${MAX_INSTANCES}" \
  --set-env-vars "PORT=8080,LOG_LEVEL=info,DEBUG=false" \
  --set-secrets "FLOWISE_USERNAME=${FLOWISE_USERNAME_SECRET}:latest,FLOWISE_PASSWORD=${FLOWISE_PASSWORD_SECRET}:latest,FLOWISE_SECRETKEY_OVERWRITE=${FLOWISE_SECRETKEY_SECRET}:latest" \
  --quiet

if [[ "${ALLOW_UNAUTHENTICATED}" == "true" ]]; then
  gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --member="allUsers" \
    --role="roles/run.invoker" \
    --quiet
  echo "WARNING: unauthenticated access enabled for ${SERVICE_NAME}"
else
  echo "Keeping service private (authenticated invokers only)."
fi

echo "Service URL:"
gcloud run services describe "${SERVICE_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --format='value(status.url)'
