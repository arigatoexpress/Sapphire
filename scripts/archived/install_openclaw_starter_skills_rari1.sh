#!/usr/bin/env bash
set -euo pipefail

SRC_ROOT="${SRC_ROOT:-/mnt/ssd/openclaw/skills}"
DEST_ROOT="${DEST_ROOT:-/home/rari/.openclaw/workspace/skills}"
LOCKFILE="${LOCKFILE:-/home/rari/.openclaw/workspace/.clawhub/lock.json}"
STAMP_MS="$(python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
)"

# Practical starter pack for the Pi operator bot.
STARTER_SKILLS=(
  summarize
  github
  clawhub
  healthcheck
  session-logs
  tmux
)

mkdir -p "${DEST_ROOT}"
mkdir -p "$(dirname "${LOCKFILE}")"

for skill in "${STARTER_SKILLS[@]}"; do
  if [[ ! -d "${SRC_ROOT}/${skill}" ]]; then
    echo "missing source skill: ${skill}" >&2
    exit 1
  fi
  rm -rf "${DEST_ROOT:?}/${skill}"
  cp -R "${SRC_ROOT}/${skill}" "${DEST_ROOT}/${skill}"
  cat > "${DEST_ROOT}/${skill}/_meta.json" <<JSON
{
  "ownerId": "local-openclaw",
  "slug": "${skill}",
  "version": "local",
  "publishedAt": ${STAMP_MS}
}
JSON
  echo "installed ${skill}"
done

LOCKFILE="${LOCKFILE}" STAMP_MS="${STAMP_MS}" python3 - <<'PY'
import json
import os
from pathlib import Path

lock_path = Path(os.environ["LOCKFILE"])
stamp = int(os.environ["STAMP_MS"])
starter_skills = ["summarize", "github", "clawhub", "healthcheck", "session-logs", "tmux"]

data = {"version": 1, "skills": {}}
if lock_path.exists():
    try:
        data = json.loads(lock_path.read_text())
    except Exception:
        data = {"version": 1, "skills": {}}

skills = data.setdefault("skills", {})
for slug in starter_skills:
    entry = skills.get(slug, {})
    entry["version"] = entry.get("version") or "local"
    entry["installedAt"] = stamp
    skills[slug] = entry

lock_path.write_text(json.dumps(data, indent=2) + "\n")
PY

echo "starter skills synced into ${DEST_ROOT}"
