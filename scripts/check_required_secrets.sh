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

print_optional_group() {
  local venue="$1"
  shift
  local present=0
  echo "${venue}:"
  for secret_name in "$@"; do
    if [[ "$(have_secret "${secret_name}")" == "yes" ]]; then
      echo "  - ${secret_name}: present"
      present=$((present + 1))
    else
      echo "  - ${secret_name}: missing"
    fi
  done
  if [[ "${present}" -eq "$#" ]]; then
    echo "  => ${venue} READY"
  elif [[ "${present}" -gt 0 ]]; then
    echo "  => ${venue} PARTIAL (bridge may not be fully active)"
  else
    echo "  => ${venue} OPTIONAL (fallback mode still available)"
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
  "SAPPHIRE_CONTROL_API_TOKEN" \
  "OPENCLAW_GATEWAY_TOKEN"
print_group "ASTER" "ASTER_API_KEY" "ASTER_SECRET_KEY"
print_group "LIGHTER" "LIGHTER_API_KEY_0" "LIGHTER_API_PUBLIC_KEY_0"
print_optional_group \
  "SCOUT_EXTERNAL_BRIDGE (optional, enables true Moltbook HTTP bridge)" \
  "SAPPHIRE_SCOUT_EXTERNAL_REGISTER_URL" \
  "SAPPHIRE_SCOUT_EXTERNAL_POST_URL" \
  "SAPPHIRE_SCOUT_EXTERNAL_API_TOKEN"
print_optional_group \
  "VIRUSTOTAL_SKILL_SCANNING (optional, enables VT lookup/upload)" \
  "VIRUSTOTAL_API_KEY"
