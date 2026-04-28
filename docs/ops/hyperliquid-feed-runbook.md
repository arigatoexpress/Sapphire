# Hyperliquid Public Feed Runbook

## Default Posture

The Hyperliquid public-feed daemon is disabled by default. It is a signal-only
reader for public market data and has no order submission path.

Live gate:

```bash
SAPPHIRE_HYPERLIQUID_LIVE=1
```

Setting this flag only permits the daemon to open `wss://api.hyperliquid.xyz/ws`
and subscribe to public feeds. It does not enable authenticated endpoints,
wallet keys, or trade execution.

## Status and Dry-Run Checks

```bash
echo '{"action":"status"}' | /usr/local/bin/python3 plugins/claw-sapphire/tools/hyperliquid.py
echo '{"action":"subscribe-test"}' | /usr/local/bin/python3 plugins/claw-sapphire/tools/hyperliquid.py
echo '{"action":"latest","limit":10}' | /usr/local/bin/python3 plugins/claw-sapphire/tools/hyperliquid.py
```

`subscribe-test` returns the exact subscription payloads without network I/O.

## Symbol Config

Default symbols: `BTC`, `ETH`, `SOL`

Override file:

```yaml
symbols:
  - BTC
  - ETH
  - SOL
```

Path: `~/.sapphire/hyperliquid_symbols.yaml`

The daemon caps configured symbols at `8` and ignores invalid ticker strings.

## Event Topics

| Topic | Rule |
| --- | --- |
| `hyperliquid.trade` | Public trade notional greater than `$250k` |
| `hyperliquid.imbalance` | BBO notional imbalance greater than `3:1` sustained for more than `10s` |
| `hyperliquid.book.thin` | Top-10 depth down more than `30%` within `60s` |

Signals are appended to `~/.sapphire/hyperliquid_signals.jsonl` for the
`latest` tool action and published to the Sapphire event bus when available.

## LaunchAgent Template

Template path:

```bash
services/hyperliquid/launchagent/com.sapphire.hyperliquid-public-feed.plist.template
```

The checked-in template sets `SAPPHIRE_HYPERLIQUID_LIVE=0`. To install later,
copy it without the `.template` suffix, review the environment, set the live
gate intentionally, then bootstrap it with launchd. Do not load it from an
agent script.

## Routine Pause

This branch did not include `lib/core/routine_pause`. The daemon therefore
ships a local fallback that pauses when any of these files exist:

- `~/.sapphire/routine_pause/hyperliquid-public-feed`
- `~/.sapphire/routine_pause/hyperliquid-public-feed.pause`
- `~/.sapphire/routine_pause/hyperliquid`
- `~/.sapphire/routine_pause/all`

The code automatically prefers `lib.core.routine_pause` if that module is
present after rebasing. Rebase this lane after Lane 2 lands so the shared pause
helper becomes the active source.

## Rollback

Revert the PR or remove the LaunchAgent copy if installed. No external state is
mutated beyond the local JSONL signal ledger and event-bus fallback file.
