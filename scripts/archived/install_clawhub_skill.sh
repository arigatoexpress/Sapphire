#!/usr/bin/env bash
set -euo pipefail

SKILL_SLUG="${1:-}"
WORKDIR="${WORKDIR:-$HOME/.openclaw/workspace}"
SKILLS_DIR="${SKILLS_DIR:-skills}"
MAX_RETRIES="${MAX_RETRIES:-3}"

if [[ -z "${SKILL_SLUG}" ]]; then
  echo "Usage: $0 <skill-slug>"
  exit 2
fi

if ! command -v node >/dev/null 2>&1 || ! command -v npx >/dev/null 2>&1; then
  echo "Node.js + npx are required."
  exit 1
fi

mkdir -p "${WORKDIR}"
cd "${WORKDIR}"

if ! npx clawhub@latest whoami --no-input >/dev/null 2>&1; then
  echo "ClawHub auth is required first."
  echo "Run: npx clawhub@latest login"
  exit 3
fi

attempt=1
while (( attempt <= MAX_RETRIES )); do
  if npx clawhub@latest install "${SKILL_SLUG}" --workdir "${WORKDIR}" --dir "${SKILLS_DIR}" --no-input; then
    echo "Installed skill: ${SKILL_SLUG}"
    exit 0
  fi
  echo "Install attempt ${attempt}/${MAX_RETRIES} failed; retrying..."
  sleep $((attempt * 2))
  ((attempt++))
done

echo "Failed to install skill after ${MAX_RETRIES} attempts."
exit 1
