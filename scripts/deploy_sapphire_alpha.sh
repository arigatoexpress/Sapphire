#!/usr/bin/env bash
# Build and deploy sapphire-alpha control plane.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
REGION="${REGION:-us-central1}"
AR_REGION="${AR_REGION:-northamerica-northeast1}"
AR_REPO="${AR_REPO:-sapphire-repo}"
SERVICE_NAME="${SERVICE_NAME:-sapphire-alpha}"
IMAGE_NAME="${IMAGE_NAME:-sapphire-alpha}"
IMAGE_TAG="${IMAGE_TAG:-$(date -u +%Y%m%d%H%M)-alpha}"
PLATFORM="${PLATFORM:-linux/amd64}"
CPU="${CPU:-1}"
MEMORY="${MEMORY:-1Gi}"
CONCURRENCY="${CONCURRENCY:-80}"
TIMEOUT="${TIMEOUT:-300}"
PORT="${PORT:-8080}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-267358751314-compute@developer.gserviceaccount.com}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ALPHA_DIR="${ROOT_DIR}/services/alpha-engine"
IMAGE_URI="${AR_REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${IMAGE_NAME}:${IMAGE_TAG}"
IMAGE_LATEST="${AR_REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${IMAGE_NAME}:latest"

echo "== Sapphire Alpha Deploy =="
echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo "Image: ${IMAGE_URI}"
echo

docker buildx build \
  --platform "${PLATFORM}" \
  -t "${IMAGE_URI}" \
  -t "${IMAGE_LATEST}" \
  --push "${ALPHA_DIR}"

gcloud run deploy "${SERVICE_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --image "${IMAGE_URI}" \
  --platform managed \
  --allow-unauthenticated \
  --service-account "${SERVICE_ACCOUNT}" \
  --memory "${MEMORY}" \
  --cpu "${CPU}" \
  --concurrency "${CONCURRENCY}" \
  --timeout "${TIMEOUT}" \
  --port "${PORT}"

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
echo
echo "Service URL: ${SERVICE_URL}"
echo "Health:"
curl -fsS "${SERVICE_URL}/health" || true
echo
echo "Deployed image: ${IMAGE_URI}"
