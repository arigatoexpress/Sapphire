#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
REGION="${REGION:-us-central1}"
MODE="${1:---dry-run}"

ALLOWLIST=(
  "agentic-pm-hub-autonomy-15m"
  "agentic-pm-hub-assistant-checkin-30m"
  "bis-automation-job"
  "sapphire-platform-brief-hourly"
  "sapphire-superswarm-rollup-hourly"
  "weekly-self-improvement"
  "sapphire-gateway-health-6h"
)

contains() {
  local needle="$1"
  shift
  local item
  for item in "$@"; do
    if [[ "$item" == "$needle" ]]; then
      return 0
    fi
  done
  return 1
}

echo "== Scheduler Drift Cleanup =="
echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo "Mode: ${MODE}"
echo

mapfile -t jobs < <(
  gcloud scheduler jobs list \
    --project "${PROJECT_ID}" \
    --location "${REGION}" \
    --format='value(name,state,schedule,httpTarget.uri)'
)

if [[ "${#jobs[@]}" -eq 0 ]]; then
  echo "No scheduler jobs found."
  exit 0
fi

echo "Current jobs:"
printf '  %s\n' "${jobs[@]}"
echo

stale_jobs=()
for row in "${jobs[@]}"; do
  job_name="${row%%$'\t'*}"
  if ! contains "${job_name}" "${ALLOWLIST[@]}"; then
    stale_jobs+=("${job_name}")
  fi
done

if [[ "${#stale_jobs[@]}" -eq 0 ]]; then
  echo "No stale scheduler jobs detected."
  exit 0
fi

echo "Stale jobs (not in allowlist):"
printf '  - %s\n' "${stale_jobs[@]}"
echo

case "${MODE}" in
  --dry-run)
    echo "Dry run complete. Re-run with --apply to pause stale jobs."
    ;;
  --apply)
    for job in "${stale_jobs[@]}"; do
      echo "Pausing ${job}..."
      gcloud scheduler jobs pause "${job}" \
        --project "${PROJECT_ID}" \
        --location "${REGION}" >/dev/null
    done
    echo "Paused ${#stale_jobs[@]} stale jobs."
    ;;
  --delete)
    for job in "${stale_jobs[@]}"; do
      echo "Deleting ${job}..."
      gcloud scheduler jobs delete "${job}" \
        --project "${PROJECT_ID}" \
        --location "${REGION}" \
        --quiet >/dev/null
    done
    echo "Deleted ${#stale_jobs[@]} stale jobs."
    ;;
  *)
    echo "Unsupported mode: ${MODE}"
    echo "Use one of: --dry-run, --apply, --delete"
    exit 1
    ;;
esac
