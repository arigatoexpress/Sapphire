#!/usr/bin/env bash
set -euo pipefail

# Keep EU proxy firewall allowlist in sync with rari2's current public IPv4.
# Default targets:
#   - remote host: rari@100.x.x.y
#   - firewall rule: allow-sapphire-eu-proxy-3128
#   - project: sapphire-479610

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
REMOTE_HOST="${REMOTE_HOST:-rari@100.x.x.y}"
FIREWALL_RULE="${FIREWALL_RULE:-allow-sapphire-eu-proxy-3128}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "missing command: $1" >&2
    exit 1
  }
}

require_cmd gcloud
require_cmd ssh

CURRENT_IP="$(
  ssh -o BatchMode=yes -o ConnectTimeout=10 "${REMOTE_HOST}" \
    "curl -4 -s --max-time 8 https://api.ipify.org" 2>/dev/null || true
)"

if [[ -z "${CURRENT_IP}" ]]; then
  echo "failed to resolve remote IPv4 from ${REMOTE_HOST}" >&2
  exit 1
fi

if [[ ! "${CURRENT_IP}" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
  echo "resolved remote IP is invalid: ${CURRENT_IP}" >&2
  exit 1
fi

TARGET_RANGE="${CURRENT_IP}/32"
EXISTING="$(
  gcloud compute firewall-rules describe "${FIREWALL_RULE}" \
    --project "${PROJECT_ID}" \
    --format="value(sourceRanges.list())" 2>/dev/null || true
)"

if [[ "${EXISTING}" == "${TARGET_RANGE}" ]]; then
  echo "firewall up to date: ${FIREWALL_RULE} -> ${TARGET_RANGE}"
  exit 0
fi

if [[ -z "${EXISTING}" ]]; then
  echo "creating firewall rule ${FIREWALL_RULE} with source ${TARGET_RANGE}"
  gcloud compute firewall-rules create "${FIREWALL_RULE}" \
    --project "${PROJECT_ID}" \
    --network default \
    --direction INGRESS \
    --priority 1000 \
    --action ALLOW \
    --rules tcp:3128 \
    --source-ranges "${TARGET_RANGE}" \
    --target-tags sapphire-eu-proxy
else
  echo "updating firewall rule ${FIREWALL_RULE}: ${EXISTING} -> ${TARGET_RANGE}"
  gcloud compute firewall-rules update "${FIREWALL_RULE}" \
    --project "${PROJECT_ID}" \
    --source-ranges "${TARGET_RANGE}"
fi

echo "done: ${FIREWALL_RULE} now allows ${TARGET_RANGE}"
