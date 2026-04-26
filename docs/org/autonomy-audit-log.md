# Autonomy Audit Log

Sapphire now has three local audit streams for autonomy safety:

- Confirmation firewall: `confirmation_firewall.jsonl`
- Kill switch: `kill_switch.jsonl`
- Autonomous decisions and market alerts: `autonomy.jsonl`

The autonomy audit log is append-only JSONL. By default it writes to
`~/.sapphire/audit/autonomy.jsonl`, or to `SAPPHIRE_AUTONOMY_AUDIT_LOG` when set.

## Current Event Types

- `autonomy.decision_evaluated`
- `autonomy.alert_detected`

## Schema

Every record includes:

- `event_type`
- `ts`
- `actor`
- `action`
- `outcome`
- optional `risk`
- optional `object_ref`
- optional sanitized `metadata`

Decision metadata intentionally records summaries only: signal id, symbol,
direction, original/adjusted confidence, rules fired, reason count, and
world-state keys. It does not write raw signals, prompts, request bodies,
secrets, order payloads, or full world snapshots.

## Safety Rules

- Treat the log as local operator evidence, not a command queue.
- Do not store token values, private keys, Telegram payloads, customer records,
  raw prompts, raw request bodies, or Secret Manager values.
- Keep trading paper-only; the audit stream is observability, not permission to
  execute.
- Any new autonomous action path should add a focused audit event before it gets
  broader execution power.
