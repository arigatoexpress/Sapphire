#!/usr/bin/env bash
# Compatibility entrypoint for the hash-addressed Grok web importer.
#
# `--pull` remains accepted by grok_web_import.py only as a deprecated alias for
# one exact `origin/main` fetch. The importer never merges, checks out, or reads
# export bytes from this working tree.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -n "${GROK_IMPORT_PYTHON:-}" ]]; then
  PYTHON_BIN="$GROK_IMPORT_PYTHON"
elif ! PYTHON_BIN="$(command -v python3)"; then
  echo "grok-web-import: python3 not found" >&2
  exit 127
fi

LEGACY_ARGS=()
if [[ -n "${SAPPHIRE_DIR:-}" ]]; then
  LEGACY_ARGS+=(--repo "$SAPPHIRE_DIR")
fi
if [[ -n "${KNOWLEDGE_INBOX:-}" ]]; then
  LEGACY_ARGS+=(--destination "$KNOWLEDGE_INBOX")
fi

LOG_DIR="${SAPPHIRE_BRIDGE_LOG_DIR:-$HOME/ops-state/logs}"
LOG_FILE="$LOG_DIR/grok-web-bridge.log"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

set +e
IMPORT_OUTPUT="$("$PYTHON_BIN" "$SCRIPT_DIR/grok_web_import.py" "${LEGACY_ARGS[@]}" "$@" 2>&1)"
IMPORT_STATUS=$?
set -e

if [[ "$IMPORT_STATUS" -eq 0 ]]; then
  printf '%s\n' "$IMPORT_OUTPUT"
else
  printf '%s\n' "$IMPORT_OUTPUT" >&2
fi

if [[ -d "$LOG_DIR" ]] || mkdir -m 700 -p "$LOG_DIR" 2>/dev/null; then
  LOG_OUTPUT="${IMPORT_OUTPUT//$'\n'/ }"
  printf '%s exit=%d %s\n' "$STAMP" "$IMPORT_STATUS" "$LOG_OUTPUT" >>"$LOG_FILE" || true
fi

exit "$IMPORT_STATUS"
