#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${DOMAIN:-https://sapphirealpha.xyz}"
AUTH_USER="${AUTH_USER:-sapphire}"
AUTH_PASS="${AUTH_PASS:-alpha2024}"
USE_HTTP_AUTH="${USE_HTTP_AUTH:-false}"
UPDATE_BASELINES="${UPDATE_BASELINES:-false}"
MAX_DIFF_PERCENT="${MAX_DIFF_PERCENT:-1.2}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASELINE_DIR="${BASELINE_DIR:-${ROOT_DIR}/tests/visual-baseline/public_frontend}"
CURRENT_DIR="$(mktemp -d)"
REPORT_DIR="${REPORT_DIR:-${ROOT_DIR}/output/frontend-visual-report}"

FAILURES=0

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILURES=$((FAILURES + 1)); }

need_cmd() {
  local cmd="$1"
  if command -v "$cmd" >/dev/null 2>&1; then
    pass "command available: $cmd"
  else
    fail "missing command: $cmd"
  fi
}

need_cmd node
need_cmd python3

echo "== Frontend Visual Regression =="
echo "domain=${DOMAIN}"
echo "baseline_dir=${BASELINE_DIR}"
echo "max_diff_percent=${MAX_DIFF_PERCENT}"

mkdir -p "$BASELINE_DIR" "$REPORT_DIR"

(
  cd "${ROOT_DIR}/sapphire-web"
  if [[ "${USE_HTTP_AUTH}" == "true" ]]; then
    node ../scripts/frontend_visual_capture.mjs "$DOMAIN" "$CURRENT_DIR" "$AUTH_USER" "$AUTH_PASS"
  else
    node ../scripts/frontend_visual_capture.mjs "$DOMAIN" "$CURRENT_DIR" "" ""
  fi
)

if [[ "${UPDATE_BASELINES}" == "true" ]]; then
  cp -f "$CURRENT_DIR"/*.png "$BASELINE_DIR"/
  pass "baselines updated from current capture"
  echo "Baselines refreshed in ${BASELINE_DIR}"
  exit 0
fi

if [[ ! -f "${BASELINE_DIR}/overview.png" || ! -f "${BASELINE_DIR}/architecture.png" ]]; then
  fail "baseline screenshots missing; run with UPDATE_BASELINES=true once"
  echo "Expected: ${BASELINE_DIR}/overview.png and ${BASELINE_DIR}/architecture.png"
  exit 1
fi

python3 - <<'PY' "$BASELINE_DIR" "$CURRENT_DIR" "$REPORT_DIR" "$MAX_DIFF_PERCENT"
import pathlib
import sys
from PIL import Image, ImageChops

baseline_dir = pathlib.Path(sys.argv[1])
current_dir = pathlib.Path(sys.argv[2])
report_dir = pathlib.Path(sys.argv[3])
max_diff_percent = float(sys.argv[4])
report_dir.mkdir(parents=True, exist_ok=True)

targets = ["overview", "architecture"]
failed = False

for name in targets:
    b = baseline_dir / f"{name}.png"
    c = current_dir / f"{name}.png"
    d = report_dir / f"{name}.diff.png"
    if not b.exists() or not c.exists():
        print(f"FAIL: missing image for {name}")
        failed = True
        continue

    bi = Image.open(b).convert("RGBA")
    ci = Image.open(c).convert("RGBA")
    if bi.size != ci.size:
        print(f"FAIL: {name} size mismatch baseline={bi.size} current={ci.size}")
        failed = True
        continue

    diff = ImageChops.difference(bi, ci)
    gray = diff.convert("L")
    raw = gray.tobytes()
    changed = 0
    total = bi.size[0] * bi.size[1]
    threshold = 20
    for v in raw:
        if v > threshold:
            changed += 1

    pct = (changed / max(total, 1)) * 100.0
    diff.save(d)
    if pct > max_diff_percent:
        print(f"FAIL: {name} changed_pixels={pct:.3f}% (max {max_diff_percent:.3f}%) diff={d}")
        failed = True
    else:
        print(f"PASS: {name} changed_pixels={pct:.3f}% (max {max_diff_percent:.3f}%)")

if failed:
    sys.exit(1)
PY
if [[ "$?" -ne 0 ]]; then
  fail "visual regression threshold exceeded"
else
  pass "visual regression within thresholds"
fi

if [[ "$FAILURES" -gt 0 ]]; then
  echo
  echo "frontend visual regression FAILED with ${FAILURES} issue(s)."
  exit 1
fi

echo
echo "frontend visual regression PASSED."
