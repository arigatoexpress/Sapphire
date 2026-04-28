# Tranche 5 Live-Soak Readiness Runbook

This runbook covers local, operator-safe verification before any Tranche 4
daemon or plugin is considered for a live soak. The harness is read-only: it
does not call live APIs, send Telegram messages, place trades, load
LaunchAgents, or mutate event-bus state.

## Scope

Run the harness from the Sapphire repo root:

```bash
python3 scripts/ops/tranche5_live_soak_readiness.py
```

Use JSON when another tool needs the output:

```bash
python3 scripts/ops/tranche5_live_soak_readiness.py --json
```

Run local status probes only when you want the harness to execute the known-safe
status commands:

```bash
python3 scripts/ops/tranche5_live_soak_readiness.py --run-status --json
```

Use strict mode for a gate that should fail on missing files, status command
failures, or enabled live/publish flags:

```bash
python3 scripts/ops/tranche5_live_soak_readiness.py --strict --json
```

## What It Checks

The harness inventories these Tranche 4 surfaces:

- Narrative Synthesis
- Regulatory + Macro Intelligence
- Cross-Asset Regime Intelligence
- On-Chain Intelligence
- Hyperliquid Counter-Party Intelligence
- Historical Event-Impact Modeling
- Adversarial Signal Defense

For each surface it reports:

- Live and publish environment gates, with values redacted
- Cache and counter locations
- Latest generated artifacts and JSONL row counts where applicable
- Required service, library, and plugin files
- LaunchAgent templates where they exist
- Safe local status commands

## Safety Posture

The default run is inventory-only. `--run-status` only executes commands that
are intended to report local status. It intentionally excludes commands that
could traverse provider collection or rebuild paths under an ambient live
environment, even when those commands offer no-write or dry-run flags.

Do not export live flags in the shell used for readiness unless the purpose is
to verify that the harness warns. A warning is expected if any live or publish
gate is enabled.

Live and publish gates currently inventoried include:

- `SAPPHIRE_NARRATIVE_LIVE`
- `SAPPHIRE_NARRATIVE_LIVE_BUS`
- `SAPPHIRE_MACRO_INTEL_LIVE`
- `SAPPHIRE_MACRO_INTEL_LIVE_BUS`
- `SAPPHIRE_CROSS_ASSET_LIVE`
- `SAPPHIRE_GLASSNODE_LIVE`
- `SAPPHIRE_SANTIMENT_LIVE`
- `SAPPHIRE_ETH_NODE_LIVE`
- `SAPPHIRE_SOL_NODE_LIVE`
- `SAPPHIRE_ONCHAIN_LIVE_BUS`
- `SAPPHIRE_HYPERLIQUID_LIVE`
- `SAPPHIRE_EVENT_IMPACT_REBUILD`
- `SAPPHIRE_EVENT_IMPACT_LIVE_BUS`
- `SAPPHIRE_ADVERSARIAL_QUARANTINE`

## Interpreting Results

`pass` means required files are present, no live or publish flags are enabled,
and any requested status commands exited successfully.

`warn` means at least one live or publish gate is enabled. Treat this as a stop
for local soak readiness unless that shell was intentionally configured for a
flag-detection test.

`fail` means at least one required file is missing or a requested status command
failed. Review the per-surface section before trying a broader gate.

## Recommended Local Gate

Before opening or updating a Tranche 5 readiness PR, run:

```bash
python3 -m pytest tests/unit/test_tranche5_live_soak_readiness.py -q
python3 scripts/ops/tranche5_live_soak_readiness.py --json
python3 scripts/ops/tranche5_live_soak_readiness.py --run-status --json
```

If `--run-status` reports command failures caused by missing optional runtime
dependencies, record the exact dependency gap in the PR notes. Do not work
around it by enabling live flags, loading LaunchAgents, sending Telegram tests,
or touching trading-critical paths.

## Troubleshooting

If status is `warn`, inspect `summary.enabled_live_or_publish_flags` and unset
those variables before repeating the local gate.

If status is `fail`, inspect `missing_required_files` and
`summary.status_command_failures`. Missing Tranche 4 files usually indicate the
branch is not based on the expected `origin/main` baseline.

If artifacts are absent, that is not automatically a failure. The harness
reports artifact availability so an operator can tell whether a surface has
recent dry-run output to inspect before a soak.
