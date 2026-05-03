# Market Intel Runbook

Last reviewed: 2026-04-30

## Triage Quickstart

Failure mode addressed: the daily brief reports a missing `market_intel`
section, or downstream signal-enhancement is operating on stale snapshots.

```bash
launchctl print gui/$(id -u)/com.sapphire.market-intel
```

```bash
stat -f '%Sm %N' data/intelligence/latest/market_intel.json
```

```bash
jq '{timestamp, errors}' data/intelligence/latest/market_intel.json
```

If the file is older than 45 minutes, the snapshot is stale by contract — check
launchd, then logs. If `errors` is non-empty, individual feeds failed but the
artifact may still be partially usable.

Live monitors: dashboard `/observability` market-intel freshness card.
On-call escalation: intel owner; p3 unless brief generation is blocked, then
p2.

This runbook covers `com.sapphire.market-intel`, the local LaunchAgent that
refreshes the market-intelligence snapshot consumed by daily briefs and signal
enhancement. It collects public data only and writes a local JSON artifact; it
does not send Telegram messages and does not submit trades.

## Ownership

| Item | Path |
|---|---|
| LaunchAgent | `infra/launchagents/com.sapphire.market-intel.plist` |
| Collector module | `lib/intel/market_intelligence.py` |
| Latest artifact | `data/intelligence/latest/market_intel.json` |
| Dated artifacts | `data/intelligence/YYYY-MM-DD/market_intel.json` |
| Stdout log | `/Users/aribs/Library/Logs/sapphire/market-intel.log` |
| Stderr log | `/Users/aribs/Library/Logs/sapphire/market-intel.err` |
| Pause flag | `/Users/aribs/.sapphire/routine_pause/market-intel` |

## Schedule

The plist runs at load and every 30 minutes:

```bash
/usr/local/bin/python3 -m lib.intel.market_intelligence
```

It sets `WorkingDirectory=/Users/aribs/Code/Sapphire` and
`PYTHONPATH=/Users/aribs/Code/Sapphire`.

## Data Flow

```text
launchd RunAtLoad + every 30 min
  -> python3 -m lib.intel.market_intelligence
  -> abort_if_paused("market-intel")
  -> collect public feeds
  -> write data/intelligence/latest/market_intel.json
  -> downstream archival/provenance jobs may copy dated artifacts
```

The five feed groups are stablecoin issuance, economic calendar, political RSS
scoring, liquidation bands, and order-flow funding velocity. Consumers treat the
latest snapshot as stale when it is older than 45 minutes.

## Normal Operation

Validate plist syntax and state:

```bash
plutil -lint infra/launchagents/com.sapphire.market-intel.plist
launchctl print gui/$(id -u)/com.sapphire.market-intel
```

Inspect the latest artifact without changing it:

```bash
jq '{timestamp, errors}' data/intelligence/latest/market_intel.json
stat -f '%Sm %N' data/intelligence/latest/market_intel.json
```

Inspect logs:

```bash
tail -n 100 /Users/aribs/Library/Logs/sapphire/market-intel.log
tail -n 100 /Users/aribs/Library/Logs/sapphire/market-intel.err
```

Run feed diagnostics without writing the canonical artifact:

```bash
/usr/local/bin/python3 -m lib.intel.market_intelligence --test
```

`--test` is read-only for repo artifacts, but it still makes live public-source
calls. Use it to separate network/source trouble from local parser regressions.

## Common Failures

### Stale Snapshot

If `market_intel.json` is older than 45 minutes, downstream consumers may treat
market intel as unavailable. Check launchd state, logs, and the pause flag
before manually collecting.

### Partial Feed Failures

The snapshot has an `errors` object. A partial failure is not automatically a
daemon failure if the other feeds saved. Hyperliquid liquidation/order-flow
paths can fall back to previous snapshot data.

### Network Or Source Breakage

Public sources can rate-limit, return invalid JSON/XML, or change schemas.
Capture the failing feed name and error text from `--test`; do not add secrets
or paid-provider calls as an emergency patch.

### Environment Drift

The plist assumes `/usr/local/bin/python3`, a working certificate bundle, and
repo-root `PYTHONPATH`. If tests pass in another interpreter but launchd fails,
reproduce with `/usr/local/bin/python3`.

### Paused Routine

`abort_if_paused("market-intel")` exits cleanly when the pause flag exists. Last
exit code 0 can mean skipped.

## Recovery

Use this order:

1. Confirm the plist is loaded and matches the repo.
2. Inspect stdout/stderr and `data/intelligence/latest/market_intel.json`.
3. Run `--test` if live public-source calls are acceptable.
4. If the parser is broken, add a fixture-backed regression test before changing
   feed logic.

Focused tests:

```bash
/usr/local/bin/python3 -m pytest \
  tests/unit/test_market_intelligence.py \
  tests/unit/test_lib_intel.py \
  tests/unit/test_routine_pause.py \
  tests/unit/test_launchagent_plists.py -q
```

## Safety Notes

- Do not run the module without `--test` unless writing the canonical artifact
  is intended.
- Do not delete `data/intelligence/latest/market_intel.json` during triage.
- Do not add API keys or private-source credentials to the plist.
- Do not convert market-intel feed output into trade approval.
- Do not unload, bootstrap, kickstart, or retarget the LaunchAgent during a
  documentation or audit pass.

## Escalation

Escalate when:

- The latest artifact is stale for more than two expected intervals.
- `errors` contains the same feed failure across multiple cycles.
- A source schema change causes malformed output in daily brief or signal
  enhancer consumers.
- The installed plist drifts from the repo plist.
- Fixing the issue would require changing feed contracts or adding credentials.

Include launchd state, latest artifact timestamp, `errors`, last 100 log lines,
`--test` output if run, and the exact consumer symptom.
