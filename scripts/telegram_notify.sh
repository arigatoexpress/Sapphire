#!/usr/bin/env bash
# Sapphire OS — Telegram draft notification wrapper
# Usage: ./telegram_notify.sh "message" [priority]
# Priority: p0 (urgent), p1 (normal), p2 (low)
#
# Default: append a PM-bot-compatible draft to
# ~/.cache/sapphire/telegram/pm_bot_drafts.jsonl.
# Set SAPPHIRE_NOTIFY_TELEGRAM_LIVE=1 only for an explicit live send window.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

MESSAGE="${1:?Usage: telegram_notify.sh \"message\" [priority]}"
PRIORITY="${2:-p1}"

exec python3 "$REPO_DIR/plugins/claw-sapphire/tools/notify.py" "$MESSAGE" --priority "$PRIORITY"
