#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
REGION="${REGION:-us-central1}"
JOB_NAME="${JOB_NAME:-sapphire-strategy-ops-digest-6h}"
SCHEDULE="${SCHEDULE:-17 */6 * * *}"
TIME_ZONE="${TIME_ZONE:-America/Denver}"
SERVICE_NAME="${SERVICE_NAME:-sapphire-unified-jobs}"
TOKEN_SECRET="${TOKEN_SECRET:-SAPPHIRE_CONTROL_API_TOKEN}"
OIDC_SERVICE_ACCOUNT="${OIDC_SERVICE_ACCOUNT:-sapphire-main-sa@sapphire-479610.iam.gserviceaccount.com}"
DAYS="${DAYS:-7}"
MIN_INTERVAL_SEC="${MIN_INTERVAL_SEC:-21600}"
FORCE="${FORCE:-false}"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "ERROR: gcloud not installed" >&2
  exit 1
fi

SERVICE_URL="$(gcloud run services describe "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --format='value(status.url)')"
if [[ -z "${SERVICE_URL:-}" ]]; then
  echo "ERROR: could not resolve service URL for $SERVICE_NAME" >&2
  exit 1
fi

TARGET_URL="${TARGET_URL:-${SERVICE_URL%/}/jobs/platform/strategy-ops-digest}"
TOKEN="$(gcloud secrets versions access latest --secret="$TOKEN_SECRET" --project "$PROJECT_ID")"
if [[ -z "${TOKEN:-}" ]]; then
  echo "ERROR: secret ${TOKEN_SECRET} is empty" >&2
  exit 1
fi

BODY="{\"days\":${DAYS},\"min_interval_sec\":${MIN_INTERVAL_SEC},\"force\":${FORCE}}"
HEADERS="X-Sapphire-Token=${TOKEN},Content-Type=application/json"

set +e
gcloud scheduler jobs describe "$JOB_NAME" --location "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1
EXISTS=$?
set -e

if [[ "$EXISTS" -eq 0 ]]; then
  echo "Updating scheduler job: $JOB_NAME"
  gcloud scheduler jobs update http "$JOB_NAME" \
    --location "$REGION" \
    --project "$PROJECT_ID" \
    --schedule "$SCHEDULE" \
    --time-zone "$TIME_ZONE" \
    --uri "$TARGET_URL" \
    --http-method POST \
    --oidc-service-account-email "$OIDC_SERVICE_ACCOUNT" \
    --oidc-token-audience "$TARGET_URL" \
    --update-headers "$HEADERS" \
    --message-body "$BODY" >/dev/null
else
  echo "Creating scheduler job: $JOB_NAME"
  gcloud scheduler jobs create http "$JOB_NAME" \
    --location "$REGION" \
    --project "$PROJECT_ID" \
    --schedule "$SCHEDULE" \
    --time-zone "$TIME_ZONE" \
    --uri "$TARGET_URL" \
    --http-method POST \
    --oidc-service-account-email "$OIDC_SERVICE_ACCOUNT" \
    --oidc-token-audience "$TARGET_URL" \
    --headers "$HEADERS" \
    --message-body "$BODY" >/dev/null
fi

echo "Job configured: $JOB_NAME"
gcloud scheduler jobs describe "$JOB_NAME" --location "$REGION" --project "$PROJECT_ID" --format='table(name,state,schedule,timeZone,httpTarget.uri)'
