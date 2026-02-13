#!/usr/bin/env bash
# Build and deploy sapphire-web to Cloud Run service sapphirebook-web.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
REGION="${REGION:-us-central1}"
AR_REGION="${AR_REGION:-northamerica-northeast1}"
AR_REPO="${AR_REPO:-sapphire-repo}"
SERVICE_NAME="${SERVICE_NAME:-sapphirebook-web}"
IMAGE_NAME="${IMAGE_NAME:-sapphirebook-web}"
IMAGE_TAG="${IMAGE_TAG:-$(date -u +%Y%m%d%H%M)-web}"
PLATFORM="${PLATFORM:-linux/amd64}"
MEMORY="${MEMORY:-512Mi}"
CPU="${CPU:-1}"
MAX_INSTANCES="${MAX_INSTANCES:-20}"
MIN_INSTANCES="${MIN_INSTANCES:-0}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_DIR="${ROOT_DIR}/sapphire-web"
IMAGE_URI="${AR_REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${IMAGE_NAME}:${IMAGE_TAG}"
IMAGE_LATEST="${AR_REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${IMAGE_NAME}:latest"
GIT_SHA="$(git -C "${ROOT_DIR}" rev-parse --short HEAD 2>/dev/null || echo unknown)"
BUILD_ID="${BUILD_ID:-web-${IMAGE_TAG}-${GIT_SHA}}"
BUILD_TIME_UTC="${BUILD_TIME_UTC:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
SKIP_NPM_INSTALL="${SKIP_NPM_INSTALL:-0}"
SKIP_LOCAL_BUILD="${SKIP_LOCAL_BUILD:-0}"

echo "== Sapphirebook Web Deploy =="
echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo "Image: ${IMAGE_URI}"
echo "Build ID: ${BUILD_ID}"
echo "Build time (UTC): ${BUILD_TIME_UTC}"
echo

cd "${WEB_DIR}"
if [[ "${SKIP_NPM_INSTALL}" != "1" ]]; then
  npm ci --no-audit --no-fund
fi

if [[ "${SKIP_LOCAL_BUILD}" != "1" ]]; then
  VITE_BUILD_ID="${BUILD_ID}" VITE_BUILD_TIME_UTC="${BUILD_TIME_UTC}" npm run build
fi

docker buildx build \
  --platform "${PLATFORM}" \
  -t "${IMAGE_URI}" \
  -t "${IMAGE_LATEST}" \
  --build-arg "VITE_BUILD_ID=${BUILD_ID}" \
  --build-arg "VITE_BUILD_TIME_UTC=${BUILD_TIME_UTC}" \
  -f Dockerfile \
  --push .

gcloud run deploy "${SERVICE_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --image "${IMAGE_URI}" \
  --platform managed \
  --allow-unauthenticated \
  --memory "${MEMORY}" \
  --cpu "${CPU}" \
  --min-instances "${MIN_INSTANCES}" \
  --max-instances "${MAX_INSTANCES}" \
  --port 8080

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
echo
echo "Service URL: ${SERVICE_URL}"
echo "Health:"
curl -fsS "${SERVICE_URL}/health" || true
echo "Index cache headers:"
curl -fsSI "${SERVICE_URL}/index.html" | grep -iE 'cache-control|pragma|expires' || true
echo
echo "Deployed image: ${IMAGE_URI}"
