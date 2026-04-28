# Tranche 4 Live-Soak Readiness

This runbook covers the read-only readiness harness for the Tranche 4 narrative,
macro, on-chain, and event-impact surfaces. The harness is for operator review
before any live soak. It reports what is observed and what is unknown; it does
not enable flags, publish to the event bus, send Telegram messages, place
trades, fetch paid providers, or write runtime artifacts.

## Command

Run the markdown view:

```bash
/usr/local/bin/python3 scripts/ops/tranche4_live_soak_readiness.py --format markdown
```

Run the JSON view:

```bash
/usr/local/bin/python3 scripts/ops/tranche4_live_soak_readiness.py --format json
```

Skip service imports when you only want env and artifact facts:

```bash
/usr/local/bin/python3 scripts/ops/tranche4_live_soak_readiness.py --no-service-status --format json
```

## What It Checks

Live flags:

- `SAPPHIRE_NARRATIVE_LIVE`
- `SAPPHIRE_NARRATIVE_LIVE_BUS`
- `SAPPHIRE_MACRO_INTEL_LIVE`
- `SAPPHIRE_MACRO_INTEL_LIVE_BUS`
- `SAPPHIRE_GLASSNODE_LIVE`
- `SAPPHIRE_SANTIMENT_LIVE`
- `SAPPHIRE_ETH_NODE_LIVE`
- `SAPPHIRE_SOL_NODE_LIVE`
- `SAPPHIRE_ONCHAIN_LIVE_BUS`
- `SAPPHIRE_EVENT_IMPACT_LIVE_BUS`

Credential presence is sanitized. The harness reports only whether expected
variable names are present in the process environment or in
`~/.sapphire/secrets.env`; it never prints secret values.

Artifact evidence:

- Narrative input/output: `data/correlated_signals/*/signals.jsonl`,
  `data/narratives/*/theses.jsonl`
- Macro output: `data/macro/*/events.jsonl`, `data/macro/*/calendar.jsonl`
- On-chain output: `data/intelligence/latest/onchain_intel.json`,
  `data/onchain_intel/*.json`
- Event-impact output: `data/event_impact/model_*.json`,
  `data/event_impact/expected_reactions.jsonl`

Each row is labeled `OBSERVED` when the harness could verify the fact locally,
or `UNKNOWN` when a file, service, or secret-file state could not be verified.

## Acceptance Checks

For a safe dry-run soak posture:

1. `summary.safe_defaults_observed` is `true`.
2. `summary.enabled_live_flags` is empty.
3. `safety.external_writes_attempted` is `false`.
4. `safety.event_bus_publish_attempted` is `false`.
5. All credential rows have `secret_values_redacted=true`.
6. Readiness rows are either `ready_with_artifact_evidence` or
   `ready_needs_soak_artifact`, not `blocked_live_flag_enabled`.

Artifact absence does not mean the service is unsafe. It means the soak has not
yet produced enough local evidence to promote. Run the existing dry-run commands
from the surface runbooks, inspect generated local artifacts, then rerun this
harness.

## Operator Notes

Keep live model/provider/RPC flags off until the dry-run artifact path is clean.
When a live smoke is approved, enable one gate at a time, run a short manual
check, inspect provider usage or event output, and turn the gate back off. Do
not combine first live provider calls with event-bus publishing.

Event-impact runtime is lookup-only. Rebuilding the model is a separate
operator-gated action through `SAPPHIRE_EVENT_IMPACT_REBUILD=1` and the local
OpenBB-compatible API. This readiness harness does not rebuild models.
