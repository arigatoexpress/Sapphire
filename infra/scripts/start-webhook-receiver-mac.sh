#!/usr/bin/env bash
# Start the Sapphire webhook receiver on Mac.
#
# This replaces the Windows PC receiver when the Windows node is offline.
# It validates TradingView HMAC and forwards approved signals to the Mac
# signal logger (localhost:18081).
set -euo pipefail

ROOT="/Users/aribs/Code/Sapphire"
WEBHOOK_PORT="${WEBHOOK_PORT:-9090}"
WEBHOOK_SECRET="${WEBHOOK_SECRET:-$(cat /Users/aribs/.config/sapphire-secrets/telegram_webhook_secret 2>/dev/null || true)}"

export WEBHOOK_SECRET
export WEBHOOK_PORT
export WEBHOOK_LOG_FILE="${WEBHOOK_LOG_FILE:-$ROOT/data/logs/webhook-receiver-mac.log}"
export ALERT_LOG_FILE="${ALERT_LOG_FILE:-$ROOT/data/webhook/alerts.jsonl}"
export SIGNAL_LOGGER_MAC="${SIGNAL_LOGGER_MAC:-http://localhost:18081}"
export OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
export PYTHONPATH="$ROOT/services/webhook:$ROOT"

cd "$ROOT/services/webhook"
exec /usr/local/bin/python3 -m uvicorn src.receiver:app --host 0.0.0.0 --port "$WEBHOOK_PORT"
