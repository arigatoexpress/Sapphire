# Pre-flight audit — trading critical path
**Date**: 2026-05-02
**Auditor**: autonomous lane (Lane J), read-only
**Scope**: MegaETH executor scaffold (PR #527, branch `feat/megaeth-executor-scaffold`) + Hyperliquid live executor (in `origin/main`) + cross-cutting safety
**Base**: `origin/main` @ `f2955ff6` ("feat(megaeth): read-only RPC client + plugin tool")
**Method**: Static read of source + tests under a fresh worktree. No code executed. No network calls. No edits to `lib/trading/`, `plugins/claw-sapphire/tools/internal/`, `services/hyperliquid/`, or `services/megaeth-ingest/`.

## Verdict
**SOFT-GAPS-ONLY** — no hard gaps that should block flipping `signing_verified=True` on Wave C, given the qualifier that the flip is performed against the **MegaETH testnet** path, not mainnet, and that a post-flip operator review of the recommended checklist below is completed first.

The Hyperliquid path is more battle-tested than the MegaETH scaffold (it has a real signing round-trip via `hyperliquid_bot/signing.py`, 17 risk tests, 38+ signing tests, and a registered read-only inspector tool). The MegaETH scaffold is correctly scoped to a signing primitive with no broadcast path; flipping `signing_verified=True` does **not** by itself enable mainnet sends because the scaffold has no broadcast call at all — a future caller must add one explicitly. That asymmetry is an intentional design strength.

## MegaETH executor (PR #527 — `feat/megaeth-executor-scaffold`)

| Gate | Status | Evidence |
|---|---|---|
| `signing_verified: bool = False` default | PRESENT | `megaeth_executor.py:95`; test `test_signing_verified_default_is_false` (test:338) |
| Killswitch `~/.sapphire/megaeth_trading_pause` checked on every send | PRESENT | `KILLSWITCH_PATH_DEFAULT` (54), `killswitch_active()` (112), checked at `send_transaction` (293); test `test_killswitch_present_refuses_send` (154) |
| Per-order cap = $5 | PRESENT | `MegaETHLivePolicy.max_order_notional_usd: float = 5.0` (88); enforced (300); test `test_per_order_cap_exceeded_refuses` (165) |
| Daily loss cap = $25 with persisted state | PRESENT | `daily_realized_loss_cap_usd: float = 25.0` (89); persisted at `data/megaeth_daily_pnl.json` via `record_realized_pnl` (134); enforced (304); test `test_daily_loss_cap_persists_and_blocks` (188) covers cross-process persistence |
| Mainnet chain_id constant pinned (4326) | PRESENT | `MAINNET_CHAIN_ID: int = 4326` (61); test `test_mainnet_chain_id_is_pinned` (323) hard-asserts the canonical value with a comment requiring an audit if it drifts |
| `signing_verified=False` + mainnet → refuses | PRESENT (defense-in-depth) | Refused in constructor (251) **and** re-checked in `send_transaction` (311); two tests cover both layers (116, 208) |
| `SAPPHIRE_MEGAETH_TESTNET_KEY` env required | PRESENT | Read at sign-time only, never cached (335); explicit error `missing_signing_key_env` (337); test `test_missing_env_key_refuses_with_clear_error` (252) |
| No broadcast helper anywhere in the module | PRESENT | Module body never references `eth_sendRawTransaction` / `eth_sendTransaction`; signing returns hex but no RPC call follows; module-level test `test_no_broadcast_path_in_module` (348) source-greps the forbidden tokens and asserts the SendResult statuses are exactly `{signed_dry_run, blocked, error}` — `broadcast` is not a permitted status |
| Tx `chainId` mismatch refused | PRESENT | (319) blocker `tx_chain_id_mismatch`; test (263) |
| Trade log appended on every result (incl. blocked) | PRESENT | `_log()` always called in every code path (331, 346, 363, 381); test (295) |
| Scaffold not registered in `tool-registry.yaml` / `agent-manifest.yaml` | PRESENT | grep confirms scaffold is not exposed as a plugin tool (the registered `megaeth` tool is the read-only RPC client, not the executor) |

**One nit (not a gap):** the constructor accepts `per_order_cap_usd` and `daily_loss_cap_usd` kwargs that allow callers to lower caps — but a coding error could just as easily *raise* them. The `__post_init__` validator only rejects ≤ 0 values, not values exceeding the dataclass defaults. In practice this is fine because `signing_verified` still gates mainnet, but a future hardening could clamp incoming caps to the policy maxima.

## Hyperliquid live executor (`services/hyperliquid/src/hyperliquid_bot/risk.py`, in main)

| Gate | Status | Evidence |
|---|---|---|
| Per-order cap = $5 | PRESENT | `max_order_notional_usd: float = 5.0` (50); enforced via `bounded_notional` (148); test `test_evaluate_risk_caps_oversized_order` |
| Per-trade leverage cap = 3x | PRESENT | `max_leverage: float = 3.0` (51); test `test_evaluate_risk_caps_oversized_leverage` |
| Max simultaneous open positions = 5 | PRESENT | `max_open_positions: int = 5` (52); test `test_evaluate_risk_blocks_when_max_positions_reached` |
| Daily loss cap = $25 with persisted state | PRESENT | `daily_realized_loss_cap_usd: float = 25.0` (53); persisted at `data/hyperliquid_daily_pnl.json` via `record_realized_pnl` (190); test `test_evaluate_risk_blocks_when_daily_loss_cap_reached` + `test_record_realized_pnl_accumulates_loss` |
| Killswitch `~/.sapphire/hyperliquid_trading_pause` | PRESENT | `KILLSWITCH_PATH_DEFAULT` (34); `killswitch_active()` (172); state pulled in `_snapshot_state` (388); test `test_evaluate_risk_blocks_when_killswitch_active` + `test_killswitch_active_reflects_file_presence` |
| `signing_verified` flag | PRESENT | `signing_verified: bool = False` (61); refused in `HyperliquidLiveExecutor.__init__` (311); tests `test_executor_refuses_mainnet_until_signing_verified` + `test_executor_allows_mainnet_when_signing_marked_verified` |
| Testnet vs mainnet gating | PRESENT | `HYPERLIQUID_TESTNET=1` default in `main.py:_resolve_testnet` (60); mainnet refused unless `signing_verified=True` |
| Trading-enabled env gate (default off) | PRESENT | `HYPERLIQUID_TRADING_ENABLED=0` default (317); enforced in both `evaluate_risk` (128) and the dry-run branch (335) — defense-in-depth |
| Env-driven key loading, no hardcoded keys | PRESENT | `load_private_key()` (217) tries macOS keychain first, falls back to `HYPERLIQUID_PRIVATE_KEY` env; never reads from disk; refuses to start if neither has a key (`main.py:90`) |
| Signing scheme verified | PRESENT | Real EIP-712 phantom-agent flow in `signing.py`; round-trip recovery test (`test_hyperliquid_signing.py`, 38 tests) including domain pinning, nonce/vault/expiry differentiation, and mainnet/testnet `source` flag |
| Read-only inspector tool | PRESENT | `plugins/claw-sapphire/tools/internal/hyperliquid.py` `live-status` action surfaces killswitch state, trading-enabled flag, today's daily loss, recent trades — without touching network or wallet |
| Idempotency (no duplicate fills on retry) | **WEAK** | `_exchange_action` uses `nonce = int(time.time() * 1000)` (client.py:189). Two retries within the same millisecond would produce identical nonces; the API would reject the duplicate, but there is no application-layer dedup or retry policy. No test exercises the retry path. |

### Live-trade record reconciliation

The first live BTC fill recorded in the repo is in `data/trading/robinhood_manual_orders.jsonl`, not the Hyperliquid path. The order details:

- `2026-04-28T04:06:03Z` — Robinhood Crypto BTC-USD limit order, `quote_amount=$5.00`, `limit_price=$76787.00`, `client_order_id=cf3b994c-...`, `state=open` at submission.
- `safety` block records: `dry_run_default=true, limit_orders_only=true, requires_typed_confirmation=true`.

**Discrepancy with memory note**: memory says `$76,774.81`. The repo record shows the **limit price** of `$76787.00` (and a separate field `submit_response.average_price=null` because the fill price was recorded later by Robinhood). The memory's `$76,774.81` is plausibly the actual fill price reported by the Robinhood API on a follow-up read, but **that fill price is not in the repo's `system_events.jsonl` or any other persisted file I could find**. Recommend writing the actual fill price + average_price into the same JSONL row when the order moves from `open` → `filled`, so the audit trail is self-contained.

This trade was on **Robinhood Crypto**, not Hyperliquid — the Hyperliquid live path has not yet placed a real order in the repo's history. That matches the activation posture: HL is gated until `signing_verified=True`, and the first-trade memory line is about the Robinhood pilot rung.

## Surprises found

1. **Two additional broadcast paths exist outside the trading critical path**, both confirmed read in this audit and both are signal-anchoring (publishing a `bytes32` strategy hash to a verifier contract), not fund movement:
   - `lib/chain/robinhood_chain.py:300` — `RobinhoodChainClient.publish_signal()` calls `account.sign_transaction(tx)` then `w3.eth.send_raw_transaction(...)`. Reads private key from constructor argument only (no implicit env load), no killswitch, no per-tx caps. Used for anchoring strategy signals to a Robinhood Chain testnet contract.
   - `lib/og/chain.py:136` — `publish_signal()` reads `OG_PRIVATE_KEY` env and broadcasts to `SapphireSignalVerifier` on 0G chain. No killswitch, no caps.
   - **Risk class**: gas-only spend on testnets, but each call is a real signed broadcast. Worth flagging because they meet the literal definition of "broadcast paths outside the executor modules" in the audit checklist. Recommendation: add a single `~/.sapphire/chain_anchor_pause` killswitch checked by both, and write a `data/chain_anchor_log.jsonl` audit trail similar to the trading executors.
   - **Also** two deploy scripts (`scripts/deploy_robinhood_chain.py:118`, `scripts/deploy_og_chain.py:159`) sign + broadcast contract deployments. Operator-run only, not on any schedule, low concern.

2. **No hardcoded private keys** anywhere in the repo. Grep for `PRIVATE_KEY = "0x..."` and `private_key = "0x<64 hex>..."` returns nothing.

3. **Killswitch naming consistency**: only `~/.sapphire/hyperliquid_trading_pause` exists in main today. The MegaETH scaffold introduces `~/.sapphire/megaeth_trading_pause` as a sibling — same parent directory, same `_trading_pause` suffix. Pattern is consistent. No collision risk.

4. **Sentinel chain-health gate (PR #546) is NOT yet wired into either executor**, as expected. The chain-health logic exists on the `feat/sentinel-dashboard-chain-health` and `feat/megaeth-wave-b3-gmx-v2` branches (commits like `160f35df feat(sentinel): MegaETH chain-health gate`), and is referenced from `lib/hackathon/sentinel.py` and `services/dashboard/templates/pages/sentinel.html` only. Recommended wiring spot for a future PR: insert a `ChainHealthVerdict` check into `MegaETHExecutor.send_transaction` between the killswitch check (line 293) and the per-order cap check (line 297), and into `evaluate_risk` (services/hyperliquid/.../risk.py:121) immediately after the killswitch blocker (line 132).

5. **Routine safety**: surveyed `~/.claude/scheduled-tasks/` (23 routines). The only trading-touching ones are `trading-research` (paper-only, scores predictions) and `market-pulse` (paper-only, calls `paper_trader.py`). Neither imports the HL executor, neither references wallet keys, neither writes to `~/.sapphire/`. Each routine begins with a `~/.sapphire/routine_pause/<name>` check (per the #392 pattern). Confirmed safe.

## Hard gaps (must fix before Wave C)

NONE. The mainnet path on both executors is gated on `signing_verified=True` being a literal source-code edit, the MegaETH scaffold has no broadcast call to flip, and the Hyperliquid path has both a default-off `HYPERLIQUID_TRADING_ENABLED` env and a default-true `HYPERLIQUID_TESTNET` env — three independent gates layered above the code-edit gate.

## Soft gaps (recommend fix in next sprint)

1. **HL nonce collision on millisecond-clock retry** (`client.py:189`). Add an atomic counter or use `time.time_ns()` to make millisecond-collision impossible, and cover with a unit test that fires two `_exchange_action` calls back-to-back and asserts the second one's nonce is strictly greater than the first.
2. **Robinhood fill record incompleteness** (`data/trading/robinhood_manual_orders.jsonl`). The submission row is captured but no follow-up row records the actual fill price / fee / final state. Operator-trail gap, not a safety gap.
3. **Signal-anchor broadcast paths lack a killswitch** (`lib/chain/robinhood_chain.py:300`, `lib/og/chain.py:136`). Add a shared `~/.sapphire/chain_anchor_pause` file check.
4. **Constructor cap-override doesn't clamp** (`megaeth_executor.py:228`). A misconfigured caller could pass `per_order_cap_usd=500.0`. Consider clamping incoming overrides to the dataclass defaults in `__post_init__`.
5. **No idempotency / replay-protection test on the HL `_exchange_action` path** — pairs with #1.
6. **Chain-health gate (PR #546) not wired into either executor** — currently a follow-up but should be in the Wave C+1 sprint.
7. **The MegaETH scaffold's `signing_verified=True` test path uses a fake `MAINNET_CHAIN_ID=99999`** (test:120). Once mainnet is real, add a test that flips `signing_verified=True` against the actual `4326` constant and asserts a signed-dry-run result; today there is no test that exercises the real mainnet chain ID end-to-end with `signing_verified=True`.

## Recommended pre-activation checklist

1. **Sanity-check killswitch behavior live**. Drop `~/.sapphire/hyperliquid_trading_pause`, run `echo '{"action":"live-status"}' | python3 plugins/claw-sapphire/tools/hyperliquid.py`, confirm the inspector reports `killswitch_active: true`. Remove the file when done.
2. **Re-run the EIP-712 verifier** (`python3 scripts/ops/verify_hyperliquid_signing.py --testnet-order`) and confirm a clean testnet round-trip. The `signing_verified` flip is justified ONLY when this script reports a successful testnet trade — that is the gate spec from the docstring (`risk.py:13-17`).
3. **Confirm `HYPERLIQUID_TRADING_ENABLED` is unset** (or `=0`) in the LaunchAgent plist for the Hyperliquid bot. The `signing_verified=True` flip alone does not enable trading — it only unlocks the mainnet code path. The trading gate is still the env flag, which the operator should flip independently and last.
4. **Verify `~/.sapphire/secrets.env` has `HYPERLIQUID_PRIVATE_KEY` (or the macOS keychain has `sapphire-hyperliquid` in service `sapphire`)** and confirm the resolved address matches the funded testnet wallet — `python3 -c "from hyperliquid_bot.risk import load_private_key, HyperliquidLivePolicy; from eth_account import Account; print(Account.from_key(load_private_key(HyperliquidLivePolicy())).address)"`.
5. **Land a follow-up PR adding the chain-anchor killswitch** for `lib/chain/robinhood_chain.py` and `lib/og/chain.py` (Soft Gap #3) before broadening Wave C beyond the operator-only path — these are the only other broadcast paths in the repo and should share the same emergency-stop semantic.
6. **For MegaETH specifically**: the `signing_verified=True` flip is safe to perform when needed, because the scaffold has no broadcast call. Pair the flip with the addition of an explicit broadcast helper in a separate PR so that the diff that introduces real mainnet writes is reviewable by itself.
7. **Document the flip** in `docs/security/credential-rotation-runbook.md` (or a new `docs/security/wave-c-activation-log.md`) including: timestamp, executor, the exact commit SHA where `signing_verified=True` was set, the operator who flipped it, and the testnet verification artifact (output of step 2 above).

---
*This report was produced under read-only constraints. No source files in `lib/trading/`, `plugins/claw-sapphire/tools/internal/`, `services/hyperliquid/`, or `services/megaeth-ingest/` were modified. No code was executed except `git`-side commands.*
