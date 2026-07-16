#!/usr/bin/env bash
# Enable Tailscale Funnel on port 9090 for the TradingView webhook receiver.
#
# Idempotent: checks current funnel status before making changes.
# Safe: prints the Tailscale admin URL and only attempts to enable funnel
# if the tailscale CLI is installed and the user is logged in.
#
# Usage:
#   infra/scripts/enable-tailscale-funnel.sh

set -euo pipefail

PORT="${SAPPHIRE_TV_FUNNEL_PORT:-9090}"
TAILSCALE_BIN="$(command -v tailscale || true)"

admin_url="https://login.tailscale.com/admin/machines"

echo "Tailscale Funnel helper for Sapphire webhook receiver"
echo "Admin console: ${admin_url}"
echo

if [[ -z "${TAILSCALE_BIN}" ]]; then
    echo "tailscale CLI not found in PATH. Install from https://tailscale.com/download"
    exit 1
fi

# Verify the user is logged in. `tailscale status` exits non-zero when not logged in.
if ! "${TAILSCALE_BIN}" status >/dev/null 2>&1; then
    echo "tailscale is not logged in. Run: tailscale up"
    echo "Then rerun this script."
    exit 1
fi

echo "tailscale logged in: $("${TAILSCALE_BIN}" status --self | head -n1 || true)"
echo

# Check whether funnel is already enabled for this port.
if "${TAILSCALE_BIN}" serve status 2>/dev/null | grep -qE "funnel.*:${PORT}|:${PORT}.*funnel"; then
    echo "Tailscale funnel appears to already be enabled on port ${PORT}."
    echo "Current serve/funnel status:"
    "${TAILSCALE_BIN}" serve status || true
    exit 0
fi

echo "Enabling Tailscale funnel on port ${PORT} ..."

# Run in the background so a hung auth/tailnet prompt does not block forever.
funnel_log="$(mktemp)"
"${TAILSCALE_BIN}" funnel --bg "tcp:${PORT}" >"${funnel_log}" 2>&1 &
funnel_pid=$!
sleep 5

if ! kill -0 "${funnel_pid}" 2>/dev/null; then
    # Process exited quickly — inspect the log.
    wait "${funnel_pid}" 2>/dev/null || true
    if "${TAILSCALE_BIN}" serve status 2>/dev/null | grep -qE "funnel.*:${PORT}|:${PORT}.*funnel"; then
        echo "Tailscale funnel enabled on port ${PORT}."
        echo "Verify with: tailscale serve status"
        echo "Admin console: ${admin_url}"
        rm -f "${funnel_log}"
        exit 0
    fi
fi

# Still running or not confirmed enabled; terminate the background job.
kill "${funnel_pid}" 2>/dev/null || true
wait "${funnel_pid}" 2>/dev/null || true

if "${TAILSCALE_BIN}" serve status 2>/dev/null | grep -qE "funnel.*:${PORT}|:${PORT}.*funnel"; then
    echo "Tailscale funnel enabled on port ${PORT}."
    echo "Verify with: tailscale serve status"
    echo "Admin console: ${admin_url}"
    rm -f "${funnel_log}"
    exit 0
fi

echo "Could not confirm funnel is enabled on port ${PORT}."
echo "Tailscale output:"
cat "${funnel_log}" || true
rm -f "${funnel_log}"
echo
echo "Common causes:"
echo "  - Funnel is not enabled for your tailnet (see ${admin_url})"
echo "  - ACLs block funnel for this machine"
echo "  - Port ${PORT} is already in use by another listener"
exit 1
