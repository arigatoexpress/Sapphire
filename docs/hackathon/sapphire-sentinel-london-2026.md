# Sapphire Sentinel: London Buildathon Plan

## Pitch

Sapphire Sentinel is a policy, privacy, and payment safety layer for autonomous
agents on Robinhood Chain testnet. Agents can buy paid intelligence through
x402-style HTTP 402 flows, but every call is checked against a human mandate,
budget, domain allow-list, prompt-injection screen, and secret-egress screen
before a receipt hash is anchored on-chain.

## Why This Should Win

- Robinhood Chain relevance is native, not decorative: the demo deploys a
  Robinhood Chain contract, `SapphireSentinelRegistry`, for agent mandates and
  payment receipts.
- The Best Agentic Project angle is obvious: an AI agent tries to pay for
  private RWA intelligence and draft a tokenized-stock action.
- The cybersecurity angle is concrete: Sentinel blocks unsafe domains, prompt
  injection, secret-exfiltration language, and budget violations.
- The privacy story is buildable: exact portfolio/risk inputs stay off-chain;
  only `policyHash`, `resultHash`, and `riskHash` land on-chain.
- **Multi-chain alpha verification** is concrete: Sentinel queries Sapphire's
  MegaETH protocol-access layer (`lib/chains/megaeth/`) to confirm USDM is
  on-peg and Aave reserves are healthy *before* approving alpha-paid orders.
  Same patterns port to Arbitrum's GMX V2 + Aave deployments.
- **Privacy story is buildable**: Zama/FHEVM mock produces deterministic
  `resultHash` + `riskHash` from hidden basket weights, so the demo's
  encrypted-input claim isn't hand-waving.
- The demo is safe by default: no live Robinhood orders, no real Telegram
  sends, no secret reads, and no production funds.

## Demo Flow

1. Human creates an agent mandate: spend cap, allowed domains, allowed actions,
   privacy mode, and expiry.
2. Agent requests a paid private RWA signal.
3. The API returns an x402-compatible payment requirement on Base Sepolia.
3.5. **Sentinel calls `ChainHealthGate.evaluate_chain(4326)`** -> reads USDM
   peg health from 4 sources + Aave reserve liquidity + frozen-reserve flags
   via the MegaETH access layer. If severity >= BREAK_100BP, payment is
   refused with a chain-health reason on top of policy reasons. (Demo: live
   mainnet read, sub-second response, judge sees actual peg numbers from
   chain.)
4. Sentinel screens the request. A safe request is approved; an untrusted or
   prompt-injected request is blocked.
5. Approved flow returns a dry-run Robinhood order draft and an on-chain anchor
   preview for `SapphireSentinelRegistry.recordPaymentEvaluation(...)`.
6. Dashboard shows the same decision as a judge-friendly chain/payment/privacy
   trace at `/chain/sentinel`.

## Build Surface

| Surface | Path |
|---|---|
| Mandate/receipt contract | `contracts/SapphireSentinelRegistry.sol` |
| Policy evaluator | `lib/hackathon/sentinel.py` |
| Dashboard page | `services/dashboard/templates/pages/sentinel.html` |
| Demo APIs | `/api/hackathon/sentinel/demo`, `/api/hackathon/sentinel/evaluate` |
| Robinhood status field | `/api/chain/robinhood/status` includes `sentinel_registry_address` |
| Deployment list | `scripts/deploy_robinhood_chain.py` |
| Zama/FHEVM mock (Lane A) | `lib/hackathon/privacy_mock.py` |
| MegaETH chain-health gate (Lane B) | `lib/hackathon/chain_health_gate.py` |
| MegaETH read-only multi-protocol access (Wave A->B.3) | `lib/chains/megaeth/protocols.py` |
| Forge test suite (18 cases, gas report) | `tests/forge/SapphireSentinelRegistry.t.sol` |
| Slither static-analysis config + CI gate | `slither.config.json`, `.github/workflows/sentinel-contracts.yml` |
| Foundry profile | `foundry.toml` |

## Safe Defaults

- `execution_enabled=false` in every order draft.
- `broadcast=false` in the chain anchor preview until a funded testnet deploy is
  intentionally run.
- x402 settlement is modeled on Base Sepolia because public facilitator support
  is mature there; Robinhood Chain receives the receipt anchor.
- The Sentinel contract is non-custodial and has no withdraw path.

## Next Buildathon Steps

1. ~~Run `python3 scripts/deploy_robinhood_chain.py --dry-run` once `py-solc-x`
   is available.~~ Superseded by the Forge build in CI
   (`.github/workflows/sentinel-contracts.yml`), which compiles the contract
   on every PR with the optimizer enabled and publishes a build artifact.
2. **(Ari)** Deploy `SapphireSentinelRegistry` to Robinhood Chain testnet with
   a funded testnet key.
3. **(Ari)** Replace the dry-run anchor preview with a
   `recordPaymentEvaluation(...)` transaction in testnet mode only.
4. ✅ Zama/FHEVM privacy mock — see `lib/hackathon/privacy_mock.py` (Lane A PR).
5. ✅ Multi-chain alpha verification — see `lib/hackathon/chain_health_gate.py` (Lane B PR), wired into `evaluate_attempt()`.
6. **(Ari)** Record a 90-second demo: approved payment, blocked injection attempt,
   Robinhood Chain explorer receipt, and non-submitting RWA order draft.
7. ✅ Forge test suite (18 cases) + Slither static-analysis CI —
   `tests/forge/SapphireSentinelRegistry.t.sol`,
   `.github/workflows/sentinel-contracts.yml`. Closes the smart-contract
   quality criterion gap flagged by Lane R PR #560.
