#!/usr/bin/env bash
# Probe the TradingView webhook ingress and print the public URL + health.
set -euo pipefail

ROOT="/Users/aribs/Code/Sapphire"
URL_FILE="$ROOT/data/webhook/tunnel_url.txt"

echo "=== Webhook Receiver ==="
if curl -s -m 3 http://localhost:9090/health >/tmp/webhook_health.json 2>/dev/null; then
    echo "localhost:9090  → OK"
    cat /tmp/webhook_health.json | python3 -m json.tool 2>/dev/null || cat /tmp/webhook_health.json
else
    echo "localhost:9090  → UNREACHABLE"
fi

echo ""
echo "=== Public Tunnel URL ==="
if [[ -f "$URL_FILE" ]]; then
    URL=$(cat "$URL_FILE")
    echo "$URL"
    if curl -s -m 8 "$URL/health" >/tmp/webhook_public_health.json 2>/dev/null; then
        echo "public health   → OK"
    else
        echo "public health   → UNREACHABLE"
    fi
else
    echo "No tunnel URL file yet. Start with: launchctl kickstart -k gui/$UID/com.sapphire.webhook-tunnel"
fi
