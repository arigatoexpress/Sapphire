#!/usr/bin/env bash
# Audit and optionally reconcile GCP service/job scope for Sapphire focused operation.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
LOCATION="${LOCATION:-us-central1}"
APPLY=0
DELETE_SERVICES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)
      APPLY=1
      ;;
    --delete-services)
      DELETE_SERVICES=1
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--apply] [--delete-services]"
      exit 2
      ;;
  esac
  shift
done

ALLOWED_SERVICES=(
  "sapphire-alpha"
  "sapphire-aster"
  "sapphire-lighter"
  "sapphire-gateway"
  "sapphire-github-webhook-relay"
  "sapphirebook-web"
)

ALLOWED_JOBS=(
  "sapphire-alpha-health-6h"
  "sapphire-aster-health-6h"
  "sapphire-lighter-health-6h"
  "sapphire-gateway-health-6h"
  "sapphire-alpha-heartbeat-30m"
  "sapphire-alpha-status-daily"
  "sapphire-alpha-strategy-gate-daily"
  "sapphire-heartbeat-30m"
  "obsidian-heartbeat-30m"
  "emerald-heartbeat-30m"
  "sapphire-dep-audit-daily"
  "sapphire-security-scan-weekly"
)

contains() {
  local needle="$1"
  shift
  local item
  for item in "$@"; do
    if [[ "${item}" == "${needle}" ]]; then
      return 0
    fi
  done
  return 1
}

echo "Project: ${PROJECT_ID}"
echo "Location: ${LOCATION}"
echo

echo "Cloud Run services:"
mapfile -t CURRENT_SERVICES < <(gcloud run services list --project "${PROJECT_ID}" --platform managed --format='value(name)' | sort)
printf '  %s\n' "${CURRENT_SERVICES[@]}"
echo

echo "Scheduler jobs (${LOCATION}):"
mapfile -t CURRENT_JOBS < <(gcloud scheduler jobs list --project "${PROJECT_ID}" --location "${LOCATION}" --format='value(name.basename())' | sort)
printf '  %s\n' "${CURRENT_JOBS[@]}"
echo

EXTRA_SERVICES=()
for svc in "${CURRENT_SERVICES[@]}"; do
  if ! contains "${svc}" "${ALLOWED_SERVICES[@]}"; then
    EXTRA_SERVICES+=("${svc}")
  fi
done

EXTRA_JOBS=()
for job in "${CURRENT_JOBS[@]}"; do
  if ! contains "${job}" "${ALLOWED_JOBS[@]}"; then
    EXTRA_JOBS+=("${job}")
  fi
done

if [[ ${#EXTRA_SERVICES[@]} -eq 0 ]]; then
  echo "No extra Cloud Run services outside focus scope."
else
  echo "Extra Cloud Run services outside focus scope:"
  printf '  %s\n' "${EXTRA_SERVICES[@]}"
fi

echo
if [[ ${#EXTRA_JOBS[@]} -eq 0 ]]; then
  echo "No extra Scheduler jobs outside focus scope."
else
  echo "Extra Scheduler jobs outside focus scope:"
  printf '  %s\n' "${EXTRA_JOBS[@]}"
fi

if [[ "${APPLY}" -eq 1 ]]; then
  echo
  echo "Applying reconciliation..."

  if [[ ${#EXTRA_JOBS[@]} -gt 0 ]]; then
    for job in "${EXTRA_JOBS[@]}"; do
      echo "Deleting Scheduler job: ${job}"
      gcloud scheduler jobs delete "${job}" --project "${PROJECT_ID}" --location "${LOCATION}" --quiet
    done
  fi

  if [[ "${DELETE_SERVICES}" -eq 1 && ${#EXTRA_SERVICES[@]} -gt 0 ]]; then
    for svc in "${EXTRA_SERVICES[@]}"; do
      echo "Deleting Cloud Run service: ${svc}"
      region="$(gcloud run services describe "${svc}" --project "${PROJECT_ID}" --platform managed --format='value(location)' 2>/dev/null || true)"
      if [[ -n "${region}" ]]; then
        gcloud run services delete "${svc}" --project "${PROJECT_ID}" --region "${region}" --quiet
      else
        echo "Skipping ${svc}: unable to resolve region"
      fi
    done
  fi

  echo "Reconciliation complete."
else
  echo
  echo "Dry-run only. Re-run with --apply to delete extra scheduler jobs."
  echo "Add --delete-services to also delete extra Cloud Run services."
fi
