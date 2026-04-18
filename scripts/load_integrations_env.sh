#!/usr/bin/env bash
# Sapphire OS — Load .env.integrations into the launchd GUI session.
#
# LaunchAgents don't read ~/.env or dotenv files — they inherit env from
# launchd.  Run this once per boot (or after updating .env.integrations)
# so com.sapphire.content-publisher + other agents can see the creds.
#
# Usage:
#   scripts/load_integrations_env.sh                     # uses repo root .env.integrations
#   scripts/load_integrations_env.sh /path/to/env.file   # explicit path
#   scripts/load_integrations_env.sh --unset             # wipe all keys we'd set (safe reset)
#
# Behaviour:
#   - Parses KEY=VALUE lines; skips blanks and `#` comments.
#   - Strips surrounding single/double quotes from values.
#   - SKIPS keys with empty values (so an un-filled placeholder never
#     clobbers a previously-set value).
#   - Refuses to run if the file is world-readable (chmod 600 required).
#   - Reports a summary: N loaded, M skipped, plus which keys were blank.
#
# Exit codes:
#   0  success (or --unset)
#   1  file missing / unreadable
#   2  file permissions too open

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_ENV_FILE="${REPO_ROOT}/.env.integrations"

# -------- helpers ---------------------------------------------------------

die() { echo "error: $*" >&2; exit "${2:-1}"; }

strip_quotes() {
    local v="$1"
    # strip matching surrounding " or ' (but not mismatched)
    if [[ ${#v} -ge 2 && "${v:0:1}" == '"' && "${v: -1}" == '"' ]]; then
        v="${v:1:-1}"
    elif [[ ${#v} -ge 2 && "${v:0:1}" == "'" && "${v: -1}" == "'" ]]; then
        v="${v:1:-1}"
    fi
    printf '%s' "$v"
}

# Collect the key list once from the example file so --unset knows the
# full surface area without needing a filled .env.integrations.
collect_keys_from_example() {
    local example="${REPO_ROOT}/.env.integrations.example"
    [[ -f "$example" ]] || return 0
    awk -F= '/^[A-Z][A-Z0-9_]*=/ {print $1}' "$example"
}

# -------- unset mode ------------------------------------------------------

if [[ "${1:-}" == "--unset" ]]; then
    echo "Unsetting all .env.integrations keys from launchd GUI session..."
    count=0
    while read -r key; do
        [[ -z "$key" ]] && continue
        launchctl unsetenv "$key" || true
        count=$((count + 1))
    done < <(collect_keys_from_example)
    echo "Unset $count keys."
    exit 0
fi

# -------- load mode -------------------------------------------------------

ENV_FILE="${1:-$DEFAULT_ENV_FILE}"

[[ -f "$ENV_FILE" ]] || die "env file not found: $ENV_FILE
   Copy .env.integrations.example → .env.integrations and fill in values."

if [[ ! -r "$ENV_FILE" ]]; then
    die "env file not readable: $ENV_FILE"
fi

# File must not be world- or group-readable — these are secrets.
# macOS stat differs from GNU stat; try BSD form first.
if perms=$(stat -f '%Lp' "$ENV_FILE" 2>/dev/null); then
    :
else
    perms=$(stat -c '%a' "$ENV_FILE")
fi
# Allow 600, 400; reject anything with group/other bits.
if [[ "$perms" != "600" && "$perms" != "400" ]]; then
    die "refusing to load $ENV_FILE with mode $perms — run: chmod 600 $ENV_FILE" 2
fi

echo "Loading $ENV_FILE into launchd GUI session..."
loaded=0
skipped_blank=0
skipped_comment=0
blank_keys=()

while IFS= read -r line || [[ -n "$line" ]]; do
    # trim leading/trailing whitespace
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"

    # skip comments and blanks
    if [[ -z "$line" ]]; then
        continue
    fi
    if [[ "$line" == \#* ]]; then
        skipped_comment=$((skipped_comment + 1))
        continue
    fi

    # must look like KEY=VALUE
    if [[ "$line" != *=* ]]; then
        continue
    fi

    key="${line%%=*}"
    value="${line#*=}"

    # validate key: uppercase, digits, underscore, must start with letter
    if [[ ! "$key" =~ ^[A-Z][A-Z0-9_]*$ ]]; then
        continue
    fi

    value="$(strip_quotes "$value")"

    if [[ -z "$value" ]]; then
        skipped_blank=$((skipped_blank + 1))
        blank_keys+=("$key")
        continue
    fi

    launchctl setenv "$key" "$value"
    loaded=$((loaded + 1))
done < "$ENV_FILE"

echo
echo "  loaded:  $loaded keys"
echo "  blank:   $skipped_blank keys (skipped, not overwritten)"

if [[ ${#blank_keys[@]} -gt 0 ]]; then
    echo
    echo "Keys still blank in $ENV_FILE:"
    printf '  - %s\n' "${blank_keys[@]}"
fi

echo
echo "Kickstart affected agents to pick up the new env, e.g.:"
echo "  launchctl kickstart -k gui/\$(id -u)/com.sapphire.content-publisher"
