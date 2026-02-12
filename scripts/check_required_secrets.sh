#!/usr/bin/env bash
# Check required Secret Manager entries for each Sapphire trading venue.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"

have_secret() {
  local name="$1"
  if gcloud secrets describe "${name}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
    echo "yes"
  else
    echo "no"
  fi
}

print_group() {
  local venue="$1"
  shift
  local missing=0
  echo "${venue}:"
  for secret_name in "$@"; do
    if [[ "$(have_secret "${secret_name}")" == "yes" ]]; then
      echo "  - ${secret_name}: present"
    else
      echo "  - ${secret_name}: MISSING"
      missing=1
    fi
  done
  if [[ "${missing}" -eq 0 ]]; then
    echo "  => ${venue} READY"
  else
    echo "  => ${venue} BLOCKED"
  fi
  echo
}

echo "Project: ${PROJECT_ID}"
echo
print_group \
  "CONTROL_PLANE" \
  "TELEGRAM_BOT_TOKEN" \
  "TELEGRAM_CHAT_ID" \
  "SAPPHIRE_TELEGRAM_WEBHOOK_SECRET" \
  "TRADINGVIEW_WEBHOOK_SECRET" \
  "OPENCLAW_GATEWAY_TOKEN"
print_group "ASTER" "ASTER_API_KEY" "ASTER_SECRET_KEY"
print_group "LIGHTER" "LIGHTER_API_KEY_0" "LIGHTER_API_PUBLIC_KEY_0"
