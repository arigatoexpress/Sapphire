# Sapphire Contracts Security Review — 2026-04-26

Reviewer: Claude (worktree security pass)
Branch reviewed: latest `main` (commit `7d13a0ac`)
Compiler: solc 0.8.20 (per `foundry.toml` and `scripts/deploy_robinhood_chain.py`)
Target chain: Robinhood Chain testnet, Arbitrum Orbit, chain id `46630`

This review consolidates the previously scattered audit notes for the two production
Solidity contracts in `contracts/`, the Foundry config, and the Python deployment path.
Findings are intended to drive a follow-up hardening PR; this PR is doc-only.

## Scope

In-scope artifacts (all paths repo-relative):

- `contracts/SapphireSignalVerifier.sol` — on-chain signal registry with operator-only
  publication and a reserved `proofHash` slot for future zk-verifiable computation.
- `contracts/SapphirePaymentGate.sol` — micropayment + subscription gate. Counterpart
  to the off-chain `lib/payments/x402_middleware.py`.
- `foundry.toml` — Foundry build config (src/out/libs paths, solc version, RPC).
- `scripts/deploy_robinhood_chain.py` — Python deploy harness (`web3.py` + `py-solc-x`).
  Provides `--check` preflight, `--dry-run` compile, and full deploy.

Out of scope: off-chain consumers (x402 middleware, signal logger, dashboard), prior
opus audit (`docs/opus-audit-2026-04-17.md`), and `lib/chain/robinhood_chain.py`
(read-only RPC client, no contract surface).

## SapphireSignalVerifier.sol

71-line registry. Single role (`operator`), single struct (`Signal`), three external
mutators, two views, one transfer. No imports, no inheritance, no libraries.

### `constructor()` — line 26
- **Input validation:** none. No constructor args.
- **Access control:** N/A (deployer becomes operator).
- **State mutation:** `operator = msg.sender`.
- **Events:** none. **No `OperatorTransferred(address(0), msg.sender)` emitted at
  deployment** — observers cannot reconstruct operator history from logs alone.
- **Reverts:** none.
- **Concerns:** Operator role is implicit and tied to the deploying EOA. If deployment
  is broadcast from a hot key (which `scripts/deploy_robinhood_chain.py` does — the
  key lives at `~/.config/sapphire-secrets/robinhood_deploy_key`), the contract is
  born owned by a hot key.

### `publishSignal(bytes32, string calldata, uint8, uint16, bytes32) external onlyOperator returns (uint256)` — line 30
- **Input validation:** none. **Direction is declared as 0=neutral / 1=long / 2=short
  but values 3-255 are accepted.** **Confidence is documented as basis points (0-10000)
  but values up to 65535 are accepted.** `symbol` length is unbounded (storage cost
  scales with caller-supplied bytes). `strategyId` and `proofHash` may be `bytes32(0)`.
- **Access control:** `onlyOperator`. Single-key.
- **State mutation:** `signalCount++` (post-increment, so id starts at 0 and the new
  count after `publishSignal` is `id + 1`); writes the full struct to `signals[id]`.
  Uses `block.timestamp` for the timestamp field.
- **Events:** `SignalPublished(id, symbol, direction, confidence)`. `proofHash` and
  `strategyId` are NOT in the event — off-chain indexers must call back into storage
  to retrieve them, defeating part of the value of indexed logs.
- **Reverts:** only `Not operator` from the modifier.
- **Gas:** dominated by `string` storage write — every additional 32 bytes of `symbol`
  costs ~22k gas. A malicious operator (or a compromised one) can push arbitrarily
  large strings.
- **Reentrancy / front-running:** no external calls; reentrancy not applicable.
  Front-running by the operator against itself is not meaningful. Public observers
  can front-run consumers of the signal stream off-chain, but that is a property of
  publishing on-chain, not a contract bug.
- **Integer over/underflow:** Solidity 0.8 has checked arithmetic, so `signalCount++`
  reverts on overflow at `2**256-1`. Practically impossible to hit.
- **Storage collision:** none — single contract, no proxy.

### `getSignal(uint256 id) external view returns (Signal memory)` — line 43
- **Input validation:** none. Returns zeroed struct for unset ids — no revert,
  caller must distinguish "no signal" from "zeroed signal".
- **Access control:** none (public view).
- **State mutation:** none.
- **Concerns:** the silent-zero behaviour is a foot-gun for off-chain consumers.
  Recommend `require(id < signalCount, "id out of range")`.

### `getLatestSignals(uint256 count) external view returns (Signal[] memory)` — line 47
- **Input validation:** none. `count == 0` returns the entire history (because
  `signalCount > 0` is true and `signalCount - 0 == signalCount`, so the loop runs
  from 0 to `signalCount`). This is the opposite of what the name suggests.
- **Access control:** none (public view).
- **State mutation:** none.
- **Gas / unbounded loop:** **the loop is bounded by the caller-supplied `count` only
  in the lower direction.** Once `signalCount` exceeds the RPC `eth_call` gas limit
  (~30M on Arbitrum Orbit), this view stops being callable. At ~21k gas per `Signal`
  copy plus the dynamic `string symbol` decode, that ceiling is in the low thousands
  to tens of thousands of signals depending on symbol length. Off-chain indexers
  should rely on events, not this view, for historical reads.
- **Off-by-one note:** the implementation copies `signals[start..signalCount-1]` into
  `result[0..signalCount-start-1]` — correct.

### `transferOperator(address newOperator) external onlyOperator` — line 56
- **Input validation:** `newOperator != address(0)`.
- **Access control:** `onlyOperator`.
- **State mutation:** `operator = newOperator`.
- **Events:** **none** — the on-chain audit trail of role changes is empty.
- **Reverts:** zero-address check; no contract-deployer guard.
- **Concerns:** **single-step transfer.** A typo or a transfer to an address whose
  private key is unknown (e.g. a contract address with no owner, or a yet-to-be-funded
  multisig) permanently bricks `publishSignal` and `transferOperator`. The standard
  fix is a two-step `pendingOperator → acceptOperator` flow (OpenZeppelin
  `Ownable2Step`).

### Declared but unused

- `event SignalVerified(uint256 indexed id, bytes32 proofHash);` — declared on
  line 19, never emitted. Either dead code (the verification path was scoped out)
  or a missing function. Should either be removed or the verification path added.

### Other observations

- No pause / kill-switch — if the operator key leaks, there is no recovery short of
  redeploying.
- No upgrade path. This is a feature for trust-minimisation, but if the team intends
  to add a real zk-proof verifier later, a UUPS or beacon proxy should be planned now.
- No reentrancy guard imported — fine, no external calls.

## SapphirePaymentGate.sol

71-line gate. Two roles via one variable (`treasury`), two `mapping` ledgers
(`credits` and `subscriptionExpiry`), two payable functions, one consume, three
treasury-only setters/transfers, two views.

### `constructor()` — line 21
- **Input validation:** none.
- **Access control:** N/A.
- **State mutation:** `treasury = msg.sender`. Hardcoded `pricePerSignal = 0.001 ether`
  and `monthlySubscription = 0.1 ether`.
- **Events:** **none.** Same blind-deployment problem as the verifier.
- **Concerns:** The price comments say "~$0.003" and "~$300" but the contract
  measures in the chain's native token. Robinhood Chain testnet uses test ETH; if
  mainnet is RBT or any other native asset, the dollar comments will become stale.
  Prefer either oracle-priced quotes or USD-denominated stablecoin payments.

### `payPerSignal() external payable` — line 25
- **Input validation:** `msg.value >= pricePerSignal`.
- **Access control:** none.
- **State mutation:** `credits[msg.sender] += msg.value / pricePerSignal`.
- **Events:** `PaymentReceived(msg.sender, msg.value, "signal")`.
- **Reverts:** "Insufficient payment".
- **Concerns:**
  - **Division by zero (HIGH).** If `treasury` ever calls
    `setPricePerSignal(0)`, every subsequent `payPerSignal()` reverts on the
    `msg.value / 0` panic. Not a fund-loss bug, but a permanent DoS on the credit
    rail until `setPricePerSignal` is corrected. `setPricePerSignal` does not guard
    against zero.
  - **Dust loss (MEDIUM).** Integer division silently rounds down. A user paying
    `0.0015 ether` with `pricePerSignal = 0.001 ether` gets 1 credit and donates
    `0.0005 ether` to the contract balance with no record of the surplus.
    For a 0.001-ether unit price the worst case is one full unit minus 1 wei.
    Either refund the remainder, store it as a fractional credit, or revert on
    non-integer multiples.
  - **Treasury front-running (LOW/centralisation).** The treasury can observe a
    user's `payPerSignal` tx in mempool and frontrun it with `setPricePerSignal`.
    Pricing is centrally controlled anyway, so this is a property of the trust
    model, not a bug. Document it.
  - **No reentrancy guard.** No external calls in this function — safe today.
- **Gas:** constant (one mapping write, one event).

### `subscribe() external payable` — line 31
- **Input validation:** `msg.value >= monthlySubscription`.
- **Access control:** none.
- **State mutation:** sets `subscriptionExpiry[msg.sender]` to `max(current, block.timestamp) + 30 days`.
  Correctly stacks an extension on top of an unexpired sub instead of resetting it.
- **Events:** `SubscriptionActivated`, `PaymentReceived`.
- **Reverts:** "Insufficient payment".
- **Concerns:**
  - **No proportionality check.** A user paying `2 * monthlySubscription` still gets
    only 30 days. Either accept multiples (`base + 30 days * (msg.value / monthlySubscription)`)
    or revert / refund on overpayment. Same shape as the dust issue above but the
    failure mode is "user got less than they paid for", which is worse.
  - **Same `setMonthlySubscription` front-run window** as `payPerSignal` /
    `setPricePerSignal`.
- **Gas:** constant.

### `consumeCredit(address user) external onlyTreasury` — line 40
- **Input validation:** `credits[user] > 0`.
- **Access control:** `onlyTreasury`.
- **State mutation:** `credits[user]--`.
- **Events:** `CreditsConsumed(user, credits[user])`.
- **Reverts:** "No credits".
- **Concerns:**
  - **Centralisation / scalability.** Every consume requires a tx from the treasury
    EOA. At even modest signal-call volume the treasury becomes a bottleneck and
    pays gas for every consume. Consider:
    - Allow the user to consume their own credit (with a backend-signed permit).
    - Batch via `consumeCredits(address[] users)` to amortise tx overhead.
    - Move credits off-chain entirely (signed receipts redeemed in batches).
  - **No event-side proof of which service was billed.** `CreditsConsumed` does not
    include a service id or call-hash, so the on-chain ledger cannot reconcile
    against the off-chain x402 logs.

### `hasAccess(address user) external view returns (bool)` — line 46
- Pure view; no concerns. Logic is `subscribed OR credits > 0`. Correct.

### `isSubscribed(address user) external view returns (bool)` — line 50
- Pure view; no concerns.

### `setPricePerSignal(uint256 price) external onlyTreasury` — line 54
- **Input validation:** **none. Allows zero.** See division-by-zero above.
- **Events:** **none.** Price changes leave no on-chain audit trail.
- **Recommendation:** `require(price > 0, "Zero price")` and emit a
  `PriceUpdated(uint256 oldPrice, uint256 newPrice)` event.

### `setMonthlySubscription(uint256 price) external onlyTreasury` — line 58
- **Input validation:** **none. Allows zero.** Setting to zero would let any caller
  with `msg.value >= 0` (i.e. anyone) extend their subscription by 30 days for free.
  `require(msg.value >= monthlySubscription)` with `monthlySubscription = 0` is
  trivially satisfied by `msg.value = 0`.
- **Events:** **none.**
- **Recommendation:** `require(price > 0, "Zero price")` and emit an event.

### `withdraw() external onlyTreasury` — line 62
- **Input validation:** none.
- **Access control:** `onlyTreasury`.
- **State mutation:** `payable(treasury).transfer(address(this).balance)`.
- **Events:** **none.**
- **Concerns:**
  - **`.transfer()` 2300-gas stipend (MEDIUM).** If the treasury is later migrated
    to a smart-contract account (multisig, account-abstraction wallet, or Safe),
    `.transfer()` will revert because typical wallet receive-hooks consume more
    than 2300 gas. **The funds become stuck.** Best practice since EIP-1884:
    `(bool ok, ) = payable(treasury).call{value: address(this).balance}(""); require(ok, "transfer failed");`
    Combine with a `nonReentrant` modifier (the only externally-callable mutator
    that triggers an external call, so reentrancy risk is theoretical, but cheap
    to defend against).
  - **No partial withdraw.** Only "drain the whole contract". A bug in the gate
    (e.g. an over-charge by a misconfigured x402) cannot be reimbursed without
    redeploying.
  - **No event.** Off-chain accounting cannot reconcile balance changes from logs
    alone.

### `transferTreasury(address newTreasury) external onlyTreasury` — line 66
- **Input validation:** `newTreasury != address(0)`.
- **Access control:** `onlyTreasury`.
- **State mutation:** `treasury = newTreasury`.
- **Events:** **none.**
- **Concerns:** Same single-step / no-event pattern as `transferOperator`.
  Recommend `Ownable2Step`.

### Other observations

- No pause mechanism. Combined with the unbounded `setPricePerSignal(0)` issue, an
  operator-key compromise can DoS the contract.
- No event on `pricePerSignal` / `monthlySubscription` initialisation in the
  constructor.
- No `receive()` / `fallback()` — direct ETH transfers without going through
  `payPerSignal` / `subscribe` revert. Good (avoids "lost ETH" support tickets),
  but also means a misclicked transfer is just bounced rather than collected.

## Cross-contract concerns

The two contracts share **no on-chain coupling** — `SapphireSignalVerifier` does not
check `SapphirePaymentGate.hasAccess()` before publishing, and `SapphirePaymentGate`
has no awareness of the verifier. All gating is performed off-chain by
`lib/payments/x402_middleware.py` plus the inference proxy.

That decoupling has consequences:

1. **Single-key compounding.** `scripts/deploy_robinhood_chain.py` deploys both
   contracts from one EOA (the key at `~/.config/sapphire-secrets/robinhood_deploy_key`).
   That EOA becomes both `operator` (verifier) and `treasury` (gate). A compromise of
   that single hot key gives an attacker:
   - The ability to publish arbitrary trading signals (reputational + market-impact
     risk).
   - The ability to drain the gate via `withdraw()`.
   - The ability to brick both contracts via single-step role transfer.
   The deploy script does not transfer either role to a multisig automatically.
   **First post-deploy action MUST be a `transferOperator` and `transferTreasury`
   to a hardware-wallet or multisig.**

2. **Off-chain authorisation bypass.** Because `publishSignal` is gated by
   `onlyOperator` and not by "the caller paid via PaymentGate", a compromise of the
   x402 middleware (HTTP-layer) does not currently gain on-chain abilities. Good.
   The reverse — a compromise of the on-chain operator key — does not let the
   attacker collect payments either. Roles are properly siloed at the contract
   layer, but they collapse to a single key at the deployment layer (see point 1).

3. **No shared role registry.** If the project later wants "anyone with `Role.PUBLISHER`
   can publish signals; anyone with `Role.TREASURY_OPS` can withdraw; both can be
   delegated independently", the current design needs a refactor to OpenZeppelin
   `AccessControl`. Worth doing before the role surface grows further.

4. **No coupling to the proof-hash field.** `SapphireSignalVerifier.publishSignal`
   accepts a `proofHash` but never verifies it. `SapphirePaymentGate` has no
   awareness of it either. The dead `SignalVerified` event suggests a
   `verifySignal(uint256 id, bytes proof)` was once planned but not landed. Either
   land it (with a real verifier contract) or remove the proof-hash argument and
   the dead event so the surface area accurately describes capabilities.

## Findings

| Sev      | Title                                                       | Location                                       | Description                                                                                                                                                                                                                              | Recommended fix                                                                                                                                       |
|----------|-------------------------------------------------------------|------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------|
| High     | DoS via `setPricePerSignal(0)` causes division panic        | `SapphirePaymentGate.sol:54` (and `:25`)       | `setPricePerSignal` accepts zero with no validation; a subsequent `payPerSignal` panics on `msg.value / 0` and reverts. Bricks credit purchases until the price is corrected.                                                            | `require(price > 0, "Zero price")` in both setters. Consider a min/max bound, too.                                                                    |
| High     | `setMonthlySubscription(0)` lets anyone subscribe for free  | `SapphirePaymentGate.sol:58` (and `:31`)       | If `monthlySubscription` is set to 0, `require(msg.value >= 0)` is trivially true and any caller gets a 30-day subscription for 0 wei.                                                                                                   | `require(price > 0, "Zero price")` in the setter.                                                                                                     |
| High     | Single-step role transfer can permanently brick both contracts | `SapphireSignalVerifier.sol:56`, `SapphirePaymentGate.sol:66` | A typo or transfer to an unowned address (contract with no owner, unfunded multisig before deployment) makes `publishSignal`, `consumeCredit`, `withdraw`, `setPricePerSignal`, `setMonthlySubscription`, and the role transfers themselves unreachable. | Use OpenZeppelin `Ownable2Step` (pending → accept) for both roles.                                                                                    |
| High     | Deployment leaves operator + treasury on a single hot key   | `scripts/deploy_robinhood_chain.py:267-287`    | One EOA controls both contracts. A compromise of the deploy key drains the gate and lets the attacker publish arbitrary signals.                                                                                                         | Add a post-deploy step (or a runbook) that transfers both roles to a multisig before any payment is accepted, and verifies the transfer on-chain.     |
| Medium   | Dust loss on overpayment in `payPerSignal`                  | `SapphirePaymentGate.sol:25-29`                | Integer division silently rounds down — overpaying users donate the remainder.                                                                                                                                                           | Either revert on non-integer multiples, refund the remainder via `call{value:dust}("")`, or carry the surplus as fractional credit.                   |
| Medium   | Overpayment on `subscribe` does not extend coverage         | `SapphirePaymentGate.sol:31-38`                | Paying 2x or 3x the price still grants 30 days. User loses funds.                                                                                                                                                                        | Either refund the surplus, or scale: `base + 30 days * (msg.value / monthlySubscription)`.                                                            |
| Medium   | `withdraw()` uses `.transfer()` (2300-gas stipend)          | `SapphirePaymentGate.sol:63`                   | If treasury is migrated to a smart-contract account (multisig / Safe / 4337 wallet), `.transfer()` reverts and funds get stuck.                                                                                                          | Switch to `(bool ok, ) = payable(treasury).call{value: bal}(""); require(ok, "transfer failed");` and add a `nonReentrant` guard for hygiene.         |
| Medium   | Missing input validation in `publishSignal`                 | `SapphireSignalVerifier.sol:30-41`             | `direction > 2`, `confidence > 10000`, empty `symbol`, zero `strategyId`/`proofHash`, and unbounded-length `symbol` are all accepted. The struct comments document tighter constraints than the contract enforces.                       | Add `require` checks per the documented constraints; cap `bytes(symbol).length` at e.g. 32.                                                           |
| Medium   | `getLatestSignals` is unbounded                             | `SapphireSignalVerifier.sol:47-54`             | Loop iterates over all stored signals up to `signalCount`. As the registry grows, eth_call gas limits will block this view; off-chain indexers should not rely on it.                                                                    | Document that off-chain consumers must use events for backfill; optionally require `count > 0` and clamp `count` to a sane max (e.g. 256).            |
| Medium   | Dead `SignalVerified` event + unused `proofHash`            | `SapphireSignalVerifier.sol:11, 19`            | The contract advertises a verifiable-computation surface it does not implement. Off-chain consumers cannot tell which signals are "verified" vs "registered".                                                                            | Either implement `verifySignal(uint256 id, bytes proof)` with a real verifier, or remove the proof-hash argument and the dead event.                  |
| Low      | No events on role transfer / price changes / withdraw       | `SapphirePaymentGate.sol:54, 58, 62, 66`; `SapphireSignalVerifier.sol:56` | Privileged actions leave no log. Reconstructing operator history requires storage reads, not log scans.                                                                                                                                   | Add `OperatorTransferred`, `TreasuryTransferred`, `PriceUpdated`, `SubscriptionPriceUpdated`, `Withdrawal` events.                                    |
| Low      | `getSignal` returns zero-struct for unknown ids             | `SapphireSignalVerifier.sol:43-45`             | Silent zero-return can hide bugs in callers that forgot to range-check.                                                                                                                                                                  | `require(id < signalCount, "id out of range")`.                                                                                                       |
| Low      | `proofHash` and `strategyId` not in `SignalPublished` event | `SapphireSignalVerifier.sol:18, 38`            | Indexers must do an extra `getSignal` call to retrieve them. Adds per-signal RPC load.                                                                                                                                                   | Include both fields in the event (mark `strategyId` `indexed` for filtering).                                                                         |
| Low      | `consumeCredit` requires a treasury tx per call             | `SapphirePaymentGate.sol:40-44`                | Treasury pays gas for every consume; throughput is bounded by treasury nonce velocity. Centralisation chokepoint.                                                                                                                        | Add a batched `consumeCredits(address[] users)`, or move to user-signed permits redeemed in batches.                                                  |
| Low      | No pause / kill-switch on either contract                   | both                                           | If a key leaks, the only recovery is redeploy. Existing users' subscriptions and credits are lost.                                                                                                                                       | Add a `Pausable`-style guard on `publishSignal`, `payPerSignal`, `subscribe`, and `consumeCredit`. Keep `withdraw` and role transfer pause-immune.    |
| Info     | No constructor event / on-chain initialisation log          | both                                           | `OperatorTransferred(0, msg.sender)` / `TreasuryTransferred(0, msg.sender)` would let observers detect deployment from logs.                                                                                                             | Emit a constructor event in both contracts.                                                                                                           |
| Info     | Hardcoded native-asset prices with USD-denominated comments | `SapphirePaymentGate.sol:9-10`                 | Comments will go stale as the native-asset price moves.                                                                                                                                                                                  | Either remove the dollar comments, or move to stablecoin payments, or quote via Chainlink-style oracle.                                               |
| Info     | No reentrancy guard imports                                 | both                                           | Currently safe because no external calls are made from mutators. Future-proofing only.                                                                                                                                                   | Inherit `ReentrancyGuard` once `withdraw()` is converted to `.call` (see Medium above).                                                               |

Counts: Critical 0, High 4, Medium 6, Low 5, Info 3. Total 18.

## Test coverage

**No Foundry test suite exists.** The repo has no `test/` directory at root, no
`*.t.sol` files anywhere, no `contracts/test/`, and no `contracts/lib/` (the
`libs = ["contracts/lib"]` entry in `foundry.toml` points at a directory that does
not exist). The project tests Python code via pytest (2,209 + 78 plugin tests) but
has zero on-chain test coverage.

**`forge` is not installed in this worktree** (`which forge` returns "not found"),
and per the task constraints we did not install it — so this PR cannot scaffold a
runnable suite. The recommended minimum suite for the next PR (which someone with
Foundry locally should land) is:

`test/SapphireSignalVerifier.t.sol`
- `test_constructor_setsOperatorToDeployer`
- `test_publishSignal_revertsForNonOperator`
- `test_publishSignal_incrementsSignalCount`
- `test_publishSignal_emitsSignalPublished` (asserts indexed `id` matches return)
- `test_publishSignal_storesAllFields` (round-trips through `getSignal`)
- `test_publishSignal_acceptsInvalidDirectionAndConfidence` (documents current
  permissive behaviour; flip to "reverts" once validation lands)
- `test_getLatestSignals_returnsTailWhenCountSmaller`
- `test_getLatestSignals_returnsAllWhenCountLarger`
- `test_getLatestSignals_emptyHistoryReturnsEmptyArray`
- `test_transferOperator_revertsOnZeroAddress`
- `test_transferOperator_revertsForNonOperator`
- `test_transferOperator_oldOperatorLosesAccess`
- `testFuzz_publishSignal_directionConfidenceProofHash` (fuzz over the three numeric
  fields and assert they round-trip)

`test/SapphirePaymentGate.t.sol`
- `test_constructor_setsTreasuryAndDefaults`
- `test_payPerSignal_creditsRoundDown`
- `test_payPerSignal_revertsOnInsufficientPayment`
- `test_payPerSignal_revertsWhenPriceIsZero` (this is the High finding — once fixed,
  the assertion flips from "panics" to "reverts with Zero price")
- `test_payPerSignal_emitsPaymentReceived`
- `test_subscribe_extendsActiveSubscription` (asserts `base = current` branch)
- `test_subscribe_resetsExpiredSubscription` (asserts `base = block.timestamp` branch)
- `test_subscribe_revertsOnInsufficientPayment`
- `test_subscribe_revertsWhenPriceIsZero` (after fix)
- `test_consumeCredit_revertsForNonTreasury`
- `test_consumeCredit_revertsWhenNoCredits`
- `test_consumeCredit_decrementsAndEmits`
- `test_hasAccess_subscriberWithoutCreditsReturnsTrue`
- `test_hasAccess_creditHolderWithoutSubscriptionReturnsTrue`
- `test_hasAccess_neitherReturnsFalse`
- `test_setPricePerSignal_onlyTreasury`
- `test_setMonthlySubscription_onlyTreasury`
- `test_withdraw_onlyTreasury_drainsBalance`
- `test_withdraw_revertsForSmartContractTreasury` (after `.transfer()` → `.call` fix)
- `test_transferTreasury_revertsOnZeroAddress`
- `test_transferTreasury_oldTreasuryLosesAccess`
- `testFuzz_payPerSignal_creditAccounting` (fuzz `msg.value` and `pricePerSignal`,
  assert `credits = msg.value / pricePerSignal`)

Coverage target: ≥95% line + branch on both contracts. Foundry's `forge coverage`
report should be checked into CI alongside Python coverage.

## Recommendations

Prioritised, with suggested PR boundaries:

1. **Land High-severity fixes first** (one PR per contract, doc-anchored to this
   review):
   - `SapphirePaymentGate`: `require(price > 0)` in both setters; `Ownable2Step`
     for treasury; `.transfer()` → `.call`; emit events on price + role + withdraw.
   - `SapphireSignalVerifier`: `Ownable2Step` for operator; emit event on transfer
     and on constructor; tighten `publishSignal` input validation.
2. **Install Foundry locally** (CI-side, since `forge` is not available in the
   worktree environment) and **scaffold the test suite above** in a follow-up PR.
   Wire `forge test` and `forge coverage` into `.github/workflows/ci.yml`.
3. **Pre-deployment runbook**: deploy to a multisig owner, not an EOA. The deploy
   script should optionally accept `--owner` and call `transferOperator` /
   `transferTreasury` in the same broadcast block. Document in
   `docs/crypto-integrations-plan.md`.
4. **Decide the proof-hash story.** Either implement
   `verifySignal(uint256 id, bytes proof)` (and the matching off-chain prover) or
   remove the field and the dead event so the public surface honestly reflects what
   the contract does.
5. **Medium fixes** (consolidated PR after High):
   - Dust refund / proportional subscription extension.
   - Bound `getLatestSignals` and document event-based historical reads.
   - Add `Pausable` to mutators (omit role transfer + withdraw).
6. **Low + Info polish PR** at the end: full event coverage, range-checked
   `getSignal`, oracle-based or stablecoin pricing.
7. **Long-term** — once role surface exceeds two principals, migrate to OpenZeppelin
   `AccessControl` and consider a UUPS proxy if the verifier is expected to evolve.

This review is doc-only; no `.sol`, `foundry.toml`, or deploy script was modified.

## 2026-04-26 follow-up — High findings landed

Branch: `feat/contracts-high-findings-2026-04-26`. PR title: `Address High findings
from contracts review (2026-04-26)`. Scope is strictly the four High items from
the table above; Medium / Low / Info polish is left for follow-up PRs.

### Addressed in this PR

1. **DoS via `setPricePerSignal(0)`** — fixed in `SapphirePaymentGate.sol` by
   adding `require(price > 0, "Zero price");` to `setPricePerSignal`. Natspec
   updated to call out the rationale and the link back to this review.
2. **`setMonthlySubscription(0)` lets anyone subscribe for free** — fixed in
   `SapphirePaymentGate.sol` by adding `require(price > 0, "Zero price");` to
   `setMonthlySubscription`. Natspec updated.
3. **Single-step role transfer** — both contracts now use a hand-rolled
   two-step transfer (no OpenZeppelin dependency added, per the PR
   constraints):
   - `SapphireSignalVerifier.sol`: new `address public pendingOperator;`
     storage slot, new `acceptOperator()` external function,
     `transferOperator` now nominates rather than mutates. New events
     `OperatorTransferStarted(previousOperator, newOperator)` and
     `OperatorTransferred(previousOperator, newOperator)`.
   - `SapphirePaymentGate.sol`: symmetric — `pendingTreasury` slot,
     `acceptTreasury()` function, `TreasuryTransferStarted` and
     `TreasuryTransferred` events.

   Existing public ABI surfaces (`transferOperator(address)` /
   `transferTreasury(address)` selectors, plus all storage getters and other
   functions) are preserved — only their behaviour changes (now they nominate
   instead of mutating). New functions and storage are additive.

### Deferred

4. **Deployment leaves operator + treasury on a single hot key** — runbook /
   process finding, not a contract change. The PR constraints explicitly
   forbid edits to `scripts/deploy_robinhood_chain.py`, so the recommended
   `--owner` flag and post-deploy `transferOperator` / `transferTreasury` block
   are out of scope here. The mitigation is documented at
   `docs/crypto-integrations-plan.md` and is now strictly stronger thanks to
   the two-step transfer landed in this PR — a single-key deploy can still
   nominate a multisig as the new role-holder, and the multisig must
   explicitly call `acceptOperator` / `acceptTreasury` before the takeover
   completes. A follow-up PR should land the deploy-script change separately.

### Test coverage added

`tests/unit/test_contracts_abi.py` — 41 text-level smoke tests over both
`.sol` files. Covers (a) presence of the new error strings and event
signatures, (b) the new two-step storage slots and accept functions, and (c)
preservation of every previously-public ABI surface. These do not replace a
real Foundry suite (still recommended in the section above) — they are a
lightweight CI guard against accidental regression of this PR's changes.

`forge` remains uninstalled in the CI environment, so a runnable Foundry
suite is still deferred to a follow-up PR.

