#!/usr/bin/env bash
# Backward-compatible entrypoint for operator runbooks and agent skills.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
exec "${SCRIPT_DIR}/ops/check_required_secrets.sh" "$@"
