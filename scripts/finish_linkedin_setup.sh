#!/usr/bin/env bash
# finish_linkedin_setup.sh — called after Ari completes the LinkedIn dev app
# flow and has an access token in hand.
#
# What it does:
#   1. Asks for the access token (doesn't echo it).
#   2. Calls /v2/userinfo to verify the token and get the user's sub (→ URN).
#   3. Writes LINKEDIN_ACCESS_TOKEN + LINKEDIN_AUTHOR_URN into .env.integrations
#      (updating existing lines in place; never appending duplicates).
#   4. Re-runs the LinkedIn smoke probe to confirm PASS.
#
# Usage:
#   scripts/finish_linkedin_setup.sh
#   # OR pass the token via env so you can paste it once:
#   LINKEDIN_ACCESS_TOKEN=AQV... scripts/finish_linkedin_setup.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env.integrations"

[[ -f "$ENV_FILE" ]] || { echo "missing $ENV_FILE" >&2; exit 1; }

if [[ -z "${LINKEDIN_ACCESS_TOKEN:-}" ]]; then
    read -r -s -p "Paste LinkedIn access token (input hidden): " LINKEDIN_ACCESS_TOKEN
    echo
fi

[[ -n "${LINKEDIN_ACCESS_TOKEN}" ]] || { echo "no token provided" >&2; exit 1; }

echo "→ verifying token against /v2/userinfo ..."
USERINFO="$(curl -sS -H "Authorization: Bearer $LINKEDIN_ACCESS_TOKEN" \
    https://api.linkedin.com/v2/userinfo)"

if ! SUB="$(echo "$USERINFO" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('sub',''))")" \
   || [[ -z "$SUB" ]]; then
    echo "error: token rejected or /v2/userinfo response had no 'sub'" >&2
    echo "response: $USERINFO" >&2
    exit 2
fi

NAME="$(echo "$USERINFO" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('name','(no name)'))")"
URN="urn:li:person:$SUB"

echo "  authenticated as: $NAME"
echo "  author URN:       $URN"
echo

# Update .env.integrations in place (portable sed — works on BSD + GNU)
python3 - "$ENV_FILE" "$LINKEDIN_ACCESS_TOKEN" "$URN" <<'PY'
import sys, pathlib
path, token, urn = sys.argv[1], sys.argv[2], sys.argv[3]
text = pathlib.Path(path).read_text()
lines = text.splitlines()
out = []
seen_token = seen_urn = False
for ln in lines:
    if ln.startswith("LINKEDIN_ACCESS_TOKEN="):
        out.append(f"LINKEDIN_ACCESS_TOKEN={token}")
        seen_token = True
    elif ln.startswith("LINKEDIN_AUTHOR_URN="):
        out.append(f"LINKEDIN_AUTHOR_URN={urn}")
        seen_urn = True
    else:
        out.append(ln)
if not seen_token:
    out.append(f"LINKEDIN_ACCESS_TOKEN={token}")
if not seen_urn:
    out.append(f"LINKEDIN_AUTHOR_URN={urn}")
pathlib.Path(path).write_text("\n".join(out) + "\n")
print(f"  wrote LINKEDIN_ACCESS_TOKEN + LINKEDIN_AUTHOR_URN to {path}")
PY

chmod 600 "$ENV_FILE"

# Reload into launchd if the helper exists (Mac only)
if [[ -x "$REPO_ROOT/scripts/load_integrations_env.sh" ]] && command -v launchctl >/dev/null 2>&1; then
    echo "→ reloading launchd env"
    bash "$REPO_ROOT/scripts/load_integrations_env.sh" >/dev/null
fi

echo "→ re-running LinkedIn smoke probe"
python3 "$REPO_ROOT/scripts/smoke_integrations.py" linkedin
