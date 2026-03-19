#!/usr/bin/env bash
# Configure single-agent Sapphire scheduler jobs.
#
# This script is idempotent: existing jobs are updated, missing jobs are created.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
LOCATION="${LOCATION:-us-central1}"
ALPHA_URL="${ALPHA_URL:-$(gcloud run services describe sapphire-alpha --project "${PROJECT_ID}" --region "${LOCATION}" --format='value(status.url)')}"
ENABLE_TRADINGVIEW_JOB_WIRING="${ENABLE_TRADINGVIEW_JOB_WIRING:-false}"
JOB_NAMES=(
  "sapphire-heartbeat-30m"
  "sapphire-dep-audit-daily"
  "sapphire-security-scan-weekly"
)
LEGACY_JOB_NAMES=(
  "obsidian-heartbeat-30m"
  "emerald-heartbeat-30m"
)

if [[ "${ENABLE_TRADINGVIEW_JOB_WIRING,,}" != "true" ]]; then
  echo "TradingView integration is disabled by default. Pausing TradingView webhook scheduler jobs."
  for job in "${JOB_NAMES[@]}" "${LEGACY_JOB_NAMES[@]}"; do
    if gcloud scheduler jobs describe "${job}" --project "${PROJECT_ID}" --location "${LOCATION}" >/dev/null 2>&1; then
      gcloud scheduler jobs pause "${job}" --project "${PROJECT_ID}" --location "${LOCATION}" >/dev/null || true
      echo "paused ${job}"
    else
      echo "missing ${job} (nothing to pause)"
    fi
  done
  echo
  echo "To re-enable TradingView webhook jobs later, run with:"
  echo "  ENABLE_TRADINGVIEW_JOB_WIRING=true ./scripts/setup_clawdbot_jobs.sh"
  exit 0
fi

WEBHOOK_SECRET="$(
  gcloud secrets versions access latest \
    --secret=TRADINGVIEW_WEBHOOK_SECRET \
    --project "${PROJECT_ID}"
)"

SAPPHIRE_HEARTBEAT_BODY="$(cat <<JSON
{
  "action": "tv_custom",
  "agent_id": "sapphire",
  "instruction": "SAPPHIRE role heartbeat for arigatoexpress/Sapphire only. Act as Security and Code Quality Lead: summarize top security posture, critical risks, and immediate remediation actions. If owner steering is needed, ask one direct question with concrete options.",
  "source": "scheduler",
  "task": "sapphire_heartbeat_30m"
}
JSON
)"

DEP_AUDIT_BODY="$(cat <<JSON
{
  "action": "tv_custom",
  "agent_id": "sapphire",
  "instruction": "Run dependency audit for arigatoexpress/Sapphire only. Provide severity-ranked findings, safe upgrade sequence, and clearly call out any breaking change risk.",
  "source": "scheduler",
  "task": "dep_audit_daily"
}
JSON
)"

SECURITY_SWEEP_BODY="$(cat <<JSON
{
  "action": "tv_custom",
  "agent_id": "sapphire",
  "instruction": "Run weekly security sweep for arigatoexpress/Sapphire only. Focus on secret exposure, dependency CVEs, container hardening, and CI/CD supply-chain risks with prioritized remediation actions.",
  "source": "scheduler",
  "task": "security_scan_weekly"
}
JSON
)"

upsert_hook_job() {
  local name="$1"
  local schedule="$2"
  local body="$3"
  local description="$4"

  if gcloud scheduler jobs describe "${name}" --project "${PROJECT_ID}" --location "${LOCATION}" >/dev/null 2>&1; then
    gcloud scheduler jobs update http "${name}" \
      --project "${PROJECT_ID}" \
      --location "${LOCATION}" \
      --description "${description}" \
      --schedule "${schedule}" \
      --time-zone "Etc/UTC" \
      --uri "${ALPHA_URL}/tradingview/webhook" \
      --http-method POST \
      --update-headers "Content-Type=application/json,X-Sapphire-Webhook-Secret=${WEBHOOK_SECRET}" \
      --message-body "${body}" >/dev/null
    echo "updated ${name}"
  else
    gcloud scheduler jobs create http "${name}" \
      --project "${PROJECT_ID}" \
      --location "${LOCATION}" \
      --description "${description}" \
      --schedule "${schedule}" \
      --time-zone "Etc/UTC" \
      --uri "${ALPHA_URL}/tradingview/webhook" \
      --http-method POST \
      --headers "Content-Type=application/json,X-Sapphire-Webhook-Secret=${WEBHOOK_SECRET}" \
      --message-body "${body}" >/dev/null
    echo "created ${name}"
  fi
}

upsert_hook_job \
  "${JOB_NAMES[0]}" \
  "*/30 * * * *" \
  "${SAPPHIRE_HEARTBEAT_BODY}" \
  "SAPPHIRE operations heartbeat for Sapphire-only operations."
upsert_hook_job \
  "${JOB_NAMES[1]}" \
  "0 14 * * *" \
  "${DEP_AUDIT_BODY}" \
  "Daily Sapphire dependency audit with owner delivery."
upsert_hook_job \
  "${JOB_NAMES[2]}" \
  "0 15 * * 1" \
  "${SECURITY_SWEEP_BODY}" \
  "Weekly Sapphire security sweep with owner delivery."

# Legacy deprecated jobs are paused to avoid noisy references.
for legacy_job in "${LEGACY_JOB_NAMES[@]}"; do
  if gcloud scheduler jobs describe "${legacy_job}" --project "${PROJECT_ID}" --location "${LOCATION}" >/dev/null 2>&1; then
    gcloud scheduler jobs pause "${legacy_job}" --project "${PROJECT_ID}" --location "${LOCATION}" >/dev/null || true
    echo "paused deprecated job ${legacy_job}"
  fi
done

echo
echo "OpenClaw employee scheduler jobs in ${PROJECT_ID}/${LOCATION}:"
gcloud scheduler jobs list \
  --project "${PROJECT_ID}" \
  --location "${LOCATION}" \
  --format="table(name.basename(),schedule,httpTarget.uri,state)" \
  --filter="name:(sapphire-heartbeat-30m OR sapphire-dep-audit-daily OR sapphire-security-scan-weekly OR obsidian-heartbeat-30m OR emerald-heartbeat-30m)"
