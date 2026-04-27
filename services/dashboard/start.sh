#!/bin/bash
# Startup wrapper for the dashboard LaunchAgent.
set -euo pipefail

SECRETS_FILE="$HOME/.sapphire/secrets.env"

if [ -f "$SECRETS_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$SECRETS_FILE"
    set +a
fi

exec /usr/local/bin/python3 app.py
