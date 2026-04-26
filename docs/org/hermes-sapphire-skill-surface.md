# Hermes Sapphire Skill Surface

Verified on 2026-04-26 from `/Users/aribs/.hermes/skills/sapphire`. This is a
read-only Wave 3 audit. It did not edit Hermes skills, restart the gateway, send
Telegram messages, call THO admin endpoints, mutate TradingView, or read secret
files.

The machine-readable inventory is `infra/hermes-sapphire-skills.yaml`.

## Summary

| Class | Skills |
|---|---|
| `read_only` | `cyber-intel`, `macro-data`, `regional-intel`, `repo-discovery`, `system-health`, `threat-intel`, `trading-analysis`, `trading-brain`, `trading-signals` |
| `local_mutating` | `inference-tier`, `paper-trading`, `system-ops` |
| `external_mutating` | `kimi-delegate`, `tradingview` |
| `production_adjacent` | `tho-operations` |

The largest consolidation risk is not file count; it is command blast radius.
Several skills are safe read paths, but a few can restart services, mutate local
paper-trading state, post local signals, send Telegram notifications, or access
customer/admin surfaces.

## Highest-Priority Splits

1. **TradingView skill**: split read-only chart/query operations from alert
   mutation, signal posting, screenshot notification, and LaunchAgent restart
   commands. Keep mutations confirmation-gated and dry-run-first.
2. **System ops / inference tier**: split status/model/log/metric reads from
   `launchctl kickstart` paths. Restart commands should require confirmation.
3. **THO operations**: replace the embedded credential-like verification payload
   with Secret Manager or local secret-file indirection before any further
   automation. Do not quote or copy the literal.
4. **Paper trading / trading brain**: keep paper-only; add or reuse audit-log
   hooks before any decision path can trigger action.

## Consolidation Guidance

- Preserve read-only skills as user-facing Hermes affordances until a Sapphire
  plugin or PM bot command covers the same ergonomics.
- Move mutating command bodies behind Sapphire-owned tools with tests, audit
  logs, confirmation firewall checks, and dry-run defaults.
- Treat `tradingview`, `system-ops`, `inference-tier`, `paper-trading`, and
  `tho-operations` as production-adjacent even when the underlying endpoint is
  local.
- Do not delete or rewrite live Hermes skills until an equivalent Sapphire-owned
  route has soaked and the rollback path is explicit.

## Next PR Candidates

- Add a Sapphire-owned read-only status wrapper for Hermes skill inventory so
  `/sapphire status` can show skill blast-radius classes.
- Create a safe THO operations skill template that reads its verification
  payload from a secret pointer instead of inline text.
- Split the TradingView skill into `tradingview-read` and `tradingview-control`
  templates, with control commands requiring confirmation.
