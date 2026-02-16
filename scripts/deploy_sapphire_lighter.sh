#!/usr/bin/env bash
# Build and deploy sapphire-lighter (Lighter venue bot) to Cloud Run.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
REGION="${REGION:-europe-west1}"
AR_REGION="${AR_REGION:-northamerica-northeast1}"
AR_REPO="${AR_REPO:-sapphire-repo}"
SERVICE_NAME="${SERVICE_NAME:-sapphire-lighter}"
IMAGE_NAME="${IMAGE_NAME:-sapphire-lighter}"
IMAGE_TAG="${IMAGE_TAG:-$(date -u +%Y%m%d%H%M)-lighter}"
PLATFORM="${PLATFORM:-linux/amd64}"

CPU="${CPU:-1}"
MEMORY="${MEMORY:-1Gi}"
CONCURRENCY="${CONCURRENCY:-160}"
TIMEOUT="${TIMEOUT:-300}"
MIN_INSTANCES="${MIN_INSTANCES:-1}"
MAX_INSTANCES="${MAX_INSTANCES:-10}"
STARTUP_CPU_BOOST="${STARTUP_CPU_BOOST:-true}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIGHTER_DIR="${ROOT_DIR}/services/bot-lighter"

IMAGE_URI="${AR_REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${IMAGE_NAME}:${IMAGE_TAG}"
IMAGE_LATEST="${AR_REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${IMAGE_NAME}:latest"

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
DEFAULT_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-${DEFAULT_SA}}"

echo "== Sapphire Lighter Bot Deploy =="
echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo "Service: ${SERVICE_NAME}"
echo "Image: ${IMAGE_URI}"
echo "Service Account: ${SERVICE_ACCOUNT}"
echo

if [[ "${SKIP_BUILD:-false}" != "true" ]]; then
  docker buildx build \
    --platform "${PLATFORM}" \
    -f "${LIGHTER_DIR}/Dockerfile" \
    -t "${IMAGE_URI}" \
    -t "${IMAGE_LATEST}" \
    --push "${LIGHTER_DIR}"
fi

gcloud run deploy "${SERVICE_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --image "${IMAGE_URI}" \
  --platform managed \
  --no-allow-unauthenticated \
  --service-account "${SERVICE_ACCOUNT}" \
  --memory "${MEMORY}" \
  --cpu "${CPU}" \
  --concurrency "${CONCURRENCY}" \
  --timeout "${TIMEOUT}" \
  --min-instances "${MIN_INSTANCES}" \
  --max-instances "${MAX_INSTANCES}" \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID}" \
  --set-env-vars "SERVICE_NAME=bot-lighter" \
  --set-env-vars "LOG_LEVEL=${LOG_LEVEL:-INFO}" \
  --set-env-vars "LIGHTER_TESTNET=${LIGHTER_TESTNET:-false}" \
  --update-secrets "LIGHTER_PRIV_KEY=LIGHTER_API_KEY_0:latest,LIGHTER_PUB_KEY=LIGHTER_API_PUBLIC_KEY_0:latest"

if [[ "${STARTUP_CPU_BOOST}" == "true" ]]; then
  gcloud run services update "${SERVICE_NAME}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --update-env-vars "PYTHONUNBUFFERED=1" \
    --update-annotations "run.googleapis.com/startup-cpu-boost=true" >/dev/null
fi

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
echo
echo "Service URL: ${SERVICE_URL}"
