#!/usr/bin/env bash
# Sapphire OS — Telegram notification wrapper
# Usage: ./telegram_notify.sh "message" [priority]
# Priority: p0 (urgent), p1 (normal), p2 (low)
#
# Requires: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in env or
#           ~/.config/sapphire-secrets/telegram_bot_token
#
# To populate from GCP Secret Manager:
#   gcloud secrets versions access latest --secret=TELEGRAM_BOT_TOKEN --project=sapphire-479610 > ~/.config/sapphire-secrets/telegram_bot_token
#   gcloud secrets versions access latest --secret=TELEGRAM_CHAT_ID --project=sapphire-479610 > ~/.config/sapphire-secrets/telegram_chat_id

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

MESSAGE="${1:?Usage: telegram_notify.sh \"message\" [priority]}"
PRIORITY="${2:-p1}"

exec python3 "$REPO_DIR/plugins/claw-sapphire/tools/notify.py" "$MESSAGE" --priority "$PRIORITY"
