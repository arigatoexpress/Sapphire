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
- `autonomy.cycle.requested`
- `autonomy.dispatch_evaluated`
- `autonomy.session_created`
- `autonomy.session_decision_applied`

## Schema

Every record includes:

- `event_type`
- `ts`
- `actor`
- `action`
- `outcome`
- optional `risk`
- optional `object_ref_hash`
- optional `object_ref_chars`
- optional sanitized `metadata`

Decision metadata intentionally records summaries only: signal id, symbol,
direction, original/adjusted confidence, rules fired, reason count, and
world-state keys. It does not write raw signals, prompts, request bodies,
secrets, order payloads, full object references, or full world snapshots.

Control-plane autonomy cycle metadata records payload key names and a hash of
the requested actor only. It does not write raw bridge payload values.

Alpha dispatch evaluation metadata records trigger/agent/reason codes,
available venue and preferred-symbol counts, failure pressure, pending session
count, and whether code, GCP, or owner-approval gates were active. It covers
disabled, rate-limited, dry-run, no-dispatcher, and not-dispatched outcomes
without writing raw instructions, full context snapshots, symbol lists, venue
payloads, Telegram payloads, or dispatcher request bodies.

Alpha autonomy session decision metadata records decision/outcome, dispatch
status, reason code, hook-result key names, note length, and hashed session and
source identifiers. It does not write raw session keys, Telegram/chat sources,
operator notes, or dispatch payload values.

Alpha autonomy session creation metadata records trigger code, instruction
length, approval mode, and a hashed session identifier. It does not write raw
session keys or generated instructions.

## Safety Rules

- Treat the log as local operator evidence, not a command queue.
- Do not store token values, private keys, Telegram payloads, customer records,
  raw prompts, raw request bodies, or Secret Manager values.
- Keep trading paper-only; the audit stream is observability, not permission to
  execute.
- Any new autonomous action path should add a focused audit event before it gets
  broader execution power.

## Operator Status

Use `scripts/ops/safety_status_report.py` for paste-safe status. The report
summarizes autonomy event, actor, outcome, and risk counts, and hashes action
and object references for recent events. It intentionally omits raw metadata
values, prompts, request bodies, order payloads, and secret-like text.

The same report also performs a lightweight schema read-back check:

- total lines and valid JSON record count
- malformed line count
- missing required field counts for `event_type`, `ts`, `actor`, `action`, and
  `outcome`
- count of records that still contain unredacted secret-shaped keys or text

These checks emit counts only. They do not print raw audit metadata or the
offending values.
