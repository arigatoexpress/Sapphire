#!/usr/bin/env bash
# Wire VirusTotal API key and policy settings into sapphire-alpha.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-sapphire-alpha}"
SECRET_NAME="${SECRET_NAME:-VIRUSTOTAL_API_KEY}"

VT_API_KEY="${VT_API_KEY:-}"
SAPPHIRE_VT_ENABLED="${SAPPHIRE_VT_ENABLED:-true}"
SAPPHIRE_VT_ENFORCEMENT_MODE="${SAPPHIRE_VT_ENFORCEMENT_MODE:-block_malicious}"
SAPPHIRE_VT_UPLOAD_IF_MISSING="${SAPPHIRE_VT_UPLOAD_IF_MISSING:-true}"
SAPPHIRE_VT_MAX_POLL_ATTEMPTS="${SAPPHIRE_VT_MAX_POLL_ATTEMPTS:-12}"
SAPPHIRE_VT_POLL_INTERVAL_SECONDS="${SAPPHIRE_VT_POLL_INTERVAL_SECONDS:-5}"

usage() {
  cat <<USAGE
Usage:
  VT_API_KEY='<vt-api-key>' ./scripts/wire_virustotal_security.sh

Optional env vars:
  PROJECT_ID, REGION, SERVICE_NAME
  SECRET_NAME (default: VIRUSTOTAL_API_KEY)
  SAPPHIRE_VT_ENABLED=true|false
  SAPPHIRE_VT_ENFORCEMENT_MODE=off|warn|block_malicious|block_suspicious
  SAPPHIRE_VT_UPLOAD_IF_MISSING=true|false
  SAPPHIRE_VT_MAX_POLL_ATTEMPTS=1..60
  SAPPHIRE_VT_POLL_INTERVAL_SECONDS=2..30
USAGE
}

ensure_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: missing required command: ${cmd}"
    exit 1
  fi
}

upsert_secret_version() {
  local secret_name="$1"
  local secret_value="$2"
  if [[ -z "$secret_value" ]]; then
    echo "ERROR: cannot write empty value for secret ${secret_name}"
    exit 1
  fi
  if ! gcloud secrets describe "$secret_name" --project "$PROJECT_ID" >/dev/null 2>&1; then
    gcloud secrets create "$secret_name" --project "$PROJECT_ID" --replication-policy=automatic >/dev/null
    echo "Created secret ${secret_name}"
  fi
  printf '%s' "$secret_value" | gcloud secrets versions add "$secret_name" \
    --project "$PROJECT_ID" \
    --data-file=- >/dev/null
  echo "Updated secret version for ${secret_name}"
}

ensure_cmd gcloud
ensure_cmd curl
ensure_cmd jq

if [[ -z "$VT_API_KEY" ]]; then
  echo "ERROR: VT_API_KEY is required."
  echo
  usage
  exit 2
fi

echo "== Wire VirusTotal Security =="
echo "Project: ${PROJECT_ID}"
echo "Service: ${SERVICE_NAME} (${REGION})"
echo "Secret: ${SECRET_NAME}"

upsert_secret_version "$SECRET_NAME" "$VT_API_KEY"

gcloud run services update "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --update-secrets "VIRUSTOTAL_API_KEY=${SECRET_NAME}:latest" \
  --update-env-vars "SAPPHIRE_VT_ENABLED=${SAPPHIRE_VT_ENABLED}" \
  --update-env-vars "SAPPHIRE_VT_ENFORCEMENT_MODE=${SAPPHIRE_VT_ENFORCEMENT_MODE}" \
  --update-env-vars "SAPPHIRE_VT_UPLOAD_IF_MISSING=${SAPPHIRE_VT_UPLOAD_IF_MISSING}" \
  --update-env-vars "SAPPHIRE_VT_MAX_POLL_ATTEMPTS=${SAPPHIRE_VT_MAX_POLL_ATTEMPTS}" \
  --update-env-vars "SAPPHIRE_VT_POLL_INTERVAL_SECONDS=${SAPPHIRE_VT_POLL_INTERVAL_SECONDS}" >/dev/null

ALPHA_URL="$(gcloud run services describe "$SERVICE_NAME" --project "$PROJECT_ID" --region "$REGION" --format='value(status.url)')"
echo "Alpha URL: ${ALPHA_URL}"

STATUS_JSON="$(curl -fsS "${ALPHA_URL}/api/v2/security/skills/status")"
echo "Security status: $(echo "$STATUS_JSON" | jq -c '{enabled,api_key_configured,enforcement_mode,upload_if_missing_default}')"
echo "VirusTotal security wiring complete."

