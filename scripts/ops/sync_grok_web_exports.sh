#!/usr/bin/env bash
# Sapphire — Grok web ↔ plant Knowledge inbox bridge sync
#
# Canonical monorepo copy of the plant wrapper
# (~/ops-state/finish-line/scripts/sync_grok_web_exports.sh). Either may call the
# other; this file is what Claude/Codex should densify into ops-state if missing.
#
# Contract:
#   1) optional git pull --ff-only of the Sapphire clone
#   2) copy NEW/CHANGED *.md from data/grok-web-exports/ → Knowledge inbox
#   3) never delete sources; never write outside the inbox
#   4) append a one-line log entry
#
# Usage:
#   bash scripts/ops/sync_grok_web_exports.sh
#   bash scripts/ops/sync_grok_web_exports.sh --pull
#   bash scripts/ops/sync_grok_web_exports.sh --dry-run
#   SAPPHIRE_DIR=~/Code/Sapphire KNOWLEDGE_INBOX=~/Knowledge/0-Inbox/grok-web \
#     bash scripts/ops/sync_grok_web_exports.sh

set -euo pipefail

PULL=0
DRY=0
for arg in "$@"; do
  case "$arg" in
    --pull) PULL=1 ;;
    --dry-run) DRY=1 ;;
    --help|-h)
      sed -n '2,24p' "$0"
      exit 0
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SAPPHIRE_DIR="${SAPPHIRE_DIR:-$REPO_ROOT}"
SRC="${SAPPHIRE_DIR}/data/grok-web-exports"
INBOX="${KNOWLEDGE_INBOX:-$HOME/Knowledge/0-Inbox/grok-web}"
LOG_DIR="${SAPPHIRE_BRIDGE_LOG_DIR:-$HOME/ops-state/logs}"
LOG_FILE="${LOG_DIR}/grok-web-bridge.log"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [[ ! -d "$SRC" ]]; then
  echo "[grok-bridge] ERROR: missing export folder: $SRC" >&2
  exit 2
fi

if [[ "$PULL" -eq 1 ]]; then
  if [[ -d "$SAPPHIRE_DIR/.git" ]]; then
    git -C "$SAPPHIRE_DIR" pull --ff-only origin main || {
      echo "[grok-bridge] WARN: git pull failed (non-fatal)" >&2
    }
  fi
fi

mkdir -p "$INBOX"
if [[ -d "$(dirname "$LOG_FILE")" ]] || mkdir -p "$LOG_DIR" 2>/dev/null; then
  :
fi

copied=0
skipped=0
failed=0

# Copy when dest missing or source is newer; never delete.
for src in "$SRC"/*.md "$SRC"/*.json; do
  [[ -e "$src" ]] || continue
  base="$(basename "$src")"
  case "$base" in
    README.md|MANIFEST.json|.gitkeep) skipped=$((skipped+1)); continue ;;
  esac
  dest="$INBOX/$base"
  if [[ -f "$dest" ]] && [[ ! "$src" -nt "$dest" ]]; then
    skipped=$((skipped+1))
    continue
  fi
  if [[ "$DRY" -eq 1 ]]; then
    echo "[dry-run] would copy $base → $dest"
    copied=$((copied+1))
    continue
  fi
  if cp -p "$src" "$dest"; then
    copied=$((copied+1))
  else
    failed=$((failed+1))
  fi
done

line="$STAMP pull=$PULL dry=$DRY copied=$copied skipped=$skipped failed=$failed src=$SRC inbox=$INBOX"
echo "[grok-bridge] $line"
if [[ -d "$LOG_DIR" ]]; then
  echo "$line" >>"$LOG_FILE" || true
fi

# Optional: publish operator feeds if plant script exists
if [[ "$DRY" -eq 0 ]] && [[ -x "$HOME/ops-state/finish-line/scripts/publish_operator_feeds.py" ]]; then
  python3 "$HOME/ops-state/finish-line/scripts/publish_operator_feeds.py" 2>/dev/null || true
elif [[ "$DRY" -eq 0 ]] && command -v python3 >/dev/null 2>&1 \
  && [[ -f "$SAPPHIRE_DIR/scripts/ops/publish_operator_feeds.py" ]]; then
  python3 "$SAPPHIRE_DIR/scripts/ops/publish_operator_feeds.py" 2>/dev/null || true
fi

exit 0
