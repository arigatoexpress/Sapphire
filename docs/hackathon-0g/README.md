# Sapphire × 0G — Verifiable Autonomous Trading

> **0G APAC Hackathon submission · Track 2: Agentic Trading Arena (Verifiable Finance)**

Sapphire is a production autonomous trading + intelligence OS. For the 0G hackathon we add a **cryptographic settlement layer** so every trading signal is provably committed *before* the market moves on it.

## One-sentence pitch (≤30 words)

A production trading agent that publishes every signal to 0G Storage and anchors it on 0G Chain, giving traders, auditors, and counterparties on-chain proof of every prediction.

## What it does

For each trading signal the system generates:

1. **Inference under TEE** — the prediction is produced by a 0G Compute provider running in a Trusted Execution Environment. The provider returns a `chatID` that anyone can later use to verify the response was signed by the attested TEE (`broker.inference.processResponse(provider, chatID)`).
2. **Storage commit** — the full signal envelope (input, reasoning, output, TEE attestation) is uploaded to **0G Storage** and content-addressed by merkle `rootHash`.
3. **Chain anchor** — `SapphireSignalVerifier.publishSignal(strategyId, symbol, direction, confidence, proofHash=rootHash)` is called on **0G Chain mainnet (chainId 16661)**, immutably committing to the prediction.
4. **Verifier path** — anyone can recover the full audit trail with the `og_verify` tool: read the on-chain entry → download the blob from 0G Storage → re-verify the merkle proof → re-verify the TEE attestation.

This closes the front-running window: by the time anyone learns the prediction *exists* (the on-chain anchor is public), the prediction is already cryptographically committed.

## Which 0G components are used

| Component | Where it shows up in code | What it secures |
|-----------|---------------------------|-----------------|
| **0G Storage** | [`lib/og/storage.py`](../../lib/og/storage.py), [`lib/og/_ts/og_storage.mjs`](../../lib/og/_ts/og_storage.mjs) | Content-addressed blob storage for the full signal envelope. |
| **0G Compute (Sealed Inference / TEE)** | [`lib/og/compute.py`](../../lib/og/compute.py) | The signal-generation inference call. Operator cannot retroactively rewrite history; provider attestation is on-chain. |
| **0G Chain (mainnet 16661)** | [`lib/og/chain.py`](../../lib/og/chain.py), [`contracts/SapphireSignalVerifier.sol`](../../contracts/SapphireSignalVerifier.sol) | Immutable, timestamped commitment to each prediction. |
| **0G payments + agent mandates** | [`contracts/SapphirePaymentGate.sol`](../../contracts/SapphirePaymentGate.sol), [`contracts/SapphireSentinelRegistry.sol`](../../contracts/SapphireSentinelRegistry.sol) | Subscription gating + agent spend mandates with on-chain payment receipts. |

## Architecture

```
TradingView webhook  ─►  signal_logger ─►  paper_trader / Hyperliquid / RH
        │
        │  [SAPPHIRE_OG_ENABLED=1]
        ▼
┌────────────────────┐    ┌─────────────────────────┐
│ 0G Compute (TEE)   │ ─► │  signal envelope        │
│ sealed inference   │    │  {input, reasoning,     │
└────────────────────┘    │   output, TEE attestn}  │
                          └────────────┬────────────┘
                                       │
                                       ▼
                          ┌────────────────────────┐
                          │ 0G Storage             │
                          │ (merkle rootHash)      │
                          └────────────┬───────────┘
                                       │
                                       ▼
                          ┌────────────────────────────────┐
                          │ SapphireSignalVerifier         │
                          │  .publishSignal(...,            │
                          │       proofHash=rootHash)       │
                          │ on 0G Chain mainnet (16661)    │
                          └────────────────────────────────┘
                                       │
                                       ▼
                          Anyone runs `og_verify` tool to:
                          1. Read on-chain Signal struct
                          2. Download blob from 0G Storage by rootHash
                          3. Verify merkle proof
                          4. Verify TEE chatID via broker.processResponse
```

## Quick start (judges / reviewers)

```bash
git clone https://github.com/<your-fork>/Sapphire.git
cd Sapphire
git checkout feat/0g-integration

# 1. Install Python deps
pip install -r requirements.txt web3 eth-account py-solc-x

# 2. Install Node deps for the 0G Storage bridge
cd lib/og/_ts && npm install && cd ../../..

# 3. Copy + customize the example secrets file (DO NOT COMMIT)
cp .env.example .env
# edit .env: set OG_PRIVATE_KEY (testnet wallet), then:
export $(grep -v '^#' .env | xargs)
export SAPPHIRE_OG_ENABLED=1
export SAPPHIRE_OG_NETWORK=testnet

# 4. Get testnet 0G from the faucet — see https://docs.0g.ai

# 5. Preflight + deploy the contracts to 0G testnet
python3 scripts/deploy_og_chain.py --check --network testnet
python3 scripts/deploy_og_chain.py --network testnet
# ABIs land in data/chain/, addresses in data/chain/deployments.json

# 6. Run the test suite
make test                       # 5,995+ core tests
pytest tests/unit/og_integration/ -q   # 56 0G integration tests

# 7. Publish a sample signal
echo '{
  "strategy": "kronos_btc_24h",
  "symbol": "BTC-USD",
  "action": "buy",
  "score": 83,
  "signal": {"price": 65000, "horizon_h": 24}
}' | python3 plugins/claw-sapphire/tools/og_publish.py

# 8. Verify it
echo '{"signal_id": 0}' | python3 plugins/claw-sapphire/tools/og_verify.py
```

## Mainnet contract addresses

> Filled in after `scripts/deploy_og_chain.py --network mainnet` completes.

| Contract | Address | Explorer |
|---|---|---|
| `SapphireSignalVerifier` | `0x...` | https://chainscan.0g.ai/address/0x... |
| `SapphirePaymentGate` | `0x...` | https://chainscan.0g.ai/address/0x... |
| `SapphireSentinelRegistry` | `0x...` | https://chainscan.0g.ai/address/0x... |

## What's safe to look at without keys

- **All code is open** under `lib/og/`, `plugins/claw-sapphire/tools/og_*.py`, `scripts/deploy_og_chain.py`, `contracts/`.
- **All tests run offline** with mocked SDK responses: `pytest tests/unit/og_integration/`.
- The Solidity contracts are unchanged from Sapphire's pre-existing deployment to Robinhood Chain testnet (Arbitrum Orbit) — review at `contracts/`. The hackathon contribution is the **0G integration glue**, not new contract logic.

## Safety

- **All 0G code is gated behind `SAPPHIRE_OG_ENABLED=1`.** With the flag unset (default), Sapphire's trading critical path is byte-identical to its pre-hackathon behavior. We did not move live trading execution onto 0G.
- **0G publish is fire-and-forget.** A failed 0G publish logs to `data/system_events.jsonl` but never delays a webhook response or blocks a trade.
- **Private keys never cross the Python ↔ Node boundary in plain text.** The Node helper reads `OG_PRIVATE_KEY` from its own subprocess env, which is set by `lib/og/storage.py`.
- See [`docs/hackathon-0g/design.md`](design.md) for the full design + safety analysis.

## Repo links

- **Demo script** — [`docs/hackathon-0g/demo-script.md`](demo-script.md)
- **Submission checklist** — [`docs/hackathon-0g/submission-checklist.md`](submission-checklist.md)
- **X post draft** — [`docs/hackathon-0g/x-post.md`](x-post.md)
- **Design doc** — [`docs/hackathon-0g/design.md`](design.md)

## Team

Solo builder: Ari Spec ([@arigatoexpress](https://github.com/arigatoexpress)) — building Sapphire OS as a long-running autonomous trading + intelligence stack.
