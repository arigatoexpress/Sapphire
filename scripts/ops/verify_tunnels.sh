#!/usr/bin/env bash
# Enumerate and health-check Cloudflare tunnels without needing a browser.
#
# Prereqs:
#   - CLOUDFLARE_API_TOKEN  (scoped: Account.Cloudflare Tunnel.Read, Zone.Read)
#   - CLOUDFLARE_ACCOUNT_ID (find at https://dash.cloudflare.com/profile)
#
# Usage:
#   scripts/ops/verify_tunnels.sh
#
# Exit codes:
#   0  all tunnels healthy
#   1  config missing
#   2  one or more tunnels unhealthy / not connected
#
# The script uses only curl + jq; no cloudflared binary required.

set -euo pipefail

: "${CLOUDFLARE_API_TOKEN:?Set CLOUDFLARE_API_TOKEN (Account.Cloudflare Tunnel.Read)}"
: "${CLOUDFLARE_ACCOUNT_ID:?Set CLOUDFLARE_ACCOUNT_ID (find at dash.cloudflare.com/profile)}"

API="https://api.cloudflare.com/client/v4"
AUTH=(-H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}")

command -v jq >/dev/null 2>&1 || { echo "jq required (brew install jq)" >&2; exit 1; }

echo "== Cloudflare tunnels for account ${CLOUDFLARE_ACCOUNT_ID} =="

TUNNELS_JSON=$(curl -sS "${AUTH[@]}" \
    "${API}/accounts/${CLOUDFLARE_ACCOUNT_ID}/cfd_tunnel?is_deleted=false&per_page=50")

SUCCESS=$(echo "${TUNNELS_JSON}" | jq -r '.success')
if [[ "${SUCCESS}" != "true" ]]; then
    echo "Cloudflare API error:" >&2
    echo "${TUNNELS_JSON}" | jq '.errors' >&2
    exit 1
fi

COUNT=$(echo "${TUNNELS_JSON}" | jq '.result | length')
echo "Found ${COUNT} tunnel(s)."
echo

unhealthy=0
echo "${TUNNELS_JSON}" | jq -c '.result[]' | while read -r tunnel; do
    NAME=$(echo "${tunnel}" | jq -r '.name')
    ID=$(echo "${tunnel}" | jq -r '.id')
    STATUS=$(echo "${tunnel}" | jq -r '.status')
    CONNECTIONS=$(echo "${tunnel}" | jq -r '.connections | length')
    CREATED=$(echo "${tunnel}" | jq -r '.created_at')

    printf "  %-40s %-10s  %d active conn   (created %s)\n" \
        "${NAME}" "${STATUS}" "${CONNECTIONS}" "${CREATED%T*}"

    # Fetch per-connection detail for anything not plainly healthy.
    if [[ "${STATUS}" != "healthy" && "${STATUS}" != "active" ]]; then
        echo "    tunnel ${ID} status=${STATUS} — fetching connections..."
        curl -sS "${AUTH[@]}" \
            "${API}/accounts/${CLOUDFLARE_ACCOUNT_ID}/cfd_tunnel/${ID}/connections" \
            | jq -c '.result[]?' \
            | while read -r conn; do
                echo "      - $(echo "${conn}" | jq -r '.colo_name // "?"') " \
                     "opened $(echo "${conn}" | jq -r '.opened_at // "?"')"
            done
        unhealthy=$((unhealthy + 1))
    fi
done

echo
if [[ "${COUNT}" -eq 0 ]]; then
    echo "No tunnels found. Create one at https://one.dash.cloudflare.com/?to=/:account/networks/tunnels"
    exit 2
fi

# The subshell above can't mutate unhealthy; compute it again for the exit code.
UNHEALTHY=$(echo "${TUNNELS_JSON}" \
    | jq '[.result[] | select(.status != "healthy" and .status != "active")] | length')
if [[ "${UNHEALTHY}" -gt 0 ]]; then
    echo "${UNHEALTHY} tunnel(s) not healthy. See above for detail."
    exit 2
fi
echo "All tunnels healthy."
