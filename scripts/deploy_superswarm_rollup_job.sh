#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
REGION="${REGION:-us-central1}"
JOB_NAME="${JOB_NAME:-sapphire-superswarm-rollup-hourly}"
SCHEDULE="${SCHEDULE:-12 * * * *}"
TIME_ZONE="${TIME_ZONE:-America/Denver}"
DOMAIN="${DOMAIN:-https://sapphirealpha.xyz}"
TARGET_URL="${TARGET_URL:-${DOMAIN%/}/jobs/superswarm/hourly-rollup}"
TOKEN_SECRET="${TOKEN_SECRET:-SAPPHIRE_CONTROL_API_TOKEN}"
HOURS="${HOURS:-24}"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "ERROR: gcloud not installed" >&2
  exit 1
fi

TOKEN="$(gcloud secrets versions access latest --secret="$TOKEN_SECRET" --project "$PROJECT_ID")"
if [[ -z "${TOKEN:-}" ]]; then
  echo "ERROR: secret ${TOKEN_SECRET} is empty" >&2
  exit 1
fi

BODY="{\"hours\":${HOURS}}"
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
    --headers "$HEADERS" \
    --message-body "$BODY"
else
  echo "Creating scheduler job: $JOB_NAME"
  gcloud scheduler jobs create http "$JOB_NAME" \
    --location "$REGION" \
    --project "$PROJECT_ID" \
    --schedule "$SCHEDULE" \
    --time-zone "$TIME_ZONE" \
    --uri "$TARGET_URL" \
    --http-method POST \
    --headers "$HEADERS" \
    --message-body "$BODY"
fi

echo "Job configured: $JOB_NAME"
gcloud scheduler jobs describe "$JOB_NAME" --location "$REGION" --project "$PROJECT_ID" --format='table(name,state,schedule,timeZone,httpTarget.uri)'
