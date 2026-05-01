# MegaETH Operator Runbook

Day-to-day operation of the MegaETH ingest, plugin tool, and (gated) executor. For background and architecture, see [`docs/integrations/megaeth.md`](../integrations/megaeth.md).

The integration is **fail-closed**. The executor will not broadcast a mainnet transaction unless every gate in the [activation section of the integrations doc](../integrations/megaeth.md#activation-gates-for-trading) is open. This runbook covers operating the ingest path and the read-only plugin tool; live-trading activation has its own gate sequence.

---

## 1. Pre-flight

Run before starting the ingest service for the first time, or after a config change.

### Environment variables set

```bash
echo "${SAPPHIRE_MEGAETH_RPC:?missing}"      # https://...
echo "${SAPPHIRE_MEGAETH_WSS:?missing}"      # wss://...
echo "${SAPPHIRE_MEGAETH_DRY_RUN:-1}"        # default 1 = simulate
```

If `SAPPHIRE_MEGAETH_RPC` or `SAPPHIRE_MEGAETH_WSS` is unset, the ingest service exits at startup with a clear message. Find current testnet URLs on https://docs.megaeth.com (see the integrations doc).

### Killswitches default state

```bash
ls ~/.sapphire/megaeth_ingest_pause 2>/dev/null   # expected: not present
ls ~/.sapphire/megaeth_trading_pause 2>/dev/null  # expected: present (until mainnet activation)
```

Default posture: ingest unpaused, trading paused. The trading killswitch ships present and is only removed once all five activation gates are open.

### Tests passing

```bash
pytest tests/unit/ -k megaeth --tb=short -q          # unit tests, no network
SAPPHIRE_MEGAETH_INTEGRATION=1 \
SAPPHIRE_MEGAETH_RPC=$SAPPHIRE_MEGAETH_RPC \
  pytest tests/integration/megaeth/ --tb=short -q     # network smoke
```

The integration suite skips entirely when `SAPPHIRE_MEGAETH_INTEGRATION` is unset, so it is safe to leave in CI without configuring endpoints.

---

## 2. Day-to-day

### Check ingest health

```bash
curl -s http://localhost:8788/health | jq
```

Expected fields: `status` (`ok` or `degraded`), `wss_connected`, `last_block_seen`, `signals_emitted_last_5m`, `paused` (true if killswitch present).

### Query the plugin tool (read-only)

```bash
echo '{"action":"chain-id"}' | python3 plugins/claw-sapphire/tools/megaeth.py
echo '{"action":"latest-block"}' | python3 plugins/claw-sapphire/tools/megaeth.py
echo '{"action":"balance","address":"0x..."}' | python3 plugins/claw-sapphire/tools/megaeth.py
```

These actions hit `SAPPHIRE_MEGAETH_RPC` only. They do not need the WSS endpoint and do not touch the executor.

### Read logs

```bash
# Ingest service log (LaunchAgent)
tail -f ~/Library/Logs/sapphire/megaeth-ingest.log

# Per-signal audit
tail -f data/megaeth_signals.jsonl

# Executor would-be / live trades (when gated path runs)
tail -f data/megaeth_trades.jsonl
```

The audit JSONL is append-only. Each line includes `signal_id`, `block_number`, `verdict`, and `dry_run`.

---

## 3. Incident playbook

### WS disconnects (intermittent)

**Symptoms.** Ingest log lines `wss closed code=1006 reconnect_in=2s`; `/health` shows `wss_connected: false` for short windows.

**Action.** The ingest service auto-reconnects with exponential backoff (1s → 2s → 4s → ... capped at 30s). Tolerate up to ~3 minutes of intermittent disconnects. If `wss_connected` stays false for >3 minutes:

1. `curl -s http://localhost:8788/health | jq .last_error` — check the recorded error.
2. Verify `SAPPHIRE_MEGAETH_WSS` is reachable: `wscat -c "$SAPPHIRE_MEGAETH_WSS"` (install with `npm i -g wscat`).
3. If the URL is reachable but the service can't connect, restart the LaunchAgent: `launchctl kickstart -k gui/$(id -u)/com.sapphire.megaeth-ingest`.
4. If the URL is unreachable, the testnet endpoint may have rotated — re-check https://docs.megaeth.com and update the env var.

### Signal-logger backpressure

**Symptoms.** Ingest `/health` shows `signals_emitted_last_5m` healthy but `data/trading_signals.jsonl` not advancing; signal-logger:18081 returning 5xx or hanging.

**Action.**

1. `curl -s http://localhost:18081/health` — check signal-logger.
2. If signal-logger is down: pause ingest first (`touch ~/.sapphire/megaeth_ingest_pause`), bring signal-logger back up, then clear ingest pause. This avoids a thundering-herd retry burst.
3. If signal-logger is up but slow: ingest emits with a 2-second timeout and drops on timeout (logged as `dropped_signal: backpressure`). Acceptable for short windows; investigate signal-logger if sustained >1 minute.

### MegaETH sequencer outage

**Symptoms.** All RPC calls returning 502/503; WSS connecting but no `newHeads` events; status post on https://x.com/megaeth_labs or https://docs.megaeth.com.

**Action.** This is upstream — Sapphire cannot fix it. Posture:

1. Confirm via the MegaETH status channel before assuming outage (the docs site is authoritative).
2. `touch ~/.sapphire/megaeth_ingest_pause` — stops retry storms and silences `/health` warning logs.
3. Wait for upstream resolution. Do **not** fail over to a different chain — Sapphire's MegaETH executor is chain-id-pinned; signing for a different chain would be a regression.
4. When upstream resolves: `rm ~/.sapphire/megaeth_ingest_pause`, then re-check `/health`.

### Suspected mainnet drift

**Symptoms.** Executor logs `chain_id mismatch: expected <X>, got <Y>` after an env-var change, or operators see unexpected mainnet behavior.

**Action.** Stop everything. The executor refuses to broadcast on chain-id mismatch, but the safer move is to confirm config before re-enabling:

1. `touch ~/.sapphire/megaeth_trading_pause` (idempotent — also helpful to prove the killswitch works).
2. Confirm the chain_id constant in `lib/chain/megaeth.py` matches the value MegaETH publishes for the network you mean to be on.
3. Confirm `SAPPHIRE_MEGAETH_RPC` resolves to that same network (check via `curl ... eth_chainId`).
4. If the constant or env was changed in error, revert via PR before clearing the killswitch. Do not edit live state to "make it match" — the constant is the source of truth.

---

## 4. Rotation: testnet wallet key

To rotate the dev-fallback testnet wallet key:

```bash
# 1. Generate a new keypair offline (or via cast wallet new — pick your tool).
# 2. Fund the new address from the testnet faucet (per docs.megaeth.com).
# 3. Replace the keychain entry:
security delete-generic-password -a sapphire-megaeth -s sapphire 2>/dev/null
security add-generic-password   -a sapphire-megaeth -s sapphire -w
# Paste the new private key when prompted (-w with no value triggers interactive input; nothing echoes).
# 4. Verify metadata:
security find-generic-password -a sapphire-megaeth -s sapphire
# 5. Restart the executor LaunchAgent (when active):
launchctl kickstart -k gui/$(id -u)/com.sapphire.megaeth-executor 2>/dev/null || true
```

Do not put the new key in `~/.zshrc`, `.env`, or commit history. The `SAPPHIRE_MEGAETH_TESTNET_KEY` env var is dev-fallback only.

After rotation, re-run the testnet rehearsal step from the activation flow before re-broadcasting any signed transactions, so the new key is exercised end-to-end.

---

## 5. Decommission

If MegaETH integration is being retired entirely:

```bash
# 1. Stop and unload the LaunchAgents.
launchctl bootout gui/$(id -u)/com.sapphire.megaeth-ingest    2>/dev/null || true
launchctl bootout gui/$(id -u)/com.sapphire.megaeth-executor  2>/dev/null || true

# 2. Remove the plist files (template path under services/megaeth-ingest/launchagent/).
rm ~/Library/LaunchAgents/com.sapphire.megaeth-ingest.plist     2>/dev/null || true
rm ~/Library/LaunchAgents/com.sapphire.megaeth-executor.plist   2>/dev/null || true

# 3. Drop the keychain entry.
security delete-generic-password -a sapphire-megaeth -s sapphire 2>/dev/null || true

# 4. Delete the integration branch (after merging the decommission PR).
git push origin --delete feat/megaeth-integration                2>/dev/null || true

# 5. Optional: archive the audit logs (don't delete — kept for compliance).
mv data/megaeth_signals.jsonl data/megaeth_signals.$(date +%Y%m%d).archive.jsonl 2>/dev/null || true
mv data/megaeth_trades.jsonl  data/megaeth_trades.$(date +%Y%m%d).archive.jsonl  2>/dev/null || true
```

The decommission PR should remove `services/megaeth-ingest/`, `plugins/claw-sapphire/tools/megaeth.py`, `plugins/claw-sapphire/tools/internal/megaeth_executor.py`, `lib/chain/megaeth.py`, the docs, and the integration test directory in one go. Do not partial-decommission — leaving the executor while removing the ingest is worse than leaving everything in place.
