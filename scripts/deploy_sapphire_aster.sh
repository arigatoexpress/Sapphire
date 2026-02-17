#!/usr/bin/env bash
# Build and deploy sapphire-aster (Aster venue bot) to Cloud Run.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
REGION="${REGION:-us-central1}"
AR_REGION="${AR_REGION:-northamerica-northeast1}"
AR_REPO="${AR_REPO:-sapphire-repo}"
SERVICE_NAME="${SERVICE_NAME:-sapphire-aster}"
IMAGE_NAME="${IMAGE_NAME:-sapphire-aster}"
IMAGE_TAG="${IMAGE_TAG:-$(date -u +%Y%m%d%H%M)-aster}"
PLATFORM="${PLATFORM:-linux/amd64}"

CPU="${CPU:-1}"
MEMORY="${MEMORY:-1Gi}"
CONCURRENCY="${CONCURRENCY:-160}"
TIMEOUT="${TIMEOUT:-300}"
MIN_INSTANCES="${MIN_INSTANCES:-1}"
MAX_INSTANCES="${MAX_INSTANCES:-5}"
STARTUP_CPU_BOOST="${STARTUP_CPU_BOOST:-true}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASTER_DIR="${ROOT_DIR}/services/bot-aster"

IMAGE_URI="${AR_REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${IMAGE_NAME}:${IMAGE_TAG}"
IMAGE_LATEST="${AR_REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${IMAGE_NAME}:latest"

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
DEFAULT_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-${DEFAULT_SA}}"

echo "== Sapphire Aster Bot Deploy =="
echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo "Service: ${SERVICE_NAME}"
echo "Image: ${IMAGE_URI}"
echo "Service Account: ${SERVICE_ACCOUNT}"
echo

if [[ "${SKIP_BUILD:-false}" != "true" ]]; then
  docker buildx build \
    --platform "${PLATFORM}" \
    -f "${ASTER_DIR}/Dockerfile" \
    -t "${IMAGE_URI}" \
    -t "${IMAGE_LATEST}" \
    --push "${ASTER_DIR}"
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
  --set-env-vars "SERVICE_NAME=bot-aster" \
  --set-env-vars "LOG_LEVEL=${LOG_LEVEL:-INFO}" \
  --update-secrets "ASTER_API_KEY=ASTER_API_KEY:latest,ASTER_SECRET_KEY=ASTER_SECRET_KEY:latest"

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
