#!/usr/bin/env bash
# Compatibility entrypoint for the hash-addressed Grok web importer.
#
# `--pull` remains accepted by grok_web_import.py only as a deprecated alias for
# one exact `origin/main` fetch. The importer never merges, checks out, or reads
# export bytes from this working tree.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${GROK_IMPORT_PYTHON:-/opt/homebrew/bin/python3}"

exec "$PYTHON_BIN" "$SCRIPT_DIR/grok_web_import.py" "$@"
