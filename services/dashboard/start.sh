#!/bin/bash
# Startup wrapper for the dashboard LaunchAgent.
set -euo pipefail

SECRETS_FILE="$HOME/.sapphire/secrets.env"
DASHBOARD_PASSWORD_FILE="$HOME/.config/sapphire-secrets/dashboard_password"

if [ -f "$SECRETS_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$SECRETS_FILE"
    set +a
fi

if [ -f "$DASHBOARD_PASSWORD_FILE" ]; then
    AUTH_PASSWORD="$(tr -d '\r\n' < "$DASHBOARD_PASSWORD_FILE")"
    export AUTH_PASSWORD
fi

exec /usr/local/bin/python3 app.py
