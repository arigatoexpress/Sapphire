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
BUILD_SERVICE_ACCOUNT="${BUILD_SERVICE_ACCOUNT:-sapphirev3@${PROJECT_ID}.iam.gserviceaccount.com}"

CPU="${CPU:-1}"
MEMORY="${MEMORY:-1Gi}"
CONCURRENCY="${CONCURRENCY:-160}"
TIMEOUT="${TIMEOUT:-300}"
MIN_INSTANCES="${MIN_INSTANCES:-1}"
MAX_INSTANCES="${MAX_INSTANCES:-10}"
STARTUP_CPU_BOOST="${STARTUP_CPU_BOOST:-true}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIGHTER_DIR="${ROOT_DIR}/services/bot-lighter"
LIGHTER_ACCOUNT_INDEX="${LIGHTER_ACCOUNT_INDEX:-699444}"
LIGHTER_API_KEY_INDEX="${LIGHTER_API_KEY_INDEX:-0}"
LIGHTER_L1_ADDRESS="${LIGHTER_L1_ADDRESS:-0xAf72Ae447aD3dcdcDfBAA01bB9c7b3C37a031aAf}"
LIGHTER_ACCOUNT_DISCOVERY_HINTS="${LIGHTER_ACCOUNT_DISCOVERY_HINTS:-699444}"
LIGHTER_ACCOUNT_DISCOVERY_SCAN_LIMIT="${LIGHTER_ACCOUNT_DISCOVERY_SCAN_LIMIT:-64}"

IMAGE_URI="${AR_REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${IMAGE_NAME}:${IMAGE_TAG}"
IMAGE_LATEST="${AR_REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${IMAGE_NAME}:latest"

DEFAULT_SA="sapphire-main-sa@${PROJECT_ID}.iam.gserviceaccount.com"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-${DEFAULT_SA}}"

echo "== Sapphire Lighter Bot Deploy =="
echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo "Service: ${SERVICE_NAME}"
echo "Image: ${IMAGE_URI}"
echo "Service Account: ${SERVICE_ACCOUNT}"
echo

if [[ "${SKIP_BUILD:-false}" != "true" ]]; then
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    docker buildx build \
      --platform "${PLATFORM}" \
      -f "${LIGHTER_DIR}/Dockerfile" \
      -t "${IMAGE_URI}" \
      -t "${IMAGE_LATEST}" \
      --push "${ROOT_DIR}"
  else
    echo "Docker daemon unavailable; using Cloud Build fallback."
    gcloud builds submit \
      --project "${PROJECT_ID}" \
      --service-account "projects/${PROJECT_ID}/serviceAccounts/${BUILD_SERVICE_ACCOUNT}" \
      --default-buckets-behavior=regional-user-owned-bucket \
      --config "${ROOT_DIR}/cloudbuild-bot-lighter.yaml" \
      --substitutions "_IMAGE=${IMAGE_URI}" \
      "${ROOT_DIR}"
    gcloud artifacts docker tags add "${IMAGE_URI}" "${IMAGE_LATEST}" --project "${PROJECT_ID}" >/dev/null
  fi
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
  --update-env-vars "GCP_PROJECT_ID=${PROJECT_ID}" \
  --update-env-vars "SERVICE_NAME=bot-lighter" \
  --update-env-vars "LOG_LEVEL=${LOG_LEVEL:-INFO}" \
  --update-env-vars "LIGHTER_TESTNET=${LIGHTER_TESTNET:-false}" \
  --update-env-vars "LIGHTER_ACCOUNT_INDEX=${LIGHTER_ACCOUNT_INDEX}" \
  --update-env-vars "LIGHTER_API_KEY_INDEX=${LIGHTER_API_KEY_INDEX}" \
  --update-env-vars "LIGHTER_L1_ADDRESS=${LIGHTER_L1_ADDRESS}" \
  --update-env-vars "LIGHTER_ACCOUNT_DISCOVERY_HINTS=${LIGHTER_ACCOUNT_DISCOVERY_HINTS}" \
  --update-env-vars "LIGHTER_ACCOUNT_DISCOVERY_SCAN_LIMIT=${LIGHTER_ACCOUNT_DISCOVERY_SCAN_LIMIT}" \
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
