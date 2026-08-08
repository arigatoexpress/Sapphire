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

exec "$PYTHON_BIN" "$SCRIPT_DIR/grok_web_import.py" "$@"
