#!/bin/bash
# Startup wrapper for inference-proxy — loads secrets from ~/.sapphire/secrets.env
# and exec's into the Python process.
set -euo pipefail

SECRETS_FILE="$HOME/.sapphire/secrets.env"

if [ -f "$SECRETS_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$SECRETS_FILE"
    set +a
fi

# Fix SSL certificate verification for /usr/local/bin/python3
export SSL_CERT_FILE="/Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12/site-packages/certifi/cacert.pem"
export REQUESTS_CA_BUNDLE="/Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12/site-packages/certifi/cacert.pem"

# Use /usr/local/bin/python3 (3.12, consistent with all other Sapphire services)
# Falls back to /opt/homebrew/bin/python3 if not available
if [ -x "/usr/local/bin/python3" ]; then
    exec /usr/local/bin/python3 "$(dirname "$0")/app.py" "$@"
else
    exec /opt/homebrew/bin/python3 "$(dirname "$0")/app.py" "$@"
fi
