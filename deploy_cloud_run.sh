#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: deploy_cloud_run.sh [options]

Options:
  --dry-run               Print the actions without executing them
  --skip-frontend-build   Do not run npm build for the dashboard bundle
  --skip-tests            Skip optional smoke tests before deployment
  --help                  Show this help message
EOF
}

DRY_RUN=false
SKIP_FRONTEND_BUILD=false
SKIP_TESTS=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      ;;
    --skip-frontend-build)
      SKIP_FRONTEND_BUILD=true
      ;;
    --skip-tests)
      SKIP_TESTS=true
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

run_cmd() {
  if $DRY_RUN; then
    printf '[dry-run] %s\n' "$*"
  else
    printf '+ %s\n' "$*"
    "$@"
  fi
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command '$1'. Please install it before running this script." >&2
    exit 1
  fi
}

require_cmd gcloud
require_cmd npm

if ! $SKIP_TESTS; then
  command -v pytest >/dev/null 2>&1 || echo "⚠️  pytest not found. Backend smoke tests will be skipped." >&2
fi

PROJECT_ID=${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}
REGION=${REGION:-us-central1}
REGIONS=${REGIONS:-${REGION}}
SERVICE_NAME=${SERVICE_NAME:-cloud-trader}

ENV_FILE=".env"
if [[ -f "${ENV_FILE}" ]]; then
  ORCHESTRATOR_FROM_ENV=$(grep -E '^ORCHESTRATOR_URL=' "${ENV_FILE}" | tail -1 | cut -d'=' -f2- || true)
  ENABLE_PAPER_FROM_ENV=$(grep -E '^ENABLE_PAPER_TRADING=' "${ENV_FILE}" | tail -1 | cut -d'=' -f2- || true)
  MOMENTUM_FROM_ENV=$(grep -E '^MOMENTUM_THRESHOLD=' "${ENV_FILE}" | tail -1 | cut -d'=' -f2- || true)
  NOTIONAL_FROM_ENV=$(grep -E '^NOTIONAL_FRACTION=' "${ENV_FILE}" | tail -1 | cut -d'=' -f2- || true)
  MCP_URL_FROM_ENV=$(grep -E '^MCP_URL=' "${ENV_FILE}" | tail -1 | cut -d'=' -f2- || true)
  MCP_SESSION_FROM_ENV=$(grep -E '^MCP_SESSION_ID=' "${ENV_FILE}" | tail -1 | cut -d'=' -f2- || true)
else
  ORCHESTRATOR_FROM_ENV=""
  ENABLE_PAPER_FROM_ENV=""
  MOMENTUM_FROM_ENV=""
  NOTIONAL_FROM_ENV=""
  MCP_URL_FROM_ENV=""
  MCP_SESSION_FROM_ENV=""
fi

ORCHESTRATOR_URL=${ORCHESTRATOR_URL:-${ORCHESTRATOR_FROM_ENV}}
ENABLE_PAPER_TRADING=${ENABLE_PAPER_TRADING:-${ENABLE_PAPER_FROM_ENV:-false}}
MOMENTUM_THRESHOLD=${MOMENTUM_THRESHOLD:-${MOMENTUM_FROM_ENV}}
NOTIONAL_FRACTION=${NOTIONAL_FRACTION:-${NOTIONAL_FROM_ENV}}
MCP_URL=${MCP_URL:-${MCP_URL_FROM_ENV}}
MCP_SESSION_ID=${MCP_SESSION_ID:-${MCP_SESSION_FROM_ENV}}

ENV_VARS="ENABLE_PAPER_TRADING=${ENABLE_PAPER_TRADING}"
if [[ -n "${ORCHESTRATOR_URL}" ]]; then
  ENV_VARS="${ENV_VARS},ORCHESTRATOR_URL=${ORCHESTRATOR_URL}"
fi
if [[ -n "${MOMENTUM_THRESHOLD}" ]]; then
  ENV_VARS="${ENV_VARS},MOMENTUM_THRESHOLD=${MOMENTUM_THRESHOLD}"
fi
if [[ -n "${NOTIONAL_FRACTION}" ]]; then
  ENV_VARS="${ENV_VARS},NOTIONAL_FRACTION=${NOTIONAL_FRACTION}"
fi
if [[ -n "${MCP_URL}" ]]; then
  ENV_VARS="${ENV_VARS},MCP_URL=${MCP_URL}"
fi
if [[ -n "${MCP_SESSION_ID}" ]]; then
  ENV_VARS="${ENV_VARS},MCP_SESSION_ID=${MCP_SESSION_ID}"
fi

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "PROJECT_ID is not set and no gcloud default project found." >&2
  exit 1
fi

IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

if ! $SKIP_FRONTEND_BUILD; then
  echo "🎨 Building dashboard frontend bundle"
  run_cmd npm --prefix cloud-trader-dashboard ci
  run_cmd npm --prefix cloud-trader-dashboard run build
else
  echo "⚠️  Skipping frontend build as requested"
fi

if [[ ! -d "cloud-trader-dashboard/dist" ]]; then
  echo "Frontend bundle not found at cloud-trader-dashboard/dist. Aborting." >&2
  exit 1
fi

if ! $SKIP_TESTS; then
  PYTHON_CMD="python"
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
  elif ! command -v python >/dev/null 2>&1; then
    echo "⚠️  No python interpreter found for smoke tests" >&2
    PYTHON_CMD=""
  fi

  if command -v pytest >/dev/null 2>&1; then
    echo "🧪 Running smoke tests (pytest)"
    if ! run_cmd pytest -q test_system.py; then
      echo "⚠️  Pytest smoke test failed, retrying with python" >&2
      if [[ -n "$PYTHON_CMD" ]]; then
        run_cmd "$PYTHON_CMD" test_system.py
      fi
    fi
  elif [[ -n "$PYTHON_CMD" ]]; then
    echo "🧪 Running smoke tests (python)"
    run_cmd "$PYTHON_CMD" test_system.py
  fi
fi

echo "📦 Building container image: ${IMAGE}"
run_cmd gcloud builds submit --tag "${IMAGE}"

REGION_LIST=()
IFS=',' read -ra REGION_LIST <<< "${REGIONS}"

for REGION in "${REGION_LIST[@]}"; do
  echo "🚀 Deploying to Cloud Run service '${SERVICE_NAME}' in region '${REGION}'"
  run_cmd gcloud run deploy "${SERVICE_NAME}" \
    --image "${IMAGE}" \
    --platform managed \
    --region "${REGION}" \
    --allow-unauthenticated \
    --set-env-vars "${ENV_VARS}" \
    --set-secrets ASTER_API_KEY=ASTER_API_KEY:latest,ASTER_SECRET_KEY=ASTER_SECRET_KEY:latest,TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest,TELEGRAM_CHAT_ID=TELEGRAM_CHAT_ID:latest \
    --cpu-boost \
    --cpu-throttling
done

if $DRY_RUN; then
  echo "✅ Dry run complete"
else
echo "✅ Deployment complete"
fi

