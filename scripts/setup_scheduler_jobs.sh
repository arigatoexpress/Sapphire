#!/usr/bin/env bash
# Configure Sapphire Cloud Scheduler jobs for health checks and control heartbeats.
#
# This script is idempotent: existing jobs are updated, missing jobs are created.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
LOCATION="${LOCATION:-us-central1}"

ALPHA_URL="${ALPHA_URL:-https://sapphire-alpha-267358751314.us-central1.run.app}"
ASTER_URL="${ASTER_URL:-https://sapphire-aster-267358751314.us-central1.run.app}"
LIGHTER_URL="${LIGHTER_URL:-https://sapphire-lighter-267358751314.europe-west1.run.app}"
GATEWAY_URL="${GATEWAY_URL:-https://sapphire-gateway-267358751314.us-central1.run.app}"
SCHEDULER_SA="${SCHEDULER_SA:-sapphire-main-sa@${PROJECT_ID}.iam.gserviceaccount.com}"

CHAT_ID="$(gcloud secrets versions access latest --secret=TELEGRAM_CHAT_ID --project "${PROJECT_ID}")"
WEBHOOK_SECRET="$(
  gcloud secrets versions access latest \
    --secret=SAPPHIRE_TELEGRAM_WEBHOOK_SECRET \
    --project "${PROJECT_ID}"
)"

STATUS_BODY="$(cat <<JSON
{"update_id":900000001,"message":{"chat":{"id":"${CHAT_ID}"},"text":"/status"}}
JSON
)"

HEARTBEAT_BODY="$(cat <<JSON
{"update_id":900000002,"message":{"chat":{"id":"${CHAT_ID}"},"text":"/heartbeat"}}
JSON
)"

STRATEGY_GATE_BODY="$(cat <<JSON
{"update_id":900000003,"message":{"chat":{"id":"${CHAT_ID}"},"text":"/promotion"}}
JSON
)"

upsert_http_job() {
  local name="$1"
  local schedule="$2"
  local uri="$3"
  local method="$4"
  local headers="$5"
  local body="$6"

  if gcloud scheduler jobs describe "${name}" --project "${PROJECT_ID}" --location "${LOCATION}" >/dev/null 2>&1; then
    if [[ "${method}" == "POST" ]]; then
      gcloud scheduler jobs update http "${name}" \
        --project "${PROJECT_ID}" \
        --location "${LOCATION}" \
        --schedule "${schedule}" \
        --time-zone "Etc/UTC" \
        --uri "${uri}" \
        --http-method POST \
        --update-headers "${headers}" \
        --message-body "${body}" >/dev/null
    else
      gcloud scheduler jobs update http "${name}" \
        --project "${PROJECT_ID}" \
        --location "${LOCATION}" \
        --schedule "${schedule}" \
        --time-zone "Etc/UTC" \
        --uri "${uri}" \
        --http-method GET >/dev/null
    fi
    echo "updated ${name}"
  else
    if [[ "${method}" == "POST" ]]; then
      gcloud scheduler jobs create http "${name}" \
        --project "${PROJECT_ID}" \
        --location "${LOCATION}" \
        --schedule "${schedule}" \
        --time-zone "Etc/UTC" \
        --uri "${uri}" \
        --http-method POST \
        --headers "${headers}" \
        --message-body "${body}" >/dev/null
    else
      gcloud scheduler jobs create http "${name}" \
        --project "${PROJECT_ID}" \
        --location "${LOCATION}" \
        --schedule "${schedule}" \
        --time-zone "Etc/UTC" \
        --uri "${uri}" \
        --http-method GET >/dev/null
    fi
    echo "created ${name}"
  fi
}

upsert_oidc_get_job() {
  local name="$1"
  local schedule="$2"
  local uri="$3"
  local audience="$4"

  if gcloud scheduler jobs describe "${name}" --project "${PROJECT_ID}" --location "${LOCATION}" >/dev/null 2>&1; then
    gcloud scheduler jobs update http "${name}" \
      --project "${PROJECT_ID}" \
      --location "${LOCATION}" \
      --schedule "${schedule}" \
      --time-zone "Etc/UTC" \
      --uri "${uri}" \
      --http-method GET \
      --oidc-service-account-email "${SCHEDULER_SA}" \
      --oidc-token-audience "${audience}" >/dev/null
    echo "updated ${name}"
  else
    gcloud scheduler jobs create http "${name}" \
      --project "${PROJECT_ID}" \
      --location "${LOCATION}" \
      --schedule "${schedule}" \
      --time-zone "Etc/UTC" \
      --uri "${uri}" \
      --http-method GET \
      --oidc-service-account-email "${SCHEDULER_SA}" \
      --oidc-token-audience "${audience}" >/dev/null
    echo "created ${name}"
  fi
}

upsert_http_job "sapphire-alpha-health-6h" "0 */6 * * *" "${ALPHA_URL}/health" "GET" "" ""
upsert_http_job "sapphire-aster-health-6h" "5 */6 * * *" "${ASTER_URL}/health" "GET" "" ""
upsert_http_job "sapphire-lighter-health-6h" "10 */6 * * *" "${LIGHTER_URL}/health" "GET" "" ""
upsert_oidc_get_job "sapphire-gateway-health-6h" "15 */6 * * *" "${GATEWAY_URL}/" "${GATEWAY_URL}"
upsert_http_job \
  "sapphire-alpha-heartbeat-30m" \
  "*/30 * * * *" \
  "${ALPHA_URL}/telegram/webhook" \
  "POST" \
  "Content-Type=application/json,X-Telegram-Bot-Api-Secret-Token=${WEBHOOK_SECRET}" \
  "${HEARTBEAT_BODY}"
upsert_http_job \
  "sapphire-alpha-status-daily" \
  "15 14 * * *" \
  "${ALPHA_URL}/telegram/webhook" \
  "POST" \
  "Content-Type=application/json,X-Telegram-Bot-Api-Secret-Token=${WEBHOOK_SECRET}" \
  "${STATUS_BODY}"
upsert_http_job \
  "sapphire-alpha-strategy-gate-daily" \
  "45 14 * * *" \
  "${ALPHA_URL}/telegram/webhook" \
  "POST" \
  "Content-Type=application/json,X-Telegram-Bot-Api-Secret-Token=${WEBHOOK_SECRET}" \
  "${STRATEGY_GATE_BODY}"

echo
echo "Cloud Scheduler jobs in ${PROJECT_ID}/${LOCATION}:"
gcloud scheduler jobs list \
  --project "${PROJECT_ID}" \
  --location "${LOCATION}" \
  --format="table(name.basename(),schedule,httpTarget.uri,state)"
