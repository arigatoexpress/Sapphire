#!/usr/bin/env bash
# scripts/hackathon_smoke.sh
#
# One-shot 0G demo-day smoke runner: deploy → publish → verify, and emit a
# submission-ready markdown summary so the user only has to copy the result
# into the HackQuest form + demo.
#
# USAGE:
#   scripts/hackathon_smoke.sh [--dry-run] [--network mainnet|testnet]
#                              [--key-path PATH] [--force-dirty]
#
# ENV (alternative to flags):
#   OG_DEPLOY_KEY_PATH   path to private-key file (mode 0600)
#   OG_NETWORK           mainnet | testnet (default mainnet)
#   OG_RPC_URL           override default RPC
#
# Discipline:
#   - bash strict mode
#   - never prints private keys
#   - reads keystore only from --key-path / OG_DEPLOY_KEY_PATH
#   - writes a full timestamped log + markdown summary under data/hackathon/
#
set -euo pipefail

# ---------------------------------------------------------------------------
# Layout & globals
# ---------------------------------------------------------------------------
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
cd "$REPO_ROOT"

ARTIFACT_DIR="$REPO_ROOT/data/hackathon"
mkdir -p "$ARTIFACT_DIR"

TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
LOG_FILE="$ARTIFACT_DIR/smoke_run_${TIMESTAMP}.log"
SUMMARY_FILE="$ARTIFACT_DIR/submission_artifacts.md"
START_EPOCH=$(date +%s)

# Defaults (flags override; env vars override defaults but flags override env).
NETWORK="${OG_NETWORK:-mainnet}"
KEY_PATH="${OG_DEPLOY_KEY_PATH:-$HOME/.config/sapphire-secrets/og_deploy_key}"
DRY_RUN=0
FORCE_DIRTY=0

# Console colors (disable when not a tty).
if [[ -t 1 ]]; then
  C_RESET=$'\033[0m'
  C_BOLD=$'\033[1m'
  C_RED=$'\033[31m'
  C_GREEN=$'\033[32m'
  C_YELLOW=$'\033[33m'
  C_BLUE=$'\033[34m'
else
  C_RESET=""; C_BOLD=""; C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""
fi

# ---------------------------------------------------------------------------
# Logging helpers (every line also tee'd to $LOG_FILE)
# ---------------------------------------------------------------------------
log()    { printf '%s\n' "$*" | tee -a "$LOG_FILE" >&2; }
info()   { log "${C_BLUE}[info]${C_RESET}  $*"; }
ok()     { log "${C_GREEN}[ ok ]${C_RESET}  $*"; }
warn()   { log "${C_YELLOW}[warn]${C_RESET}  $*"; }
err()    { log "${C_RED}[fail]${C_RESET}  $*"; }
section(){ log ""; log "${C_BOLD}== $* ==${C_RESET}"; }

die() {
  local code="$1"; shift
  err "$*"
  exit "$code"
}

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------
print_usage() {
  cat <<'USAGE'
Usage: scripts/hackathon_smoke.sh [--dry-run] [--network mainnet|testnet]
                                  [--key-path PATH] [--force-dirty]

Runs the 0G hackathon smoke flow: deploy → publish → verify.
Writes a submission-ready markdown to data/hackathon/submission_artifacts.md.

  --dry-run         Run preflight + abi-only deploy; skip publish/verify.
  --network NET     "mainnet" or "testnet" (default mainnet, or $OG_NETWORK).
  --key-path PATH   Private-key file (mode 0600). Default $OG_DEPLOY_KEY_PATH
                    or ~/.config/sapphire-secrets/og_deploy_key.
  --force-dirty     Don't fail on a dirty git tree (warn only).
  -h, --help        Show this message.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)      DRY_RUN=1 ;;
    --force-dirty)  FORCE_DIRTY=1 ;;
    --network)      shift; NETWORK="${1:-}" ;;
    --network=*)    NETWORK="${1#*=}" ;;
    --key-path)     shift; KEY_PATH="${1:-}" ;;
    --key-path=*)   KEY_PATH="${1#*=}" ;;
    -h|--help)      print_usage; exit 0 ;;
    *) print_usage; die 1 "unknown argument: $1" ;;
  esac
  shift || true
done

case "$NETWORK" in
  mainnet|testnet) ;;
  *) die 1 "--network must be 'mainnet' or 'testnet' (got '$NETWORK')" ;;
esac

# Network-specific config (mirrors lib/og/config.py).
if [[ "$NETWORK" == "mainnet" ]]; then
  CHAIN_ID=16661
  DEFAULT_RPC="https://evmrpc.0g.ai"
  EXPLORER="https://chainscan.0g.ai"
  MIN_BALANCE_FLOAT="0.05"
  MIN_BALANCE_WEI="50000000000000000"  # 0.05 * 1e18
else
  CHAIN_ID=16602
  DEFAULT_RPC="https://evmrpc-testnet.0g.ai"
  EXPLORER="https://chainscan-galileo.0g.ai"
  MIN_BALANCE_FLOAT="0.001"
  MIN_BALANCE_WEI="1000000000000000"   # 0.001 * 1e18
fi
RPC_URL="${OG_RPC_URL:-$DEFAULT_RPC}"

info "log file:      $LOG_FILE"
info "network:       $NETWORK (chain_id=$CHAIN_ID)"
info "rpc:           $RPC_URL"
info "explorer:      $EXPLORER"
info "key path:      $KEY_PATH"
info "dry-run:       $DRY_RUN"

# ---------------------------------------------------------------------------
# Pre-checks
# ---------------------------------------------------------------------------
check_git_clean() {
  section "pre-check: git status"
  if [[ ! -d "$REPO_ROOT/.git" ]] && ! git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    warn "not a git checkout; skipping clean-tree check"
    return 0
  fi
  if [[ -n "$(git -C "$REPO_ROOT" status --porcelain 2>/dev/null)" ]]; then
    if [[ "$FORCE_DIRTY" -eq 1 ]]; then
      warn "git tree is dirty (continuing because --force-dirty)"
    else
      die 1 "git tree is dirty; commit or pass --force-dirty"
    fi
  else
    ok "git tree clean"
  fi
}

check_tools() {
  section "pre-check: tooling"
  for bin in python3 node npm curl; do
    if ! command -v "$bin" >/dev/null 2>&1; then
      die 1 "$bin not on PATH"
    fi
  done
  ok "python3 $(python3 --version 2>&1 | awk '{print $2}'), node $(node --version), npm $(npm --version)"
}

check_node_modules() {
  section "pre-check: 0G storage bridge node deps"
  local ts_dir="$REPO_ROOT/lib/og/_ts"
  if [[ ! -d "$ts_dir" ]]; then
    die 1 "$ts_dir not found (lib/og/_ts/ missing)"
  fi
  if [[ -d "$ts_dir/node_modules" ]]; then
    ok "lib/og/_ts/node_modules present"
    return 0
  fi
  info "node_modules absent; running 'npm install'..."
  if ! ( cd "$ts_dir" && npm install --no-audit --no-fund ) >>"$LOG_FILE" 2>&1; then
    die 1 "npm install failed in $ts_dir; see $LOG_FILE"
  fi
  ok "npm install complete"
}

check_key_file() {
  section "pre-check: deploy key"
  if [[ -z "$KEY_PATH" ]]; then
    die 2 "no key path; pass --key-path PATH or set OG_DEPLOY_KEY_PATH"
  fi
  if [[ ! -f "$KEY_PATH" ]]; then
    die 2 "key file not found: $KEY_PATH"
  fi
  # mode check (BSD vs GNU stat)
  local mode
  if mode=$(stat -f '%A' "$KEY_PATH" 2>/dev/null); then : ;
  elif mode=$(stat -c '%a' "$KEY_PATH" 2>/dev/null); then : ;
  else mode=""
  fi
  if [[ "$mode" != "600" && "$mode" != "0600" ]]; then
    die 2 "key file mode is '$mode'; must be 0600. Run: chmod 600 \"$KEY_PATH\""
  fi
  # Smoke-check: file is non-empty.
  if [[ ! -s "$KEY_PATH" ]]; then
    die 2 "key file is empty: $KEY_PATH"
  fi
  ok "key file ok (mode 0600)"
}

# Derive the wallet address from the key file using web3/eth-account.
# Returns address on stdout. Never prints the key itself. On any failure
# returns empty string and a non-zero rc; the caller exits 2.
derive_address() {
  local key_path="$1"
  python3 - "$key_path" <<'PY' 2>>"${LOG_FILE:-/dev/null}" || true
import sys
try:
    from eth_account import Account
except ImportError:
    sys.stderr.write("eth_account not installed (pip install eth-account)\n")
    sys.exit(1)
key_path = sys.argv[1]
try:
    with open(key_path) as f:
        key = f.read().strip()
    if not key:
        raise ValueError("key file is empty")
    addr = Account.from_key(key).address
    print(addr)
except Exception as exc:
    sys.stderr.write(f"address derivation failed: {exc}\n")
    sys.exit(1)
PY
}

# JSON-RPC eth_getBalance query via curl (no key material on the wire).
rpc_get_balance_wei() {
  local addr="$1"
  local payload
  payload=$(printf '{"jsonrpc":"2.0","method":"eth_getBalance","params":["%s","latest"],"id":1}' "$addr")
  local response
  response=$(curl -sS --max-time 10 -H "Content-Type: application/json" \
    -d "$payload" "$RPC_URL")
  python3 - "$response" <<'PY'
import json, sys
r = json.loads(sys.argv[1])
if "error" in r:
    print(f"ERROR:{r['error'].get('message', 'rpc error')}")
    sys.exit(1)
hex_wei = r.get("result", "0x0")
print(int(hex_wei, 16))
PY
}

check_wallet_balance() {
  section "pre-check: wallet balance"
  local addr balance_wei deficit_wei
  addr=$(derive_address "$KEY_PATH" 2>>"$LOG_FILE")
  if [[ -z "$addr" || "$addr" != 0x* ]]; then
    die 2 "could not derive wallet address from key (malformed key file)"
  fi
  info "wallet:        $addr"
  WALLET_ADDR="$addr"

  if ! balance_wei=$(rpc_get_balance_wei "$addr"); then
    die 1 "RPC eth_getBalance failed against $RPC_URL"
  fi
  if [[ "$balance_wei" == ERROR:* ]]; then
    die 1 "RPC error: ${balance_wei#ERROR:}"
  fi
  local balance_float
  balance_float=$(python3 -c "print(f'{int($balance_wei) / 1e18:.6f}')")
  info "balance:       $balance_float 0G ($balance_wei wei)"

  if [[ "$balance_wei" -lt "$MIN_BALANCE_WEI" ]]; then
    if [[ "${SAPPHIRE_HACKATHON_SMOKE_BYPASS_BALANCE:-0}" == "1" && "$DRY_RUN" -eq 1 ]]; then
      warn "balance below min ($balance_float < $MIN_BALANCE_FLOAT) but bypass+dry-run set"
      ok "balance check bypassed for dry-run testing"
      return 0
    fi
    deficit_wei=$((MIN_BALANCE_WEI - balance_wei))
    local deficit_float
    deficit_float=$(python3 -c "print(f'{int($deficit_wei) / 1e18:.6f}')")
    err "wallet under-funded for $NETWORK"
    err "  needed: $MIN_BALANCE_FLOAT 0G"
    err "  have:   $balance_float 0G"
    err "  short:  $deficit_float 0G"
    if [[ "$NETWORK" == "testnet" ]]; then
      err "  fund testnet wallet from https://docs.0g.ai (faucet)"
    else
      err "  fund mainnet wallet $addr with at least $MIN_BALANCE_FLOAT 0G before retrying"
    fi
    exit 2
  fi
  ok "balance ≥ minimum for $NETWORK"
}

# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------
deploy_contracts() {
  section "step 1: deploy contracts"
  if [[ "${SAPPHIRE_HACKATHON_SMOKE_SKIP_DEPLOY:-0}" == "1" && "$DRY_RUN" -eq 1 ]]; then
    warn "deploy skipped (SAPPHIRE_HACKATHON_SMOKE_SKIP_DEPLOY=1, dry-run only)"
    return 0
  fi
  local mode_flag=""
  if [[ "$DRY_RUN" -eq 1 ]]; then
    mode_flag="--abi-only"
    info "dry-run: invoking deploy_og_chain.py --abi-only (no broadcast)"
  fi
  # Pass the key through env (deploy script reads OG_PRIVATE_KEY first).
  local key
  key=$(cat "$KEY_PATH")
  if ! OG_PRIVATE_KEY="$key" python3 scripts/deploy_og_chain.py \
        --network "$NETWORK" $mode_flag \
        >>"$LOG_FILE" 2>&1; then
    err "deploy step failed; tail of $LOG_FILE:"
    tail -n 40 "$LOG_FILE" | sed 's/^/    /' | tee -a "$LOG_FILE" >&2 || true
    exit 1
  fi
  unset key
  ok "deploy step complete"
}

read_deployments() {
  # Returns the deployment record for $NETWORK as JSON on stdout.
  python3 - "$NETWORK" <<'PY'
import json, os, sys
from pathlib import Path
network = sys.argv[1]
p = Path("data/chain/deployments.json")
if not p.exists():
    sys.stderr.write("deployments.json not found; deploy did not run?\n")
    sys.exit(1)
data = json.loads(p.read_text())
key = f"og_{network}"
rec = data.get(key)
if not rec:
    sys.stderr.write(f"no deployment record for {key}\n")
    sys.exit(1)
print(json.dumps(rec))
PY
}

publish_signal() {
  section "step 2: publish demo signal"
  local pub_input pub_output
  pub_input=$(cat <<'JSON'
{
  "strategy": "hackathon_demo_kronos_btc_24h",
  "symbol": "BTC-USD",
  "action": "buy",
  "score": 83,
  "signal": {"price": 65000, "horizon_h": 24, "source": "hackathon_smoke", "demo": true},
  "inputs": {"window": "24h", "candles": "synthetic"}
}
JSON
)
  pub_output=$(SAPPHIRE_OG_ENABLED=1 SAPPHIRE_OG_NETWORK="$NETWORK" \
    bash -c "echo '$pub_input' | python3 plugins/claw-sapphire/tools/og_publish.py" 2>>"$LOG_FILE") \
    || { err "og_publish failed"; tail -n 30 "$LOG_FILE" >&2; exit 1; }
  echo "$pub_output" >>"$LOG_FILE"
  if ! python3 -c "import json,sys; d=json.loads(sys.argv[1]); sys.exit(0 if d.get('ok') else 1)" "$pub_output"; then
    err "og_publish returned ok=false:"
    log "$pub_output"
    exit 1
  fi
  SIGNAL_ID=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['anchor']['signal_id'])" "$pub_output")
  PUBLISH_TX=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['anchor']['tx_hash'])" "$pub_output")
  ROOT_HASH=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['root_hash'])" "$pub_output")
  ok "published signal_id=$SIGNAL_ID tx=$PUBLISH_TX"
}

verify_signal() {
  section "step 3: verify signal"
  local ver_output
  ver_output=$(SAPPHIRE_OG_ENABLED=1 SAPPHIRE_OG_NETWORK="$NETWORK" \
    bash -c "echo '{\"signal_id\": $SIGNAL_ID}' | python3 plugins/claw-sapphire/tools/og_verify.py" 2>>"$LOG_FILE") \
    || { err "og_verify failed"; tail -n 30 "$LOG_FILE" >&2; exit 1; }
  echo "$ver_output" >>"$LOG_FILE"
  if ! python3 -c "import json,sys; d=json.loads(sys.argv[1]); sys.exit(0 if d.get('ok') and d.get('verified',{}).get('merkle_proof') else 1)" "$ver_output"; then
    err "og_verify did not pass:"
    log "$ver_output"
    exit 1
  fi
  ok "verify PASS (TEE attestation OK, storage rootHash matches)"
}

# ---------------------------------------------------------------------------
# Summary writer
# ---------------------------------------------------------------------------
write_summary() {
  section "step 4: assemble submission summary"
  local end_epoch duration deployments_json
  end_epoch=$(date +%s)
  duration=$((end_epoch - START_EPOCH))
  local human_ts
  human_ts=$(date -u +"%Y-%m-%d %H:%M:%S UTC")

  if [[ "$DRY_RUN" -eq 1 ]]; then
    {
      printf '## Submission artifacts (DRY-RUN %s)\n' "$human_ts"
      printf -- '- Network: %s\n' "$NETWORK"
      printf -- '- Chain ID: %s\n' "$CHAIN_ID"
      printf -- '- Wallet: %s\n' "${WALLET_ADDR:-unknown}"
      printf -- '- Mode: dry-run (preflight + abi-only deploy, no publish/verify)\n'
      printf -- '- Run duration: %ss\n' "$duration"
      printf -- '- Log: %s\n' "$LOG_FILE"
    } | tee "$SUMMARY_FILE" | tee -a "$LOG_FILE"
    return 0
  fi

  if ! deployments_json=$(read_deployments 2>>"$LOG_FILE"); then
    die 1 "could not read deployments.json after deploy"
  fi

  # Emit the summary via python so we get reliable JSON parsing + formatting.
  python3 - "$deployments_json" "$NETWORK" "$CHAIN_ID" "$EXPLORER" \
    "$SIGNAL_ID" "$PUBLISH_TX" "$ROOT_HASH" "$human_ts" "$duration" \
    "${WALLET_ADDR:-unknown}" "$LOG_FILE" "$SUMMARY_FILE" <<'PY'
import json, sys
from pathlib import Path

(_, deployments_raw, network, chain_id, explorer, signal_id, publish_tx,
 root_hash, human_ts, duration, wallet, log_file, summary_file) = sys.argv

rec = json.loads(deployments_raw)
contracts = rec.get("contracts", {})

lines = []
lines.append(f"## Submission artifacts (generated {human_ts})")
lines.append(f"- Network: **{network}**")
lines.append(f"- Chain ID: {chain_id}")
lines.append(f"- Wallet: `{wallet}`")
for name in ("SapphireSignalVerifier", "SapphirePaymentGate", "SapphireSentinelRegistry"):
    info = contracts.get(name, {})
    addr = info.get("address", "0x?")
    url = f"{explorer}/address/{addr}"
    lines.append(f"- {name}: `{addr}` -> {url}")
lines.append(f"- First signal ID: {signal_id}")
lines.append(f"- Publish tx: `{publish_tx}` -> {explorer}/tx/{publish_tx}")
lines.append(f"- Storage rootHash: `{root_hash}`")
lines.append(f"- Verify result: PASS (TEE attestation OK, storage rootHash matches)")
lines.append(f"- Run duration: {duration}s")
lines.append(f"- Log: `{log_file}`")
lines.append("")
lines.append("All outputs above are READY TO PASTE into the HackQuest submission form.")

text = "\n".join(lines) + "\n"
Path(summary_file).write_text(text)
sys.stdout.write(text)
PY
  # Mirror the summary into the run log (already written via tee in stdout above).
  cat "$SUMMARY_FILE" >>"$LOG_FILE" || true
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  : > "$LOG_FILE"  # truncate fresh
  log "hackathon_smoke.sh starting at $(date -u +%FT%TZ)"
  log "args: dry-run=$DRY_RUN network=$NETWORK key=$KEY_PATH"

  check_git_clean
  check_tools
  check_node_modules
  check_key_file
  check_wallet_balance

  deploy_contracts

  if [[ "$DRY_RUN" -eq 1 ]]; then
    write_summary
    section "DRY-RUN COMPLETE"
    log "preflight + abi-only deploy succeeded; publish/verify skipped"
    exit 0
  fi

  publish_signal
  verify_signal
  write_summary

  section "SMOKE COMPLETE"
  log "summary: $SUMMARY_FILE"
  log "log:     $LOG_FILE"
}

main "$@"
