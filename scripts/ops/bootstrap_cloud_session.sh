#!/usr/bin/env bash
# Bootstrap a Claude Code on the web / cloud container so the test suite runs.
#
# Why this exists
# ---------------
# A fresh cloud container clones the repo but installs nothing. `pytest
# tests/unit/` then dies with ~42 collection errors (`No module named 'flask'`,
# `No module named '_cffi_backend'`, …). Those look exactly like a broken repo,
# and an agent that trusts them will "fix" tests that were never broken.
#
# Two container-specific failures this handles that a bare
# `pip install -r requirements-test.txt` does not:
#
#   1. Debian's system PyYAML has no RECORD file, so pip cannot uninstall it and
#      aborts the whole resolution:
#        "ERROR: Cannot uninstall PyYAML 6.0.1, RECORD file not found."
#      --ignore-installed PyYAML steps around it.
#   2. Some images ship a Rust-backed cryptography wheel without _cffi_backend,
#      which makes test_robinhood.py abort collection with a pyo3 PanicException
#      rather than a normal ImportError. Installing cffi first avoids it.
#
# Idempotent and safe to re-run. Exits non-zero only if the install itself fails
# — a partially-provisioned container is worse than a loud failure.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PY="${PYTHON:-python3}"

echo "bootstrap: python=$($PY --version 2>&1) at $(command -v "$PY")"

if [[ ! -f requirements-test.txt ]]; then
  echo "bootstrap: requirements-test.txt missing — wrong directory?" >&2
  exit 1
fi

# Fast path: if the suite can already collect, don't spend a minute reinstalling.
if $PY -c "import flask, pandas, numpy, web3, pytest" >/dev/null 2>&1; then
  echo "bootstrap: test dependencies already present — nothing to do"
  exit 0
fi

echo "bootstrap: installing test dependencies (~1-2 min on a cold container)"

# cffi first — see note (2) above.
$PY -m pip install --quiet --disable-pip-version-check cffi >/dev/null 2>&1 || true

# --ignore-installed PyYAML — see note (1) above.
if ! $PY -m pip install --quiet --disable-pip-version-check \
      --ignore-installed PyYAML -r requirements-test.txt; then
  echo "bootstrap: dependency install FAILED — the suite will report phantom" >&2
  echo "bootstrap: collection errors. Fix the install before trusting results." >&2
  exit 1
fi

# Report what the suite can actually see, so a session that skips this script's
# output still has the truth in the transcript.
$PY - <<'PY'
import importlib

required = ["flask", "pandas", "numpy", "scipy", "web3", "pytest", "yaml", "redis"]
missing = [m for m in required if not importlib.util.find_spec(m)]
if missing:
    print(f"bootstrap: WARNING still missing: {', '.join(missing)}")
else:
    print("bootstrap: all core test dependencies importable")
PY

echo "bootstrap: done — run 'python3 -m pytest tests/unit/ -q' to verify"
