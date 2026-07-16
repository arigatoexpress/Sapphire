#!/usr/bin/env bash
# Expose the Mac webhook receiver (localhost:9090) via Cloudflare Quick Tunnel.
# Writes the public URL to data/webhook/tunnel_url.txt so TradingView alerts
# can be pointed at it.
set -euo pipefail

ROOT="/Users/aribs/Code/Sapphire"
TUNNEL_LOG="$ROOT/data/logs/webhook-tunnel.log"
URL_FILE="$ROOT/data/webhook/tunnel_url.txt"

mkdir -p "$ROOT/data/logs" "$ROOT/data/webhook"

# cloudflared quick tunnel prints the URL to stderr/stdout.
# Capture it, write the URL file, then tail the log so the LaunchAgent
# process stays alive.
cloudflared tunnel --url "http://localhost:9090" >"$TUNNEL_LOG" 2>&1 &
CF_PID=$!

# Wait for URL to appear.
for i in {1..30}; do
    URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" | head -1 || true)
    if [[ -n "$URL" ]]; then
        echo "$URL" > "$URL_FILE"
        echo "tunnel_url=$URL" >> "$TUNNEL_LOG"
        break
    fi
    sleep 1
done

if [[ ! -s "$URL_FILE" ]]; then
    echo "ERROR: failed to obtain tunnel URL" >> "$TUNNEL_LOG"
    exit 1
fi

# Keep the LaunchAgent process alive by waiting on cloudflared.
wait "$CF_PID"
