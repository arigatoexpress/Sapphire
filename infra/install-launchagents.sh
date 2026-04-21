#!/usr/bin/env bash
# Install (or reload) every plist in infra/launchagents/ into ~/Library/LaunchAgents/.
#
# Usage:
#   infra/install-launchagents.sh               # install + bootstrap everything
#   infra/install-launchagents.sh --dry-run     # list what would change, no writes
#   infra/install-launchagents.sh --only <name> # just one label (e.g. --only heartbeat)
#
# Skips any .plist.disabled file. Use `launchctl bootout` manually to stop
# an already-installed agent.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTS_DIR="$SCRIPT_DIR/launchagents"
TARGET_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs/sapphire"
AUTONOMY_LOG_DIR="$HOME/autonomy-status/logs"

DRY_RUN=0
ONLY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --only) ONLY="$2"; shift 2 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done

mkdir -p "$TARGET_DIR" "$LOG_DIR" "$AUTONOMY_LOG_DIR"

uid=$(id -u)
installed=0
skipped=0
reloaded=0

for src in "$AGENTS_DIR"/*.plist; do
  [[ -e "$src" ]] || continue
  name="$(basename "$src" .plist)"

  if [[ -n "$ONLY" && "$name" != *"$ONLY"* ]]; then
    continue
  fi

  dest="$TARGET_DIR/$(basename "$src")"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    if [[ -f "$dest" ]]; then
      if ! cmp -s "$src" "$dest"; then
        echo "[would reload]  $name"
      else
        echo "[no-op]         $name"
      fi
    else
      echo "[would install] $name"
    fi
    continue
  fi

  if [[ -f "$dest" ]] && cmp -s "$src" "$dest"; then
    skipped=$((skipped + 1))
    continue
  fi

  # Boot out if currently loaded (ignore errors — may not be loaded).
  launchctl bootout "gui/$uid/$name" 2>/dev/null || true
  cp "$src" "$dest"
  launchctl bootstrap "gui/$uid" "$dest"
  echo "[loaded]        $name"
  if [[ -f "$dest" ]]; then
    reloaded=$((reloaded + 1))
    installed=$((installed + 1))
  fi
done

if [[ "$DRY_RUN" -eq 0 ]]; then
  echo ""
  echo "Done — $installed changed, $skipped already current."
  echo ""
  echo "Status:  launchctl list | grep com.sapphire"
  echo "Logs:    ls -lt $LOG_DIR $AUTONOMY_LOG_DIR"
fi
