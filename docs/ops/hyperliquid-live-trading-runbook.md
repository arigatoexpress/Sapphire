# Hyperliquid Live Trading Runbook

Activating the Hyperliquid live-trading executor from cold install to first live $5 order.

The executor is **fail-closed by default**. It will not place a live order unless every gate is open: keychain key present, signing verification passed, `signing_verified=True` in code, `HYPERLIQUID_TRADING_ENABLED=1`, no killswitch file, daily-loss cap clear, position cap clear. Each section below opens one gate.

Implementation:
- [risk.py](services/hyperliquid/src/hyperliquid_bot/risk.py) — `HyperliquidLivePolicy` (caps + `signing_verified` flag)
- [signing.py](services/hyperliquid/src/hyperliquid_bot/signing.py) — EIP-712 L1 signing
- [signal_subscriber.py](services/hyperliquid/src/hyperliquid_bot/signal_subscriber.py) — tails `data/trading_signals.jsonl`

Hard caps (defined in [risk.py](services/hyperliquid/src/hyperliquid_bot/risk.py)):
- `$5` max notional per order
- `3x` max leverage
- `5` max open positions
- `$25` daily realized-loss → auto-pause for the rest of the UTC day

---

## 1. Prerequisites

- **Hyperliquid wallet.** Create a dedicated trading sub-account (do not reuse a personal wallet). Hyperliquid sub-accounts isolate balances and key exposure — if a key leaks, only the sub-account is at risk.
- **Testnet HYPE balance.** You need a small amount of testnet HYPE to pay fees during signing verification mode 3 and the first testnet order. Faucet: `https://app.hyperliquid-testnet.xyz/drip`.
- **Mainnet USDC deposit.** For mainnet activation only. Deposit a small float (the executor's per-order cap is $5, so $25–$50 is enough for the first soak).
- **Optional: Telegram bot token.** Set `HERMES_TELEGRAM_BOT_TOKEN` to receive trade alerts. Not required.

---

## 2. Key Storage

Store the wallet private key in macOS keychain. The `HYPERLIQUID_PRIVATE_KEY` environment variable is a dev-fallback only — production must use keychain so the key never sits in shell history, dotfiles, or process env.

Add the key:

```bash
security add-generic-password -a sapphire-hyperliquid -s sapphire -w
```

The `-w` with no value triggers an interactive prompt — paste the key, hit return. Nothing is echoed and nothing is logged.

Verify the entry exists without printing the key:

```bash
security find-generic-password -a sapphire-hyperliquid -s sapphire
```

This returns metadata only (account, service, creation date). If the key is missing you'll see `SecKeychainSearchCopyNext: The specified item could not be found in the keychain.` — re-run the `add-generic-password` command above.

To rotate or remove the key:

```bash
security delete-generic-password -a sapphire-hyperliquid -s sapphire
```

Then re-add via `add-generic-password`.

---

## 3. Signing Verification

[verify_hyperliquid_signing.py](scripts/ops/verify_hyperliquid_signing.py) has three escalating modes. Run them in order. Each must pass before flipping `signing_verified=True`.

### Mode 1: local sign + recover (no network)

```bash
python3 scripts/ops/verify_hyperliquid_signing.py
```

Constructs a phantom-agent message, runs the canonical msgpack → keccak → EIP-712 typed-data sign pipeline, then `ecrecover`s the signature and asserts the recovered address matches the wallet address derived from the keychain key. No network calls, no fees, no Hyperliquid API touched.

Expected output ends with `signing OK (local recover)`. If you see `recovered address mismatch`, the signing path is broken — do not proceed.

### Mode 2: local sign + testnet `/info` probe

```bash
python3 scripts/ops/verify_hyperliquid_signing.py --info
```

Mode 1 plus a read-only `clearinghouseState` query against the Hyperliquid testnet `/info` endpoint. This proves the wallet address is recognized by Hyperliquid and that the API is reachable. Still no fees, no order side effects.

Expected output ends with `signing OK (local recover) + info probe OK`. If `/info` returns `account not found`, fund the testnet account first via the faucet.

### Mode 3: full testnet round-trip

```bash
python3 scripts/ops/verify_hyperliquid_signing.py --testnet-order
```

Mode 2 plus a real signed order: places a far-from-market limit order on testnet, asserts the response carries an order ID, then immediately cancels it. **Requires testnet HYPE for fees** — fund via the faucet first.

Expected output ends with `signing OK (full round-trip)`. Common failures:
- `insufficient margin` → testnet balance too low; faucet again.
- `nonce too low` → another process used the same key recently; wait 30s and retry.
- `signature mismatch` → bug in the signing path; do not proceed, report to engineering.

---

## 4. Flipping the Gate

Once all three verification modes pass, edit [risk.py](services/hyperliquid/src/hyperliquid_bot/risk.py) and set `signing_verified=True` on the `HyperliquidLivePolicy` default. This is intentionally a code-level flip rather than an env var — it shows up in `git blame`, requires a PR, and forces a reviewer to read the verification log before approving.

The diff is one line, e.g.:

```diff
-    signing_verified: bool = False
+    signing_verified: bool = True
```

Open a PR titled something like `hyperliquid: enable signing_verified after testnet round-trip`. In the PR body, paste the output of all three verification modes (mode 3 truncated to confirm the order ID and cancel ack). Land the PR before continuing.

If `signing_verified` is `False` and you set `HYPERLIQUID_TESTNET=false`, the executor will refuse mainnet with `refusing to run on mainnet — signing not yet verified`.

---

## 5. Dry-Run Smoke Test

Before any live order, confirm the bot tails the signal file, evaluates risk, and writes a dry-run audit entry without hitting Hyperliquid.

Defaults are already safe:
- `HYPERLIQUID_TRADING_ENABLED=0` (dry-run)
- `HYPERLIQUID_TESTNET=true`

Start the bot:

```bash
cd ~/Code/Sapphire
python3 -m hyperliquid_bot
```

In a second terminal, append a test signal:

```bash
echo '{"symbol":"BTC","action":"buy","signal_id":"smoke-1","price":50000}' >> data/trading_signals.jsonl
```

Watch the bot log. You should see:

```
signal smoke-1 received
verdict: blocked: trading_disabled_env_flag
```

Confirm the dry-run entry was written:

```bash
tail -n 1 data/hyperliquid_trades.jsonl
```

Expected: a JSON line with `"verdict": "blocked"`, `"reason": "trading_disabled_env_flag"`, `"dry_run": true`. The `response` field will be `null` since no order was submitted.

Stop the bot (`Ctrl-C`). Reset the signal offset before re-running so the next session re-reads the test signal:

```bash
rm data/hyperliquid_signal_offset.json
```

If you skip the offset reset, the bot picks up where it left off and the next test signal won't reprocess.

---

## 6. First Live Testnet Order

Now flip the trading gate while staying on testnet. Real signing, real Hyperliquid testnet endpoint, no real money.

```bash
export HYPERLIQUID_TRADING_ENABLED=1
export HYPERLIQUID_TESTNET=true
python3 -m hyperliquid_bot
```

Append a signal in the second terminal:

```bash
echo '{"symbol":"BTC","action":"buy","signal_id":"testnet-1","price":50000}' >> data/trading_signals.jsonl
```

Watch the bot log. You should see:

```
signal testnet-1 received
verdict: executed
order_id: 0x...
```

Confirm via the read-only inspector:

```bash
echo '{"action":"live-status"}' | python3 plugins/claw-sapphire/tools/hyperliquid.py
```

Output includes `trading_enabled: true`, `testnet: true`, today's PnL, and the last 5 trades. The testnet-1 entry should appear at the top of `recent_trades`.

Cross-check on Hyperliquid testnet UI (`https://app.hyperliquid-testnet.xyz`) — your order should be visible in open orders or fills depending on whether it filled.

Let it run for at least 24 hours on testnet before mainnet activation. Watch for unexpected verdicts, signed-payload errors, or daily-loss-cap trips.

---

## 7. Mainnet Activation

After a clean 24-hour testnet soak, flip to mainnet:

```bash
export HYPERLIQUID_TRADING_ENABLED=1
export HYPERLIQUID_TESTNET=false
python3 -m hyperliquid_bot
```

**The executor uses real funds at this point.** Every signal that passes risk evaluation will place a real order against your mainnet wallet, capped at $5 notional per order.

Recommended first-day posture:
- Stay at the desk for the first hour.
- Cap signal volume by leaving only one or two TradingView alerts active.
- Check `data/hyperliquid_trades.jsonl` every 15 minutes for the first three orders.
- Confirm fills on the Hyperliquid mainnet UI side-by-side with the audit log.
- After three clean fills, you can leave it unattended.

If anything looks wrong, drop the killswitch immediately (next section).

---

## 8. Killswitch Usage

The killswitch is a single file. The signal subscriber checks for it before every order.

Halt all new orders:

```bash
touch ~/.sapphire/hyperliquid_trading_pause
```

Resume:

```bash
rm ~/.sapphire/hyperliquid_trading_pause
```

While the file exists, every signal logs `verdict: blocked, reason: killswitch_active` and is recorded as a dry-run in `data/hyperliquid_trades.jsonl`.

**The killswitch does NOT close existing positions.** It blocks new orders only. If you need to close out:

1. Drop the killswitch (above) so no new orders can race in.
2. Cancel open orders manually via `client.cancel_order` from a python REPL (see Rollback section).
3. Close positions via `client.close_position`.

The killswitch is the right tool for "stop the bleeding." It is not the right tool for "I'm done for the night" — for that, just stop the bot process.

---

## 9. Daily Checks

Three things to look at every morning:

### Realized-loss tally

```bash
cat data/hyperliquid_daily_pnl.json
```

Format: `{"YYYY-MM-DD": <realized_pnl_usd>, ...}`. The executor reads today's UTC date and auto-pauses if `abs(pnl) >= 25` and `pnl < 0`. If you see today at `-24.50`, the next $0.50+ loss trips the cap.

### Recent activity

```bash
tail -n 20 data/hyperliquid_trades.jsonl
```

Each line is one order verdict. Look for unexpected `blocked` reasons, repeat `error` lines from the same signal_id (suggests the signal subscriber is replaying), or notional values above $5 (should be impossible — would indicate a risk-cap regression).

### Executor health

```bash
echo '{"action":"live-status"}' | python3 plugins/claw-sapphire/tools/hyperliquid.py
```

Returns:
- `trading_enabled` — should be `true` during live hours
- `killswitch_active` — should be `false`
- `today_pnl_usd` — cross-check vs `hyperliquid_daily_pnl.json`
- `recent_trades` — last 5 entries, mirror of the `tail` above
- `open_positions_count` — under 5; if at 5, no new positions until one closes

If any field is unexpected, investigate before letting the bot continue.

---

## 10. Rollback

If something goes wrong, follow this sequence in order. Each step is more aggressive than the last — stop at the first one that resolves the issue.

### Step 1: drop the killswitch

```bash
touch ~/.sapphire/hyperliquid_trading_pause
```

This stops new orders within the next signal-poll cycle (sub-second). Existing positions and open orders are untouched. Most "something looks weird" situations end here.

### Step 2: cancel open orders manually

Open a python REPL with the bot's environment:

```bash
cd ~/Code/Sapphire
python3
```

```python
from hyperliquid_bot.client import HyperliquidClient
client = HyperliquidClient.from_keychain(testnet=False)
open_orders = client.list_open_orders()
for order in open_orders:
    client.cancel_order(order["coin"], order["oid"])
    print(f"cancelled {order['coin']} {order['oid']}")
```

Confirm zero open orders on the Hyperliquid UI before continuing.

### Step 3: close positions

Same REPL:

```python
positions = client.list_positions()
for pos in positions:
    client.close_position(pos["coin"])
    print(f"closed {pos['coin']}")
```

This places market orders against open positions. They will fill at whatever the book offers — slippage applies. After closing, confirm zero positions on the UI.

### Step 4: unset the env flag

```bash
unset HYPERLIQUID_TRADING_ENABLED
```

Or in the shell that started the bot, set it to `0`. The bot reads this on next signal evaluation and will start logging `blocked: trading_disabled_env_flag` regardless of the killswitch state. Belt-and-suspenders for the cases where you want the killswitch file removed but trading still off.

After rollback, do a post-mortem on `data/hyperliquid_trades.jsonl` and `data/hyperliquid_daily_pnl.json` before re-enabling. Don't flip the gate back on until you understand what tripped it.

---

## 11. Common Errors

| Error | Cause | Fix |
|---|---|---|
| `no Hyperliquid private key found` | Keychain entry missing or accessible only to a different user. | Re-run `security add-generic-password -a sapphire-hyperliquid -s sapphire -w`. Verify with `security find-generic-password -a sapphire-hyperliquid -s sapphire`. |
| `refusing to run on mainnet — signing not yet verified` | `HyperliquidLivePolicy.signing_verified` is still `False` while `HYPERLIQUID_TESTNET=false`. | Run all three modes of [verify_hyperliquid_signing.py](scripts/ops/verify_hyperliquid_signing.py), then flip `signing_verified=True` in [risk.py](services/hyperliquid/src/hyperliquid_bot/risk.py) via PR. |
| `max_open_positions_reached` | Already holding 5 open positions — the cap defined in [risk.py](services/hyperliquid/src/hyperliquid_bot/risk.py). | Close at least one position via `client.close_position` (see Rollback step 3) before new entries can take. |
| `daily_loss_cap_reached` | Today's realized loss in `data/hyperliquid_daily_pnl.json` is at or below `-25`. Auto-paused for the rest of the UTC day. | Wait until next UTC midnight — the tally resets per-date. Investigate the losing trades in `data/hyperliquid_trades.jsonl` before the next session. |
| `order_notional_exceeds_cap` | Computed order size > $5. Should be impossible — risk policy clamps before submission. | This is a regression. Drop the killswitch, file a bug, do not bypass the cap. |
| `signature mismatch` from Hyperliquid | Domain or msgpack encoding drift in [signing.py](services/hyperliquid/src/hyperliquid_bot/signing.py). | Drop the killswitch. Re-run mode 1 of the verify script — if that fails, the signing path is broken. Do not bypass; file a bug. |
| `nonce too low` | Two processes signing with the same key concurrently. | Kill any orphan `python3 -m hyperliquid_bot` processes (`pkill -f hyperliquid_bot`), wait 30 seconds for nonces to settle, restart cleanly. |
| `trading_disabled_env_flag` (verdict, not error) | `HYPERLIQUID_TRADING_ENABLED` is unset or `0`. Working as designed — dry-run mode. | Set `HYPERLIQUID_TRADING_ENABLED=1` to go live, or leave as-is for dry-run. |
| `killswitch_active` (verdict, not error) | `~/.sapphire/hyperliquid_trading_pause` exists. Working as designed. | `rm ~/.sapphire/hyperliquid_trading_pause` to resume. |

---

## Appendix: file map

- [risk.py](services/hyperliquid/src/hyperliquid_bot/risk.py) — `HyperliquidLivePolicy` caps and `signing_verified` flag
- [signing.py](services/hyperliquid/src/hyperliquid_bot/signing.py) — EIP-712 L1 signing (`Exchange/1/1337/0x0…0` domain, `a`/`b` source for mainnet/testnet)
- [signal_subscriber.py](services/hyperliquid/src/hyperliquid_bot/signal_subscriber.py) — tails `data/trading_signals.jsonl`
- [signal_logger.py](services/alpha/src/signal_logger.py) — upstream writer (TradingView webhooks → `data/trading_signals.jsonl`)
- [verify_hyperliquid_signing.py](scripts/ops/verify_hyperliquid_signing.py) — three-mode verifier
- `plugins/claw-sapphire/tools/hyperliquid.py` — `live-status` inspector
- `data/trading_signals.jsonl` — input signal stream
- `data/hyperliquid_trades.jsonl` — per-order audit (verdict + response)
- `data/hyperliquid_daily_pnl.json` — daily realized-loss tally (auto-pause source of truth)
- `data/hyperliquid_signal_offset.json` — subscriber's read offset (delete to re-read)
- `~/.sapphire/hyperliquid_trading_pause` — killswitch file (presence = paused)
