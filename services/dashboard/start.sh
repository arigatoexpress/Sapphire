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

if [ -z "${AUTH_PASSWORD:-}" ]; then
    echo "dashboard: AUTH_PASSWORD unset — app.py rejects a missing/weak password at import." >&2
    echo "dashboard: expected $DASHBOARD_PASSWORD_FILE or AUTH_PASSWORD in $SECRETS_FILE" >&2
    exit 78  # EX_CONFIG — a misconfiguration, not a transient crash.
fi

# Pin the interpreter but do not hard-depend on it: a python3 that is absent or
# broken on one machine should degrade to the other, not take the service down.
if [ -x "/usr/local/bin/python3" ]; then
    exec /usr/local/bin/python3 app.py
else
    exec /opt/homebrew/bin/python3 app.py
fi
