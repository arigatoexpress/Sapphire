# Counterparty Intel Runbook

**Service:** `services/counterparty/run.py`  
**Tool:** `plugins/claw-sapphire/tools/internal/counterparty_intel.py`  
**Default mode:** dry-run, public-data-only, read-only.

## Quick Status

```bash
echo '{"action":"status"}' \
  | /usr/local/bin/python3 plugins/claw-sapphire/tools/internal/counterparty_intel.py
```

Expected dry-run posture:

```json
{
  "live_enabled": false,
  "public_data_only": true,
  "max_refresh_per_hour": 12
}
```

If `live_enabled` is false, no Hyperliquid network call is made. This is
the default and the expected behavior in CI.

## Leaderboard

Dry-run leaderboard:

```bash
echo '{"action":"leaderboard","top_n":5}' \
  | /usr/local/bin/python3 plugins/claw-sapphire/tools/internal/counterparty_intel.py
```

Live leaderboard, operator only:

```bash
SAPPHIRE_HYPERLIQUID_LIVE=1 \
  echo '{"action":"leaderboard","top_n":10}' \
  | /usr/local/bin/python3 plugins/claw-sapphire/tools/internal/counterparty_intel.py
```

The live path uses Hyperliquid public info endpoints only. It does not load
wallet keys or call authenticated exchange endpoints.

## Position Changes

Pass previous and current snapshots:

```bash
echo '{
  "action": "position-changes",
  "previous": [
    {"trader":"0x1","asset":"BTC","side":"long","size_usd":100000}
  ],
  "current": [
    {"trader":"0x1","asset":"BTC","side":"long","size_usd":130000}
  ]
}' | /usr/local/bin/python3 plugins/claw-sapphire/tools/internal/counterparty_intel.py
```

The default threshold is 15 percent. A new position, a closed position,
or a long-to-short flip will all generate a material change when they
exceed the threshold.

## Smart-Money Consensus

Aggregate changes into correlator-ready signals:

```bash
echo '{
  "action": "smart-money-consensus",
  "position_changes": [
    {
      "trader":"0x1",
      "asset":"BTC",
      "old_side":"long",
      "new_side":"long",
      "old_size_usd":100000,
      "new_size_usd":150000,
      "change_pct":50,
      "side":"long",
      "detected_at":"2026-04-28T00:00:00+00:00"
    }
  ]
}' | /usr/local/bin/python3 plugins/claw-sapphire/tools/internal/counterparty_intel.py
```

The signal output includes `traders_corroborating`, `magnitude`, and
`smart_money_consensus`. These fields are context features for the
correlator and narrative engine. They are not execution instructions.

## One-Shot Service

```bash
/usr/local/bin/python3 services/counterparty/run.py run-once
```

This writes:

```text
data/counterparty/<date>/counterparty_signals.json
data/counterparty/<date>/counterparty_signals.json.envelope.json
```

Use `--publish` only after the integration pass has tests for the event
topic:

```bash
/usr/local/bin/python3 services/counterparty/run.py run-once --publish
```

The published event topic is `counterparty.smart_money.move`.

## Caps

- Maximum tracked traders: 100
- Maximum live refreshes per hour: 12
- Minimum 30-day PnL for watchlist eligibility: 50,000 USD
- Material position-change threshold: 15 percent

Counters are stored in `~/.cache/sapphire/counterparty_intel/counters.json`.
Delete that file only if you are intentionally resetting the local rate
window during development.

## Verification

Focused tests:

```bash
/usr/local/bin/python3 -m pytest \
  tests/unit/test_counterparty_tracker.py \
  tests/unit/test_counterparty_sources.py \
  tests/unit/test_counterparty_signal_generator.py \
  plugins/claw-sapphire/tests/test_counterparty_intel.py \
  -q --tb=short
```

Run plugin and unit suites separately in full verification:

```bash
ruff check .
/usr/local/bin/python3 -m pytest tests/unit/ -q --tb=short
/usr/local/bin/python3 -m pytest plugins/claw-sapphire/tests/ -q --tb=short
/usr/local/bin/python3 scripts/validate_tool_registry.py
/usr/local/bin/python3 scripts/ops/production_readiness_sweep.py --no-external | tail -5
```

## Failure Modes

If live calls return empty data, first confirm `SAPPHIRE_HYPERLIQUID_LIVE=1`
is set and the public endpoint is reachable. Do not add authenticated
fallbacks. Empty public data should degrade to no signals.

If smart-money consensus looks too strong, inspect the underlying trader
count. A single trader can generate a signal for development and testing,
but production dashboards should visually distinguish one-trader moves
from multi-trader consensus.

If the same trader appears to move across many assets at once, treat that
as an adversarial-defense input. It may be legitimate portfolio rotation,
but it may also be a public leaderboard bait pattern.

## Rollback

This lane is additive. Revert the PR, remove the registry entry, or stop
calling the service. There is no LaunchAgent installed by this PR and no
live state mutation outside optional local JSON snapshots.

## Pre-Publish Checklist

Before enabling `--publish`, run one dry-run service invocation and inspect
the output file:

```bash
/usr/local/bin/python3 services/counterparty/run.py run-once
jq '.signals' data/counterparty/$(date -u +%F)/counterparty_signals.json
```

Confirm three things. First, `mode` should be `dry-run` unless you intended
to opt into live public data. Second, every signal should have an asset,
side, trader count, and bounded consensus value. Third, the sibling
`.envelope.json` file should exist and pass the repo-wide provenance sweep.

For live public data, start with a single manual invocation and no
publishing:

```bash
SAPPHIRE_HYPERLIQUID_LIVE=1 \
  /usr/local/bin/python3 services/counterparty/run.py run-once
```

Only after the JSON looks sane should an operator use `--publish`. Even
then, publish only to the event bus; do not wire this directly into any
execution path.

## Privacy And Ethics

Use only public leaderboard and public position data. Do not try to
associate wallets with real-world identities. Do not enrich addresses
through doxxing databases. Sapphire’s job is to reason over public market
structure, not to unmask counterparties.
