#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
"${ROOT_DIR}/scripts/check_source_of_truth.sh"

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
REGION="${REGION:-us-central1}"
AR_REGION="${AR_REGION:-northamerica-northeast1}"
AR_REPO="${AR_REPO:-sapphire-repo}"
SERVICE_NAME="${SERVICE_NAME:-sapphire-scout-sandbox}"
IMAGE_NAME="${IMAGE_NAME:-sapphire-scout-sandbox}"
IMAGE_TAG="${IMAGE_TAG:-$(date -u +%Y%m%d%H%M)-sandbox}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-sapphire-main-sa@${PROJECT_ID}.iam.gserviceaccount.com}"
BUILD_SERVICE_ACCOUNT="${BUILD_SERVICE_ACCOUNT:-sapphirev3@${PROJECT_ID}.iam.gserviceaccount.com}"

SCOUT_SANDBOX_TOKEN_SECRET="${SCOUT_SANDBOX_TOKEN_SECRET:-SAPPHIRE_SCOUT_SANDBOX_TOKEN}"
SCOUT_SANDBOX_REGISTER_URL_SECRET="${SCOUT_SANDBOX_REGISTER_URL_SECRET:-SAPPHIRE_SCOUT_EXTERNAL_REGISTER_URL}"
SCOUT_SANDBOX_POST_URL_SECRET="${SCOUT_SANDBOX_POST_URL_SECRET:-SAPPHIRE_SCOUT_EXTERNAL_POST_URL}"
SCOUT_SANDBOX_EXTERNAL_API_TOKEN_SECRET="${SCOUT_SANDBOX_EXTERNAL_API_TOKEN_SECRET:-SAPPHIRE_SCOUT_EXTERNAL_API_TOKEN}"

SCOUT_SANDBOX_DRY_RUN="${SCOUT_SANDBOX_DRY_RUN:-false}"
SCOUT_SANDBOX_AUTO_VERIFY_ENABLED="${SCOUT_SANDBOX_AUTO_VERIFY_ENABLED:-true}"
SCOUT_SANDBOX_ALLOWED_HOSTS="${SCOUT_SANDBOX_ALLOWED_HOSTS:-moltbook.com,www.moltbook.com,molthub.com,www.molthub.com}"
ENV_DELIM="^@^"

IMAGE_URI="${AR_REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${IMAGE_NAME}:${IMAGE_TAG}"

has_secret() {
  local name="$1"
  gcloud secrets describe "${name}" --project "${PROJECT_ID}" >/dev/null 2>&1
}

echo "== Deploy SCOUT sandbox =="
echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo "Image: ${IMAGE_URI}"

gcloud builds submit \
  --project "${PROJECT_ID}" \
  --service-account "projects/${PROJECT_ID}/serviceAccounts/${BUILD_SERVICE_ACCOUNT}" \
  --config "${ROOT_DIR}/cloudbuild-scout-sandbox.yaml" \
  --substitutions "_IMAGE=${IMAGE_URI}" \
  "${ROOT_DIR}"

gcloud run deploy "${SERVICE_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --image "${IMAGE_URI}" \
  --platform managed \
  --allow-unauthenticated \
  --service-account "${SERVICE_ACCOUNT}" \
  --memory "512Mi" \
  --cpu "1" \
  --concurrency "40" \
  --timeout "120" \
  --port "8080" \
  --update-env-vars "${ENV_DELIM}GCP_PROJECT_ID=${PROJECT_ID}@SCOUT_SANDBOX_DRY_RUN=${SCOUT_SANDBOX_DRY_RUN}@SCOUT_SANDBOX_AUTO_VERIFY_ENABLED=${SCOUT_SANDBOX_AUTO_VERIFY_ENABLED}@SCOUT_SANDBOX_ALLOWED_HOSTS=${SCOUT_SANDBOX_ALLOWED_HOSTS}"

SECRET_MAPPINGS=()
if has_secret "${SCOUT_SANDBOX_TOKEN_SECRET}"; then
  SECRET_MAPPINGS+=("SCOUT_SANDBOX_TOKEN=${SCOUT_SANDBOX_TOKEN_SECRET}:latest")
fi
if has_secret "${SCOUT_SANDBOX_REGISTER_URL_SECRET}"; then
  SECRET_MAPPINGS+=("SCOUT_SANDBOX_REGISTER_URL=${SCOUT_SANDBOX_REGISTER_URL_SECRET}:latest")
fi
if has_secret "${SCOUT_SANDBOX_POST_URL_SECRET}"; then
  SECRET_MAPPINGS+=("SCOUT_SANDBOX_POST_URL=${SCOUT_SANDBOX_POST_URL_SECRET}:latest")
fi
if has_secret "${SCOUT_SANDBOX_EXTERNAL_API_TOKEN_SECRET}"; then
  SECRET_MAPPINGS+=("SCOUT_SANDBOX_EXTERNAL_API_TOKEN=${SCOUT_SANDBOX_EXTERNAL_API_TOKEN_SECRET}:latest")
fi

if [[ "${#SECRET_MAPPINGS[@]}" -gt 0 ]]; then
  SECRET_ARG="$(IFS=,; echo "${SECRET_MAPPINGS[*]}")"
  gcloud run services update "${SERVICE_NAME}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --update-secrets "${SECRET_ARG}" >/dev/null
  echo "Applied secret bindings: ${SECRET_ARG}"
else
  echo "No sandbox secrets found. Service is running but bridge dispatch will be limited."
fi

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
echo "Service URL: ${SERVICE_URL}"
echo "Health:" && curl -fsS "${SERVICE_URL}/health" && echo
