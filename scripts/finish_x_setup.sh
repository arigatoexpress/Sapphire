#!/usr/bin/env bash
# finish_x_setup.sh — called after Ari regenerates X (Twitter) OAuth 1.0a
# tokens with Read+Write scope and copies them out of the dev console.
#
# What it does:
#   1. Prompts for the four OAuth 1.0a tokens (input hidden) + optional bearer.
#   2. Verifies the bearer (if provided) against /2/users/me.
#   3. Writes all five vars into .env.integrations in place.
#   4. Re-runs the X smoke probe.
#
# Usage:
#   scripts/finish_x_setup.sh
#   # OR pre-fill all five via env to skip the prompts:
#   X_API_KEY=... X_API_SECRET=... X_ACCESS_TOKEN=... X_ACCESS_SECRET=... \
#     X_BEARER_TOKEN=... scripts/finish_x_setup.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env.integrations"

[[ -f "$ENV_FILE" ]] || { echo "missing $ENV_FILE" >&2; exit 1; }

prompt_secret() {
    local var="$1" label="$2"
    if [[ -z "${!var:-}" ]]; then
        read -r -s -p "$label (hidden): " VAL
        echo
        printf -v "$var" '%s' "$VAL"
    fi
}

prompt_secret X_API_KEY        "X_API_KEY (consumer key)"
prompt_secret X_API_SECRET     "X_API_SECRET (consumer secret)"
prompt_secret X_ACCESS_TOKEN   "X_ACCESS_TOKEN"
prompt_secret X_ACCESS_SECRET  "X_ACCESS_SECRET"
if [[ -z "${X_BEARER_TOKEN:-}" ]]; then
    read -r -s -p "X_BEARER_TOKEN (optional, hidden — empty to skip): " X_BEARER_TOKEN
    echo
fi

# Verify bearer if provided
if [[ -n "$X_BEARER_TOKEN" ]]; then
    echo "→ verifying bearer token against /2/users/me ..."
    RESP="$(curl -sS -H "Authorization: Bearer $X_BEARER_TOKEN" \
        https://api.twitter.com/2/users/me)"
    if echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('data') else 1)" 2>/dev/null; then
        HANDLE="$(echo "$RESP" | python3 -c "import json,sys; print(json.load(sys.stdin)['data'].get('username','?'))")"
        echo "  authenticated as: @$HANDLE"
    else
        echo "  warning: bearer verification failed (response: $RESP)" >&2
        echo "  continuing — OAuth 1.0a quartet may still work for posting" >&2
    fi
fi

# Update .env.integrations in place
python3 - "$ENV_FILE" "$X_API_KEY" "$X_API_SECRET" "$X_ACCESS_TOKEN" "$X_ACCESS_SECRET" "$X_BEARER_TOKEN" <<'PY'
import sys, pathlib
path, key, secret, atoken, asecret, bearer = sys.argv[1:7]
text = pathlib.Path(path).read_text()
lines = text.splitlines()
out = []
written = {"X_API_KEY": False, "X_API_SECRET": False,
           "X_ACCESS_TOKEN": False, "X_ACCESS_SECRET": False,
           "X_BEARER_TOKEN": False}
values = {"X_API_KEY": key, "X_API_SECRET": secret,
          "X_ACCESS_TOKEN": atoken, "X_ACCESS_SECRET": asecret,
          "X_BEARER_TOKEN": bearer}
for ln in lines:
    matched = False
    for k in written:
        if ln.startswith(f"{k}="):
            out.append(f"{k}={values[k]}")
            written[k] = True
            matched = True
            break
    if not matched:
        out.append(ln)
for k, done in written.items():
    if not done:
        out.append(f"{k}={values[k]}")
pathlib.Path(path).write_text("\n".join(out) + "\n")
print(f"  wrote X_* vars to {path}")
PY

chmod 600 "$ENV_FILE"

if [[ -x "$REPO_ROOT/scripts/load_integrations_env.sh" ]] && command -v launchctl >/dev/null 2>&1; then
    echo "→ reloading launchd env"
    bash "$REPO_ROOT/scripts/load_integrations_env.sh" >/dev/null
fi

echo "→ re-running X smoke probe"
python3 "$REPO_ROOT/scripts/smoke_integrations.py" x
