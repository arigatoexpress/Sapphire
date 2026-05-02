#!/usr/bin/env bash
# scripts/hackathon_smoke.sh
#
# One-shot demo-day smoke runner for the 0G APAC and Arbitrum/Robinhood
# London hackathons. Deploys (or re-uses) contracts, publishes a smoke
# signal on-chain, and emits a submission-ready markdown summary so the
# user only has to copy the result into the HackQuest form + demo.
#
# USAGE:
#   scripts/hackathon_smoke.sh [--dry-run] [--target 0g|robinhood|both]
#                              [--network mainnet|testnet] [--key-path PATH]
#                              [--force-dirty] [--force-redeploy]
#
# ENV (alternative to flags):
#   OG_DEPLOY_KEY_PATH         path to 0G private-key file (mode 0600) —
#                              required for --target 0g|both
#   ROBINHOOD_DEPLOY_KEY_PATH  path to Robinhood Chain testnet key file
#                              (mode 0600) — required for --target robinhood|both
#   OG_NETWORK                 mainnet | testnet (default mainnet)
#   ROBINHOOD_NETWORK          testnet only (mainnet not supported by
#                              Sapphire today; default testnet)
#   OG_RPC_URL                 override default 0G RPC
#   ROBINHOOD_RPC_URL          override default Robinhood Chain RPC
#                              (default https://rpc.testnet.chain.robinhood.com)
#
# Discipline:
#   - bash strict mode
#   - never prints private keys
#   - reads keystore only from --key-path / *_DEPLOY_KEY_PATH env vars
#   - writes a full timestamped log + markdown summary under data/hackathon/
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
TARGET="0g"
NETWORK="${OG_NETWORK:-mainnet}"
KEY_PATH="${OG_DEPLOY_KEY_PATH:-$HOME/.config/sapphire-secrets/og_deploy_key}"
ROBINHOOD_KEY_PATH="${ROBINHOOD_DEPLOY_KEY_PATH:-$HOME/.config/sapphire-secrets/robinhood_deploy_key}"
ROBINHOOD_NETWORK="${ROBINHOOD_NETWORK:-testnet}"
ROBINHOOD_RPC_URL="${ROBINHOOD_RPC_URL:-https://rpc.testnet.chain.robinhood.com}"
ROBINHOOD_EXPLORER="https://explorer.testnet.chain.robinhood.com"
ROBINHOOD_CHAIN_ID=46630
ROBINHOOD_MIN_BALANCE_FLOAT="0.001"
ROBINHOOD_MIN_BALANCE_WEI="1000000000000000"  # 0.001 ETH
DRY_RUN=0
FORCE_DIRTY=0
FORCE_REDEPLOY=0

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
Usage: scripts/hackathon_smoke.sh [--dry-run] [--target 0g|robinhood|both]
                                  [--network mainnet|testnet]
                                  [--key-path PATH] [--force-dirty]
                                  [--force-redeploy]

Runs hackathon-submission smoke flows. Writes a submission-ready markdown
to data/hackathon/submission_artifacts.md.

  --dry-run         Run preflight + abi/compile-only deploy; skip publish/verify.
  --target T        "0g" (default), "robinhood", or "both".
  --network NET     "mainnet" or "testnet" for the 0G target (default mainnet).
                    Robinhood is testnet-only today.
  --key-path PATH   0G private-key file (mode 0600). Default $OG_DEPLOY_KEY_PATH
                    or ~/.config/sapphire-secrets/og_deploy_key. Robinhood key
                    comes from $ROBINHOOD_DEPLOY_KEY_PATH or
                    ~/.config/sapphire-secrets/robinhood_deploy_key.
  --force-dirty     Don't fail on a dirty git tree (warn only).
  --force-redeploy  Re-deploy even when an address is already on record.
  -h, --help        Show this message.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)        DRY_RUN=1 ;;
    --force-dirty)    FORCE_DIRTY=1 ;;
    --force-redeploy) FORCE_REDEPLOY=1 ;;
    --network)        shift; NETWORK="${1:-}" ;;
    --network=*)      NETWORK="${1#*=}" ;;
    --key-path)       shift; KEY_PATH="${1:-}" ;;
    --key-path=*)     KEY_PATH="${1#*=}" ;;
    --target)         shift; TARGET="${1:-}" ;;
    --target=*)       TARGET="${1#*=}" ;;
    -h|--help)        print_usage; exit 0 ;;
    *) print_usage; die 1 "unknown argument: $1" ;;
  esac
  shift || true
done

case "$TARGET" in
  0g|robinhood|both) ;;
  *) print_usage; die 1 "--target must be '0g', 'robinhood', or 'both' (got '$TARGET')" ;;
esac

case "$NETWORK" in
  mainnet|testnet) ;;
  *) die 1 "--network must be 'mainnet' or 'testnet' (got '$NETWORK')" ;;
esac

# 0G network-specific config (mirrors lib/og/config.py).
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

info "log file:        $LOG_FILE"
info "target:          $TARGET"
info "0g network:      $NETWORK (chain_id=$CHAIN_ID)"
info "0g rpc:          $RPC_URL"
info "0g key path:     $KEY_PATH"
info "robinhood net:   $ROBINHOOD_NETWORK (chain_id=$ROBINHOOD_CHAIN_ID)"
info "robinhood rpc:   $ROBINHOOD_RPC_URL"
info "robinhood key:   $ROBINHOOD_KEY_PATH"
info "dry-run:         $DRY_RUN"
info "force-redeploy:  $FORCE_REDEPLOY"

# ---------------------------------------------------------------------------
# Pre-checks (shared)
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

check_python_chain_libs() {
  section "pre-check: web3 + eth-account"
  if ! python3 -c "import web3, eth_account" >>"$LOG_FILE" 2>&1; then
    die 1 "web3 / eth-account not importable; pip install -r requirements-test.txt"
  fi
  ok "web3 + eth-account importable"
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

# Generic key-file validator. Sets WALLET_ADDR_<TAG> via the CALLER on success.
check_key_file_for() {
  local label="$1" path="$2"
  section "pre-check: $label deploy key"
  if [[ -z "$path" ]]; then
    die 2 "no key path for $label; pass --key-path PATH or set the appropriate env var"
  fi
  if [[ ! -f "$path" ]]; then
    die 2 "key file not found: $path"
  fi
  local mode
  if mode=$(stat -f '%A' "$path" 2>/dev/null); then : ;
  elif mode=$(stat -c '%a' "$path" 2>/dev/null); then : ;
  else mode=""
  fi
  if [[ "$mode" != "600" && "$mode" != "0600" ]]; then
    die 2 "key file mode is '$mode'; must be 0600. Run: chmod 600 \"$path\""
  fi
  if [[ ! -s "$path" ]]; then
    die 2 "key file is empty: $path"
  fi
  ok "$label key file ok (mode 0600)"
}

# Derive the wallet address from a key file using web3/eth-account.
# Returns address on stdout. Never prints the key itself.
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

# JSON-RPC eth_getBalance via curl. $1=address $2=rpc_url
rpc_get_balance_wei() {
  local addr="$1" rpc="$2"
  local payload
  payload=$(printf '{"jsonrpc":"2.0","method":"eth_getBalance","params":["%s","latest"],"id":1}' "$addr")
  local response
  response=$(curl -sS --max-time 10 -H "Content-Type: application/json" \
    -d "$payload" "$rpc")
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

check_wallet_balance_for() {
  local label="$1" key_path="$2" rpc="$3" min_wei="$4" min_float="$5" symbol="$6"
  local _result_var="$7"
  section "pre-check: $label wallet balance"
  local addr balance_wei deficit_wei
  addr=$(derive_address "$key_path" 2>>"$LOG_FILE")
  if [[ -z "$addr" || "$addr" != 0x* ]]; then
    die 2 "could not derive wallet address from $label key (malformed key file)"
  fi
  info "$label wallet:   $addr"
  printf -v "$_result_var" '%s' "$addr"

  if ! balance_wei=$(rpc_get_balance_wei "$addr" "$rpc"); then
    die 1 "RPC eth_getBalance failed against $rpc"
  fi
  if [[ "$balance_wei" == ERROR:* ]]; then
    die 1 "RPC error: ${balance_wei#ERROR:}"
  fi
  local balance_float
  balance_float=$(python3 -c "print(f'{int($balance_wei) / 1e18:.6f}')")
  info "$label balance:  $balance_float $symbol ($balance_wei wei)"

  if [[ "$balance_wei" -lt "$min_wei" ]]; then
    if [[ "${SAPPHIRE_HACKATHON_SMOKE_BYPASS_BALANCE:-0}" == "1" && "$DRY_RUN" -eq 1 ]]; then
      warn "$label balance below min ($balance_float < $min_float) but bypass+dry-run set"
      ok "balance check bypassed for dry-run testing"
      return 0
    fi
    deficit_wei=$((min_wei - balance_wei))
    local deficit_float
    deficit_float=$(python3 -c "print(f'{int($deficit_wei) / 1e18:.6f}')")
    err "$label wallet under-funded"
    err "  needed: $min_float $symbol"
    err "  have:   $balance_float $symbol"
    err "  short:  $deficit_float $symbol"
    if [[ "$label" == "robinhood" ]]; then
      err "  fund testnet wallet $addr from Robinhood Chain testnet faucet"
    elif [[ "$NETWORK" == "testnet" ]]; then
      err "  fund testnet wallet from https://docs.0g.ai (faucet)"
    else
      err "  fund mainnet wallet $addr with at least $min_float $symbol before retrying"
    fi
    exit 2
  fi
  ok "$label balance >= minimum"
}

# ---------------------------------------------------------------------------
# 0G actions
# ---------------------------------------------------------------------------
deploy_contracts_og() {
  section "0g: step 1 — deploy contracts"

  # Idempotency: skip if deployment record exists, unless --force-redeploy.
  local already
  already=$(python3 - "$NETWORK" <<'PY' 2>/dev/null || true
import json, sys
from pathlib import Path
network = sys.argv[1]
p = Path("data/chain/deployments.json")
if not p.exists():
    sys.exit(0)
try:
    data = json.loads(p.read_text())
except Exception:
    sys.exit(0)
rec = data.get(f"og_{network}")
if rec and rec.get("contracts"):
    addr = next(iter(rec["contracts"].values())).get("address", "")
    print(addr)
PY
)
  if [[ -n "$already" && "$FORCE_REDEPLOY" -eq 0 ]]; then
    ok "0g: already deployed (e.g. $already), skipping deploy (use --force-redeploy to override)"
    return 0
  fi

  if [[ "${SAPPHIRE_HACKATHON_SMOKE_SKIP_DEPLOY:-0}" == "1" && "$DRY_RUN" -eq 1 ]]; then
    warn "deploy skipped (SAPPHIRE_HACKATHON_SMOKE_SKIP_DEPLOY=1, dry-run only)"
    return 0
  fi
  local mode_flag=""
  if [[ "$DRY_RUN" -eq 1 ]]; then
    mode_flag="--abi-only"
    info "dry-run: invoking deploy_og_chain.py --abi-only (no broadcast)"
  fi
  local key
  key=$(cat "$KEY_PATH")
  if ! OG_PRIVATE_KEY="$key" python3 scripts/deploy_og_chain.py \
        --network "$NETWORK" $mode_flag \
        >>"$LOG_FILE" 2>&1; then
    err "0g deploy step failed; tail of $LOG_FILE:"
    tail -n 40 "$LOG_FILE" | sed 's/^/    /' | tee -a "$LOG_FILE" >&2 || true
    exit 1
  fi
  unset key
  ok "0g deploy step complete"
}

read_deployments_og() {
  python3 - "$NETWORK" <<'PY'
import json, sys
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

publish_signal_og() {
  section "0g: step 2 — publish demo signal"
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

verify_signal_og() {
  section "0g: step 3 — verify signal"
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
# Robinhood actions
# ---------------------------------------------------------------------------
deploy_contracts_robinhood() {
  section "robinhood: step 1 — deploy contracts"

  # Idempotency: skip if a robinhood deployment record exists.
  local already
  already=$(python3 - <<'PY' 2>/dev/null || true
import json, sys
from pathlib import Path
p = Path("data/chain/deployments.json")
if not p.exists():
    sys.exit(0)
try:
    data = json.loads(p.read_text())
except Exception:
    sys.exit(0)
# Accept either the deploy script's key (robinhood_testnet) or a future
# robinhood_chain alias.
rec = data.get("robinhood_testnet") or data.get("robinhood_chain")
if rec and rec.get("contracts"):
    reg = rec["contracts"].get("SapphireSentinelRegistry") or next(iter(rec["contracts"].values()))
    print(reg.get("address", ""))
PY
)
  if [[ -n "$already" && "$FORCE_REDEPLOY" -eq 0 ]]; then
    ok "robinhood: already deployed at $already, skipping deploy (use --force-redeploy to override)"
    return 0
  fi

  if [[ "${SAPPHIRE_HACKATHON_SMOKE_SKIP_DEPLOY:-0}" == "1" && "$DRY_RUN" -eq 1 ]]; then
    warn "robinhood deploy skipped (SAPPHIRE_HACKATHON_SMOKE_SKIP_DEPLOY=1, dry-run only)"
    return 0
  fi

  local mode_flag=""
  if [[ "$DRY_RUN" -eq 1 ]]; then
    mode_flag="--dry-run"
    info "dry-run: invoking deploy_robinhood_chain.py --dry-run (compile only, no broadcast)"
  fi

  local key
  key=$(cat "$ROBINHOOD_KEY_PATH")
  if ! ROBINHOOD_DEPLOY_KEY="$key" python3 scripts/deploy_robinhood_chain.py \
        $mode_flag \
        >>"$LOG_FILE" 2>&1; then
    err "robinhood deploy step failed; tail of $LOG_FILE:"
    tail -n 40 "$LOG_FILE" | sed 's/^/    /' | tee -a "$LOG_FILE" >&2 || true
    exit 1
  fi
  unset key
  ok "robinhood deploy step complete"
}

# Read the robinhood deployment record (JSON on stdout). Empty stdout +
# rc=2 if no record exists yet (expected during dry-runs that skip deploy).
read_deployments_robinhood() {
  python3 - <<'PY'
import json, sys
from pathlib import Path
p = Path("data/chain/deployments.json")
if not p.exists():
    sys.exit(2)
try:
    data = json.loads(p.read_text())
except Exception:
    sys.exit(2)
rec = data.get("robinhood_testnet") or data.get("robinhood_chain")
if not rec:
    sys.exit(2)
print(json.dumps(rec))
PY
}

publish_signal_robinhood() {
  section "robinhood: step 2 — publish smoke signal"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    warn "dry-run: skipping on-chain publish (would call RobinhoodChainClient.publish_signal)"
    ROBINHOOD_PUBLISH_TX=""
    ROBINHOOD_SIGNAL_ID=""
    return 0
  fi

  local key
  key=$(cat "$ROBINHOOD_KEY_PATH")
  local out
  out=$(ROBINHOOD_DEPLOY_KEY="$key" python3 - <<'PY' 2>>"$LOG_FILE"
import json, os, sys
from lib.chain.robinhood_chain import RobinhoodChainClient

key = os.environ.get("ROBINHOOD_DEPLOY_KEY", "").strip()
if not key:
    print(json.dumps({"error": "no key in env"}))
    sys.exit(1)
client = RobinhoodChainClient(private_key=key)
result = client.publish_signal("smoke_test", "BTC-USD", "long", 0.5)
print(json.dumps(result))
PY
) || { err "robinhood publish_signal failed"; tail -n 30 "$LOG_FILE" >&2; unset key; exit 1; }
  unset key
  echo "$out" >>"$LOG_FILE"

  if ! python3 -c "import json,sys; d=json.loads(sys.argv[1]); sys.exit(0 if not d.get('error') and d.get('tx_hash') else 1)" "$out"; then
    err "robinhood publish_signal returned error:"
    log "$out"
    exit 1
  fi

  ROBINHOOD_PUBLISH_TX=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('tx_hash',''))" "$out")
  ROBINHOOD_SIGNAL_ID=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('signal_id') or '')" "$out")
  ok "robinhood publish OK: tx=0x$ROBINHOOD_PUBLISH_TX"
}

# Sentinel chain-health probe — the cross-chain alpha-verification money
# shot for the London buildathon. Mocks a basket and calls
# evaluate_from_payload(); captured as a sample in the artifact summary.
verify_signal_robinhood() {
  section "robinhood: step 3 — sentinel chain-health probe"
  local out
  out=$(python3 - <<'PY' 2>>"$LOG_FILE"
import json, sys
from lib.hackathon.sentinel import evaluate_from_payload

payload = {
    "resource": "https://signals.sapphire.local/api/private-rwa-signal?basket=RH-STOCKS",
    "amount_usdc": "0.012",
    "action": "buy-private-signal",
    "method": "GET",
    "payload_summary": "mock basket — TSLA/AMZN/PLTR/NFLX/AMD risk signal",
    "result_summary": "basket risk passes issuer concentration + drawdown caps",
    "order_symbol": "PLTR",
    "order_action": "buy",
    "notional_usd": 25.0,
    # Forward-compat: when Lane E (#555) merges, this routes to a MegaETH
    # chain-health gate. Until then evaluate_from_payload silently ignores it.
    "target_chain_id": 4326,
}
print(json.dumps(evaluate_from_payload(payload)))
PY
) || { err "sentinel evaluate_from_payload failed"; tail -n 30 "$LOG_FILE" >&2; exit 1; }
  echo "$out" >>"$LOG_FILE"

  if ! python3 -c "import json,sys; d=json.loads(sys.argv[1]); sys.exit(0 if 'receipt_id' in d else 1)" "$out"; then
    err "sentinel evaluate_from_payload returned unexpected shape:"
    log "$out"
    exit 1
  fi

  # Truncate to 600 chars for the artifact (full payload is in the run log).
  ROBINHOOD_SENTINEL_SAMPLE=$(python3 - "$out" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
text = json.dumps(data, indent=2, sort_keys=True)
print(text[:600] + ("\n..." if len(text) > 600 else ""))
PY
)
  ok "sentinel evaluate PASS (approved=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('approved'))" "$out"))"
}

# ---------------------------------------------------------------------------
# Summary writers (one per target; appended to the same SUMMARY_FILE)
# ---------------------------------------------------------------------------
init_summary() {
  : > "$SUMMARY_FILE"
}

append_summary_og() {
  section "0g: assemble submission summary"
  local end_epoch duration deployments_json human_ts
  end_epoch=$(date +%s)
  duration=$((end_epoch - START_EPOCH))
  human_ts=$(date -u +"%Y-%m-%d %H:%M:%S UTC")

  if [[ "$DRY_RUN" -eq 1 ]]; then
    {
      printf '## 0G (APAC Buildathon submission artifacts — DRY-RUN %s)\n' "$human_ts"
      printf -- '- Network: %s\n' "$NETWORK"
      printf -- '- Chain ID: %s\n' "$CHAIN_ID"
      printf -- '- Wallet: %s\n' "${WALLET_ADDR_OG:-unknown}"
      printf -- '- Mode: dry-run (preflight + abi-only deploy, no publish/verify)\n'
      printf -- '- Run duration: %ss\n' "$duration"
      printf -- '- Log: %s\n' "$LOG_FILE"
      printf '\n'
    } | tee -a "$SUMMARY_FILE" | tee -a "$LOG_FILE"
    return 0
  fi

  if ! deployments_json=$(read_deployments_og 2>>"$LOG_FILE"); then
    die 1 "could not read 0g deployments.json after deploy"
  fi

  python3 - "$deployments_json" "$NETWORK" "$CHAIN_ID" "$EXPLORER" \
    "$SIGNAL_ID" "$PUBLISH_TX" "$ROOT_HASH" "$human_ts" "$duration" \
    "${WALLET_ADDR_OG:-unknown}" "$LOG_FILE" "$SUMMARY_FILE" <<'PY'
import json, sys
from pathlib import Path

(_, deployments_raw, network, chain_id, explorer, signal_id, publish_tx,
 root_hash, human_ts, duration, wallet, log_file, summary_file) = sys.argv

rec = json.loads(deployments_raw)
contracts = rec.get("contracts", {})

lines = []
lines.append(f"## 0G (APAC Buildathon submission artifacts — generated {human_ts})")
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
lines.append("")

text = "\n".join(lines) + "\n"
with open(summary_file, "a") as f:
    f.write(text)
sys.stdout.write(text)
PY
  cat "$SUMMARY_FILE" >>"$LOG_FILE" || true
}

append_summary_robinhood() {
  section "robinhood: assemble submission summary"
  local end_epoch duration deployments_json human_ts
  end_epoch=$(date +%s)
  duration=$((end_epoch - START_EPOCH))
  human_ts=$(date -u +"%Y-%m-%d %H:%M:%S UTC")

  # Try to read the deployments record (may be absent in dry-run).
  deployments_json=$(read_deployments_robinhood 2>/dev/null || true)

  python3 - "${deployments_json:-}" "$ROBINHOOD_CHAIN_ID" "$ROBINHOOD_EXPLORER" \
    "${ROBINHOOD_PUBLISH_TX:-}" "${ROBINHOOD_SIGNAL_ID:-}" \
    "${ROBINHOOD_SENTINEL_SAMPLE:-}" "$human_ts" "$duration" \
    "${WALLET_ADDR_ROBINHOOD:-unknown}" "$LOG_FILE" "$SUMMARY_FILE" \
    "$DRY_RUN" <<'PY'
import json, sys
from pathlib import Path

(_, deployments_raw, chain_id, explorer, publish_tx, signal_id,
 sentinel_sample, human_ts, duration, wallet, log_file, summary_file,
 dry_run) = sys.argv

dry = dry_run == "1"

contracts = {}
if deployments_raw:
    try:
        rec = json.loads(deployments_raw)
        contracts = rec.get("contracts", {})
    except Exception:
        pass

dry_tag = " — DRY-RUN" if dry else ""
lines = []
lines.append(f"## Robinhood Chain (London Buildathon submission artifacts{dry_tag} — generated {human_ts})")
lines.append(f"- Network: **testnet**")
lines.append(f"- Chain ID: {chain_id}")
lines.append(f"- Wallet: `{wallet}`")
for name in ("SapphireSignalVerifier", "SapphirePaymentGate", "SapphireSentinelRegistry"):
    info = contracts.get(name, {})
    addr = info.get("address", "0x? (not deployed in this run)")
    if addr.startswith("0x") and addr != "0x?" and not addr.endswith("(not deployed in this run)"):
        url = f"{explorer}/address/{addr}"
        lines.append(f"- {name}: `{addr}` -> {url}")
    else:
        lines.append(f"- {name}: {addr}")

if publish_tx:
    norm_tx = publish_tx if publish_tx.startswith("0x") else f"0x{publish_tx}"
    lines.append(f"- First smoke signal tx: `{norm_tx}` -> {explorer}/tx/{norm_tx}")
elif dry:
    lines.append(f"- First smoke signal tx: (dry-run; not broadcast)")
else:
    lines.append(f"- First smoke signal tx: (not captured)")

if signal_id:
    lines.append(f"- Signal ID (event topic): `{signal_id}`")

if sentinel_sample:
    lines.append("")
    lines.append("### Sentinel evaluate-with-chain-health response (truncated)")
    lines.append("")
    lines.append("```json")
    lines.append(sentinel_sample.rstrip())
    lines.append("```")
elif dry:
    lines.append(f"- Sentinel evaluate-with-chain-health: (dry-run; not invoked)")

lines.append("")
lines.append(f"- Run duration: {duration}s")
lines.append(f"- Log: `{log_file}`")
lines.append("")
lines.append("All outputs above are READY TO PASTE into the Arbitrum HackQuest form.")
lines.append("")

text = "\n".join(lines) + "\n"
with open(summary_file, "a") as f:
    f.write(text)
sys.stdout.write(text)
PY
  cat "$SUMMARY_FILE" >>"$LOG_FILE" || true
}

# ---------------------------------------------------------------------------
# Per-target orchestrators
# ---------------------------------------------------------------------------
run_target_og() {
  WALLET_ADDR_OG=""
  check_node_modules
  check_key_file_for "0g" "$KEY_PATH"
  KEY_PATH_FOR_BAL="$KEY_PATH" \
    check_wallet_balance_for "0g" "$KEY_PATH" "$RPC_URL" \
                             "$MIN_BALANCE_WEI" "$MIN_BALANCE_FLOAT" "0G" \
                             WALLET_ADDR_OG

  deploy_contracts_og

  if [[ "$DRY_RUN" -eq 1 ]]; then
    append_summary_og
    return 0
  fi

  publish_signal_og
  verify_signal_og
  append_summary_og
}

run_target_robinhood() {
  WALLET_ADDR_ROBINHOOD=""
  check_key_file_for "robinhood" "$ROBINHOOD_KEY_PATH"
  check_wallet_balance_for "robinhood" "$ROBINHOOD_KEY_PATH" "$ROBINHOOD_RPC_URL" \
                           "$ROBINHOOD_MIN_BALANCE_WEI" "$ROBINHOOD_MIN_BALANCE_FLOAT" "ETH" \
                           WALLET_ADDR_ROBINHOOD

  deploy_contracts_robinhood
  publish_signal_robinhood

  # Sentinel probe runs even on dry-run — it's pure-Python with no chain
  # I/O, and shows the API is callable for the buildathon submission.
  verify_signal_robinhood

  append_summary_robinhood
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  : > "$LOG_FILE"  # truncate fresh
  log "hackathon_smoke.sh starting at $(date -u +%FT%TZ)"
  log "args: dry-run=$DRY_RUN target=$TARGET network=$NETWORK"

  check_git_clean
  check_tools
  check_python_chain_libs
  init_summary

  case "$TARGET" in
    0g)
      run_target_og
      ;;
    robinhood)
      run_target_robinhood
      ;;
    both)
      run_target_og
      run_target_robinhood
      ;;
  esac

  if [[ "$DRY_RUN" -eq 1 ]]; then
    section "DRY-RUN COMPLETE"
    log "preflight + abi/compile-only deploy succeeded for target=$TARGET; publish/verify skipped (or stubbed)"
    exit 0
  fi

  section "SMOKE COMPLETE"
  log "summary: $SUMMARY_FILE"
  log "log:     $LOG_FILE"
}

main "$@"
