#!/usr/bin/env bash
# Create/update true external Moltbook scout bridge secrets and attach them to sapphire-alpha.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-sapphire-alpha}"

REGISTER_SECRET="${REGISTER_SECRET:-SAPPHIRE_SCOUT_EXTERNAL_REGISTER_URL}"
POST_SECRET="${POST_SECRET:-SAPPHIRE_SCOUT_EXTERNAL_POST_URL}"
TOKEN_SECRET="${TOKEN_SECRET:-SAPPHIRE_SCOUT_EXTERNAL_API_TOKEN}"

MOLTBOOK_REGISTER_URL="${MOLTBOOK_REGISTER_URL:-}"
MOLTBOOK_POST_URL="${MOLTBOOK_POST_URL:-}"
MOLTBOOK_API_TOKEN="${MOLTBOOK_API_TOKEN:-}"

TEST_SCOUT_USERNAME="${TEST_SCOUT_USERNAME:-sapphire_scout}"
TEST_SCOUT_DISPLAY_NAME="${TEST_SCOUT_DISPLAY_NAME:-Sapphire Scout}"
RUN_SMOKE_TESTS="${RUN_SMOKE_TESTS:-true}"

usage() {
  cat <<USAGE
Usage:
  MOLTBOOK_REGISTER_URL=<url> \
  MOLTBOOK_POST_URL=<url> \
  MOLTBOOK_API_TOKEN=<token> \
  ./scripts/wire_moltbook_bridge.sh

Optional env vars:
  PROJECT_ID, REGION, SERVICE_NAME
  REGISTER_SECRET, POST_SECRET, TOKEN_SECRET
  TEST_SCOUT_USERNAME, TEST_SCOUT_DISPLAY_NAME
  RUN_SMOKE_TESTS=true|false
USAGE
}

ensure_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: required command missing: $cmd"
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
    echo "Creating secret: ${secret_name}"
    gcloud secrets create "$secret_name" --project "$PROJECT_ID" --replication-policy=automatic >/dev/null
  fi

  printf '%s' "$secret_value" | gcloud secrets versions add "$secret_name" \
    --project "$PROJECT_ID" \
    --data-file=- >/dev/null
  echo "Updated secret version: ${secret_name}"
}

ensure_cmd gcloud
ensure_cmd jq
ensure_cmd curl

if [[ -z "$MOLTBOOK_REGISTER_URL" || -z "$MOLTBOOK_POST_URL" || -z "$MOLTBOOK_API_TOKEN" ]]; then
  echo "Moltbook bridge is not ready: missing one or more required values."
  echo "Required: MOLTBOOK_REGISTER_URL, MOLTBOOK_POST_URL, MOLTBOOK_API_TOKEN"
  echo
  usage
  exit 2
fi

echo "== Wiring Moltbook Scout Bridge =="
echo "Project: ${PROJECT_ID}"
echo "Service: ${SERVICE_NAME} (${REGION})"
echo "Register URL secret: ${REGISTER_SECRET}"
echo "Post URL secret: ${POST_SECRET}"
echo "Token secret: ${TOKEN_SECRET}"
echo

upsert_secret_version "$REGISTER_SECRET" "$MOLTBOOK_REGISTER_URL"
upsert_secret_version "$POST_SECRET" "$MOLTBOOK_POST_URL"
upsert_secret_version "$TOKEN_SECRET" "$MOLTBOOK_API_TOKEN"

SECRET_BINDINGS="SAPPHIRE_SCOUT_EXTERNAL_REGISTER_URL=${REGISTER_SECRET}:latest,SAPPHIRE_SCOUT_EXTERNAL_POST_URL=${POST_SECRET}:latest,SAPPHIRE_SCOUT_EXTERNAL_API_TOKEN=${TOKEN_SECRET}:latest"

echo "Applying Cloud Run secret bindings..."
gcloud run services update "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --update-secrets "$SECRET_BINDINGS" >/dev/null

echo "Secret bindings applied."

ALPHA_URL="$(gcloud run services describe "$SERVICE_NAME" --project "$PROJECT_ID" --region "$REGION" --format='value(status.url)')"
echo "Alpha URL: ${ALPHA_URL}"

STATUS_JSON="$(curl -fsS "${ALPHA_URL}/api/v2/forum/scout/status")"
DISPATCH_MODE="$(echo "$STATUS_JSON" | jq -r '.external_bridge.dispatch_mode // "unknown"')"

echo "Scout dispatch mode: ${DISPATCH_MODE}"

if [[ "$RUN_SMOKE_TESTS" == "true" ]]; then
  echo
  echo "Running scout bridge smoke tests..."

  REGISTER_PAYLOAD="$(jq -nc --arg u "$TEST_SCOUT_USERNAME" --arg d "$TEST_SCOUT_DISPLAY_NAME" '{username:$u,display_name:$d,bio:"Least-privilege external scout account."}')"
  REGISTER_RESPONSE="$(curl -fsS -X POST "${ALPHA_URL}/api/v2/forum/scout/register" -H 'Content-Type: application/json' -d "$REGISTER_PAYLOAD")"
  echo "Register response: $(echo "$REGISTER_RESPONSE" | jq -c '{ok,dispatch:.dispatch,registration:.registration}')"

  TOPIC_ID="$(curl -fsS "${ALPHA_URL}/api/v2/forum/topics?lane=external&limit=1" | jq -r '.topics[0].topic_id // ""')"
  if [[ -z "$TOPIC_ID" ]]; then
    TOPIC_ID="TOPIC-00003"
  fi
  PUBLISH_PAYLOAD="$(jq -nc --arg t "$TOPIC_ID" '{topic_id:$t,body:"Scout smoke test note via true external bridge.",author:"SAPPHIRE_SCOUT",kind:"note"}')"
  PUBLISH_RESPONSE="$(curl -fsS -X POST "${ALPHA_URL}/api/v2/forum/scout/publish" -H 'Content-Type: application/json' -d "$PUBLISH_PAYLOAD")"
  echo "Publish response: $(echo "$PUBLISH_RESPONSE" | jq -c '{ok,topic_id,dispatch:.dispatch}')"
fi

echo

echo "Moltbook external bridge wiring complete."
