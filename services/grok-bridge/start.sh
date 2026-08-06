#!/bin/bash
# Startup wrapper for grok-bridge — loads secrets from ~/.sapphire/secrets.env
# and exec's into the Python process.
#
# Uses /opt/homebrew/bin/python3 directly: /usr/local/bin/python3 (framework
# build) is known to hang on this Mac (see CLAUDE.md Gotchas), unlike the
# other services' start.sh which still try it first.
set -euo pipefail

SECRETS_FILE="$HOME/.sapphire/secrets.env"

if [ -f "$SECRETS_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$SECRETS_FILE"
    set +a
fi

exec /opt/homebrew/bin/python3 "$(dirname "$0")/app.py" "$@"
