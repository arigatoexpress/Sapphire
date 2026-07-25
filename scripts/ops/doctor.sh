#!/usr/bin/env bash
# Sapphire OS — dev environment health check.
# Reports PASS/WARN/FAIL for toolchain, services, and common foot-guns.
# Read-only: never mutates state.

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

PASS=0 WARN=0 FAIL=0
C_RED=$'\e[31m'; C_GRN=$'\e[32m'; C_YLW=$'\e[33m'; C_DIM=$'\e[2m'; C_BLD=$'\e[1m'; C_RST=$'\e[0m'

pass() { echo "  ${C_GRN}✓${C_RST} $*"; PASS=$((PASS+1)); }
warn() { echo "  ${C_YLW}!${C_RST} $*"; WARN=$((WARN+1)); }
fail() { echo "  ${C_RED}✗${C_RST} $*"; FAIL=$((FAIL+1)); }
info() { echo "  ${C_DIM}·${C_RST} $*"; }
section() { echo ""; echo "${C_BLD}$*${C_RST}"; }

have() { command -v "$1" >/dev/null 2>&1; }

section "Toolchain"

if have /usr/local/bin/python3; then
  v=$(/usr/local/bin/python3 -V 2>&1)
  pass "/usr/local/bin/python3 (${v})"
else
  fail "/usr/local/bin/python3 missing — CLAUDE.md expects this path on Mac"
fi

if have python3; then
  v=$(python3 -V 2>&1)
  case "${v}" in
    *3.14*) warn "\`python3\` resolves to ${v} (brew 3.14 often lacks pytest) — use /usr/local/bin/python3" ;;
    *)      pass "\`python3\` ${v}" ;;
  esac
else
  fail "python3 not on PATH"
fi

for tool in ruff pytest pre-commit gh git node npm; do
  if have "${tool}"; then
    pass "${tool} ($(${tool} --version 2>&1 | head -1))"
  else
    warn "${tool} not installed"
  fi
done

section "Project config"

for f in pyproject.toml .pre-commit-config.yaml .editorconfig .gitignore .gitattributes Makefile; do
  [[ -f "${f}" ]] && pass "${f}" || fail "missing ${f}"
done

if [[ -d .github/workflows ]]; then
  n=$(find .github/workflows -name "*.yml" | wc -l | tr -d ' ')
  pass ".github/workflows (${n} workflow(s))"
else
  fail ".github/workflows missing"
fi

if [[ -f .flake8 ]]; then
  warn ".flake8 present — redundant with ruff in pyproject.toml"
fi

section "Lint + tests"

if have ruff; then
  if ruff check --no-cache >/dev/null 2>&1; then
    pass "ruff check — clean"
  else
    errs=$(ruff check --no-cache 2>&1 | tail -3 | head -1)
    fail "ruff check — ${errs}"
  fi
else
  warn "ruff not installed; skipping lint"
fi

section "Secrets / data hygiene"

if [[ -d ~/.config/sapphire-secrets ]]; then
  perms=$(stat -f %Lp ~/.config/sapphire-secrets 2>/dev/null || stat -c %a ~/.config/sapphire-secrets 2>/dev/null)
  case "${perms}" in
    700) pass "~/.config/sapphire-secrets (perms ${perms})" ;;
    *)   warn "~/.config/sapphire-secrets perms ${perms} — expected 700" ;;
  esac
else
  warn "~/.config/sapphire-secrets not found — robinhood/foundry integrations will fail"
fi

if git ls-files --error-unmatch .env 2>/dev/null; then
  fail ".env is tracked in git — should be gitignored"
else
  pass ".env not tracked"
fi

if git ls-files | grep -qE "(migrated_customers\.json|trading_signals\.jsonl)$" 2>/dev/null; then
  fail "PII/trading file tracked in git"
else
  pass "no PII/trading files in git"
fi

section "Local services (probe; not fatal)"

probe_url() {
  local url="$1" label="$2"
  if curl -fsS -m 2 "${url}" >/dev/null 2>&1; then
    pass "${label} (${url})"
  else
    info "${label} not responding at ${url}"
  fi
}

probe_url "http://127.0.0.1:8080/healthz" "dashboard :8080"
probe_url "http://127.0.0.1:8082/healthz" "control-plane :8082"
probe_url "http://127.0.0.1:11435/health" "inference-proxy :11435"
probe_url "http://127.0.0.1:11434/api/version" "ollama :11434"
probe_url "http://127.0.0.1:6900/api/v1/" "openbb :6900"

if have redis-cli; then
  if redis-cli ping >/dev/null 2>&1; then
    pass "redis :6379"
  else
    info "redis not responding (event bus will fall back to JSONL)"
  fi
fi

section "LaunchAgents"

if have launchctl; then
  n=$(launchctl list 2>/dev/null | grep -c "com.sapphire" || true)
  if [[ "${n}" -gt 0 ]]; then
    pass "${n} com.sapphire LaunchAgent(s) loaded"
  else
    info "no com.sapphire LaunchAgents loaded"
  fi
fi

if [[ -d infra/launchagents ]]; then
  n=$(find infra/launchagents -name "*.plist" -not -name "*.disabled" | wc -l | tr -d ' ')
  pass "${n} enabled plist(s) on disk"
fi

section "Data freshness"

if have python3 && [[ -f infra/staleness-thresholds.yaml ]]; then
  # scripts/ops/staleness_monitor.py owns the config; exit=2 means at least one
  # STALE, exit=0 all-clear. We echo one line per stale/missing target only.
  stale_out=$(python3 scripts/ops/staleness_monitor.py --stale-only 2>&1 || true)
  # Header row is always emitted; if only the header came back, everything is FRESH.
  if [[ "$(echo "${stale_out}" | wc -l | tr -d ' ')" -le 1 ]]; then
    pass "all watched data files within threshold"
  else
    echo "${stale_out}" | tail -n +2 | while IFS= read -r line; do
      # STALE = fail-worthy; MISSING = optional target absent, informational.
      case "${line}" in
        *STALE*)   fail "staleness: ${line}" ;;
        *MISSING*) info  "missing (optional): ${line}" ;;
      esac
    done
  fi
else
  info "staleness monitor unavailable (no python3 or config)"
fi

section "Git"

branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
ahead=$(git rev-list --count @{u}.. 2>/dev/null || echo "0")
behind=$(git rev-list --count ..@{u} 2>/dev/null || echo "0")
info "branch: ${branch} (ahead ${ahead}, behind ${behind})"

if [[ -z "$(git status --porcelain)" ]]; then
  pass "clean working tree"
else
  n=$(git status --porcelain | wc -l | tr -d ' ')
  info "${n} uncommitted change(s)"
fi

stale=$(git for-each-ref --sort=-committerdate --format='%(refname:short) %(committerdate:unix)' refs/heads/ | awk -v cutoff=$(( $(date +%s) - 60*60*24*30 )) '$2 < cutoff {print $1}' | wc -l | tr -d ' ')
if [[ "${stale}" -gt 5 ]]; then
  warn "${stale} local branch(es) not committed-to in 30+ days — consider cleanup"
else
  info "stale-branch count: ${stale}"
fi

section "Summary"
echo "  ${C_GRN}PASS ${PASS}${C_RST}    ${C_YLW}WARN ${WARN}${C_RST}    ${C_RED}FAIL ${FAIL}${C_RST}"
[[ "${FAIL}" -gt 0 ]] && exit 1 || exit 0
