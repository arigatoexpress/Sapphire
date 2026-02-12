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
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-sapphire-main-sa@${PROJECT_ID}.iam.gserviceaccount.com}"
FULL_AUTONOMY_ENABLED="${FULL_AUTONOMY_ENABLED:-true}"
AUTONOMY_ALLOW_CODE_CHANGES="${AUTONOMY_ALLOW_CODE_CHANGES:-true}"
AUTONOMY_ALLOW_GCLOUD_CHANGES="${AUTONOMY_ALLOW_GCLOUD_CHANGES:-true}"
AUTONOMY_DRY_RUN="${AUTONOMY_DRY_RUN:-false}"
AUTONOMY_REQUIRE_OWNER_APPROVAL="${AUTONOMY_REQUIRE_OWNER_APPROVAL:-false}"
AUTONOMY_LOOP_SECONDS="${AUTONOMY_LOOP_SECONDS:-900}"
AUTONOMY_MIN_DISPATCH_INTERVAL_SECONDS="${AUTONOMY_MIN_DISPATCH_INTERVAL_SECONDS:-600}"
GEMINI_FLASH_MIN_INTERVAL_SECONDS="${GEMINI_FLASH_MIN_INTERVAL_SECONDS:-1800}"
TRADINGVIEW_EXECUTION_ENABLED="${TRADINGVIEW_EXECUTION_ENABLED:-true}"
TRADINGVIEW_DEFAULT_QUANTITY="${TRADINGVIEW_DEFAULT_QUANTITY:-0.02}"
SAPPHIRE_ALLOWED_REPOS="${SAPPHIRE_ALLOWED_REPOS:-arigatoexpress/Sapphire;Sapphire}"
SAPPHIRE_ALLOWED_GCP_PROJECTS="${SAPPHIRE_ALLOWED_GCP_PROJECTS:-${PROJECT_ID}}"
SAPPHIRE_BLOCKED_SCOPE_TERMS="${SAPPHIRE_BLOCKED_SCOPE_TERMS:-sapphireai;sapphire-inc;sapphire_inc}"

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

gcloud run services update "${SERVICE_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --update-env-vars "SAPPHIRE_FULL_AUTONOMY_ENABLED=${FULL_AUTONOMY_ENABLED}" \
  --update-env-vars "SAPPHIRE_AUTONOMY_ALLOW_CODE_CHANGES=${AUTONOMY_ALLOW_CODE_CHANGES}" \
  --update-env-vars "SAPPHIRE_AUTONOMY_ALLOW_GCLOUD_CHANGES=${AUTONOMY_ALLOW_GCLOUD_CHANGES}" \
  --update-env-vars "SAPPHIRE_AUTONOMY_DRY_RUN=${AUTONOMY_DRY_RUN}" \
  --update-env-vars "SAPPHIRE_AUTONOMY_REQUIRE_OWNER_APPROVAL=${AUTONOMY_REQUIRE_OWNER_APPROVAL}" \
  --update-env-vars "SAPPHIRE_AUTONOMY_LOOP_SECONDS=${AUTONOMY_LOOP_SECONDS}" \
  --update-env-vars "SAPPHIRE_AUTONOMY_MIN_DISPATCH_INTERVAL_SECONDS=${AUTONOMY_MIN_DISPATCH_INTERVAL_SECONDS}" \
  --update-env-vars "GEMINI_FLASH_MIN_INTERVAL_SECONDS=${GEMINI_FLASH_MIN_INTERVAL_SECONDS}" \
  --update-env-vars "TRADINGVIEW_EXECUTION_ENABLED=${TRADINGVIEW_EXECUTION_ENABLED}" \
  --update-env-vars "TRADINGVIEW_DEFAULT_QUANTITY=${TRADINGVIEW_DEFAULT_QUANTITY}" \
  --update-env-vars "SAPPHIRE_ALLOWED_REPOS=${SAPPHIRE_ALLOWED_REPOS}" \
  --update-env-vars "SAPPHIRE_ALLOWED_GCP_PROJECTS=${SAPPHIRE_ALLOWED_GCP_PROJECTS}" \
  --update-env-vars "SAPPHIRE_BLOCKED_SCOPE_TERMS=${SAPPHIRE_BLOCKED_SCOPE_TERMS}" \
  >/dev/null

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
echo
echo "Service URL: ${SERVICE_URL}"
echo "Health:"
curl -fsS "${SERVICE_URL}/health" || true
echo
echo "Deployed image: ${IMAGE_URI}"
