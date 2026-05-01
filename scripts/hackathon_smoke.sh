#!/usr/bin/env bash
# Sapphire × 0G hackathon — single-command smoke test.
#
# Runs end-to-end against 0G TESTNET (no mainnet, no real funds):
#   1. Preflight RPC + key + balance
#   2. Compile + deploy contracts (idempotent — reuses deployments.json if recent)
#   3. Publish a synthetic signal via og_publish
#   4. Verify it round-trips via og_verify
#
# Required env (or place a one-line key file at ~/.config/sapphire-secrets/og_deploy_key):
#   OG_PRIVATE_KEY    funded 0G testnet wallet (faucet: https://docs.0g.ai)
#
# Optional env:
#   SAPPHIRE_SMOKE_REDEPLOY=1    force redeploy even if recent
#   SAPPHIRE_SMOKE_SKIP_DEPLOY=1 use existing deployments.json without checking
#
# Usage:
#   bash scripts/hackathon_smoke.sh

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT=$(pwd)

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
red()  { printf '\033[31m%s\033[0m\n' "$*"; }
green(){ printf '\033[32m%s\033[0m\n' "$*"; }

if [ -z "${OG_PRIVATE_KEY:-}" ] && [ ! -f ~/.config/sapphire-secrets/og_deploy_key ]; then
  red "OG_PRIVATE_KEY is not set and ~/.config/sapphire-secrets/og_deploy_key is missing."
  red "Create a testnet wallet, fund it from the 0G faucet, then export OG_PRIVATE_KEY."
  exit 1
fi

export SAPPHIRE_OG_ENABLED=1
export SAPPHIRE_OG_NETWORK=testnet

bold "==> [1/5] Node deps for the 0G Storage bridge"
if [ ! -d lib/og/_ts/node_modules ]; then
  ( cd lib/og/_ts && npm install --no-audit --no-fund )
else
  green "    already installed (lib/og/_ts/node_modules present)"
fi

bold "==> [2/5] Preflight 0G testnet"
python3 scripts/deploy_og_chain.py --check --network testnet

if [ "${SAPPHIRE_SMOKE_SKIP_DEPLOY:-0}" = "1" ]; then
  bold "==> [3/5] SKIPPING deploy (SAPPHIRE_SMOKE_SKIP_DEPLOY=1)"
elif [ "${SAPPHIRE_SMOKE_REDEPLOY:-0}" = "1" ] || ! python3 -c "
import json, sys, time
from pathlib import Path
p = Path('data/chain/deployments.json')
if not p.exists(): sys.exit(1)
d = json.loads(p.read_text()).get('og_testnet', {})
if not d.get('contracts'): sys.exit(1)
# Re-deploy if older than 30 days
age = time.time() - d.get('deployed_at', 0)
sys.exit(0 if age < 30 * 86400 else 1)
" 2>/dev/null; then
  bold "==> [3/5] Deploying contracts to 0G testnet"
  python3 scripts/deploy_og_chain.py --network testnet
else
  green "==> [3/5] Recent testnet deployment found — reusing"
  python3 -c "
import json
from pathlib import Path
d = json.loads(Path('data/chain/deployments.json').read_text())['og_testnet']
for name, info in d['contracts'].items():
    print(f\"    {name}: {info['address']}\")
"
fi

bold "==> [4/5] Publishing a synthetic signal via og_publish"
PUBLISH_OUT=$(mktemp)
trap 'rm -f "$PUBLISH_OUT"' EXIT

cat <<'EOF' | python3 plugins/claw-sapphire/tools/og_publish.py | tee "$PUBLISH_OUT"
{
  "strategy": "smoke_test_kronos_btc_24h",
  "symbol": "BTC-USD",
  "action": "buy",
  "score": 83,
  "signal": {"price": 65000, "horizon_h": 24, "source": "hackathon_smoke"},
  "inputs": {"window": "24h", "candles": "synthetic"}
}
EOF

ROOT_HASH=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('root_hash',''))" "$PUBLISH_OUT")
SIGNAL_ID=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('anchor',{}).get('signal_id',''))" "$PUBLISH_OUT")

if [ -z "$ROOT_HASH" ] || [ -z "$SIGNAL_ID" ]; then
  red "Publish failed (no root_hash or signal_id in response)"
  cat "$PUBLISH_OUT"
  exit 1
fi

green "    rootHash: $ROOT_HASH"
green "    signalId: $SIGNAL_ID"

bold "==> [5/5] Verifying the signal round-trips via og_verify"
echo "{\"signal_id\": $SIGNAL_ID}" | python3 plugins/claw-sapphire/tools/og_verify.py | python3 -m json.tool

bold "✅ Hackathon smoke test passed — testnet is wired up end-to-end."
echo
echo "Next:"
echo "  1. Update docs/hackathon-0g/README.md with the testnet addresses (already in data/chain/deployments.json)."
echo "  2. When ready: re-run this script with SAPPHIRE_OG_NETWORK=mainnet (after funding the wallet on mainnet)."
