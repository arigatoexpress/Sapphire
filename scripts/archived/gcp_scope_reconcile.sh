#!/usr/bin/env bash
# Audit and optionally reconcile GCP service/job scope for Sapphire focused operation.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
LOCATION="${LOCATION:-us-central1}"
APPLY=0
DELETE_SERVICES=0
STRICT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)
      APPLY=1
      ;;
    --delete-services)
      DELETE_SERVICES=1
      ;;
    --strict)
      STRICT=1
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--apply] [--delete-services] [--strict]"
      exit 2
      ;;
  esac
  shift
done

ALLOWED_SERVICES=(
  "agentic-pm-hub"
  "blanga-bis-beta"
  "sapphire-alpha"
  "sapphire-aster"
  "sapphire-gateway"
  "sapphire-lighter"
  "sapphire-openclaw-cloud"
  "sapphire-scout-sandbox"
  "sapphire-telegram-bot"
  "sapphire-unified-frontend"
  "sapphire-unified-jobs"
  "tho-agent"
)

ALLOWED_JOBS=(
  "agentic-pm-hub-assistant-checkin-30m"
  "agentic-pm-hub-autonomy-15m"
  "bis-automation-job"
  "sapphire-architecture-bottleneck-digest-hourly"
  "sapphire-gateway-health-6h"
  "sapphire-platform-brief-hourly"
  "sapphire-strategy-ops-digest-6h"
  "sapphire-strategy-ops-snapshot-hourly"
  "sapphire-superswarm-rollup-hourly"
  "weekly-self-improvement"
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

read_array_compat() {
  # macOS default bash (3.x) lacks mapfile/readarray; keep script portable.
  local target_array="$1"
  local input_data="$2"
  if declare -F mapfile >/dev/null 2>&1; then
    mapfile -t "$target_array" <<<"$input_data"
  else
    eval "$target_array=()"
    while IFS= read -r line; do
      [[ -n "$line" ]] || continue
      eval "$target_array+=(\"\$line\")"
    done <<<"$input_data"
  fi
}

load_inventory() {
  local services_raw jobs_raw
  services_raw="$(
    gcloud run services list --project "${PROJECT_ID}" --platform managed --format='value(name)' | sort
  )"
  jobs_raw="$(
    gcloud scheduler jobs list --project "${PROJECT_ID}" --location "${LOCATION}" --format='value(name.basename())' | sort
  )"
  read_array_compat CURRENT_SERVICES "${services_raw}"
  read_array_compat CURRENT_JOBS "${jobs_raw}"
}

compute_extras() {
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
}

print_extras() {
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
}

resolve_service_region() {
  local service_name="$1"
  local region

  region="$(
    gcloud run services list \
      --project "${PROJECT_ID}" \
      --platform managed \
      --format='value(name,region)' \
      | awk -v target="${service_name}" '$1 == target {print $2; exit}'
  )"
  if [[ -n "${region}" ]]; then
    echo "${region}"
    return
  fi

  region="$(
    gcloud run services describe "${service_name}" \
      --project "${PROJECT_ID}" \
      --platform managed \
      --format='value(region)' 2>/dev/null || true
  )"
  if [[ -n "${region}" ]]; then
    echo "${region}"
    return
  fi

  region="$(
    gcloud run services describe "${service_name}" \
      --project "${PROJECT_ID}" \
      --platform managed \
      --format='value(location)' 2>/dev/null || true
  )"
  echo "${region}"
}

echo "Project: ${PROJECT_ID}"
echo "Location: ${LOCATION}"
echo

load_inventory
echo "Cloud Run services:"
printf '  %s\n' "${CURRENT_SERVICES[@]}"
echo

echo "Scheduler jobs (${LOCATION}):"
printf '  %s\n' "${CURRENT_JOBS[@]}"
echo

compute_extras
print_extras

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
      region="$(resolve_service_region "${svc}")"
      if [[ -n "${region}" ]]; then
        gcloud run services delete "${svc}" --project "${PROJECT_ID}" --region "${region}" --quiet
      else
        echo "Skipping ${svc}: unable to resolve region"
      fi
    done
  fi

  echo "Reconciliation complete."

  if [[ "${STRICT}" -eq 1 ]]; then
    echo
    echo "Running strict post-reconcile scope check..."
    load_inventory
    compute_extras
    if [[ ${#EXTRA_SERVICES[@]} -gt 0 || ${#EXTRA_JOBS[@]} -gt 0 ]]; then
      print_extras
      echo "Strict scope check FAILED after reconciliation."
      exit 1
    fi
    echo "Strict scope check PASSED."
  fi
else
  if [[ "${STRICT}" -eq 1 ]]; then
    if [[ ${#EXTRA_SERVICES[@]} -gt 0 || ${#EXTRA_JOBS[@]} -gt 0 ]]; then
      echo
      echo "Strict scope check FAILED: extras detected."
      exit 1
    fi
    echo
    echo "Strict scope check PASSED."
  fi

  echo
  echo "Dry-run only. Re-run with --apply to delete extra scheduler jobs."
  echo "Add --delete-services to also delete extra Cloud Run services."
fi
