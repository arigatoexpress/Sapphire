# On-Chain Intel Runbook

## Purpose

This runbook tells an operator how to run Sapphire's on-chain intelligence service safely. The system collects read-only provider context from Glassnode, Santiment, Ethereum JSON-RPC, and Solana JSON-RPC, aggregates it into schema version `0.2.0`, and writes latest/archive snapshots for downstream intelligence lanes. Fixture mode is the default and expected local posture. Live mode is opt-in per provider and should be introduced one provider at a time.

The core safety promise is simple: no wallet keys, no transaction signing, no order placement, no real trading. On-chain data is context for research and narrative synthesis. It is not an execution authority.

## Quick Status

Run status from the service wrapper:

```bash
/usr/local/bin/python3 services/onchain_intel/run.py status
```

Run status through the plugin:

```bash
echo '{"action":"status"}' | /usr/local/bin/python3 plugins/claw-sapphire/tools/onchain_intel.py
```

Expected default output:

- `mode=fixture`
- `wallet_keys_required=false`
- `trading_enabled=false`
- all provider `live_enabled=false`

If any provider unexpectedly shows `live_enabled=true`, inspect the shell environment before continuing. The provider requires both its gate and its credential/RPC env var; remove either to return to fixture mode.

## Dry-Run Snapshot

Use the daemon entrypoint without writes:

```bash
/usr/local/bin/python3 services/onchain_intel/run.py run-once --assets BTC,ETH --backfill-days 30 --no-write
```

Use the older one-shot compatibility module:

```bash
/usr/local/bin/python3 -m services.onchain_intel.run_once --assets BTC,ETH --backfill-days 30 --no-write
```

Use the plugin:

```bash
echo '{"action":"snapshot","assets":["BTC","ETH"],"backfill_days":30}' \
  | /usr/local/bin/python3 plugins/claw-sapphire/tools/onchain_intel.py
```

In fixture mode, no network call should be attempted. The snapshot should include provider fixture payloads, Ethereum/Solana read-only node fixture state, and a composite heat score per asset.

## Live Provider Enablement

Enable only one provider at a time. Start with a narrow asset list and a short backfill. Keep `--no-write` on the first smoke check so generated data stays out of the repo.

Glassnode:

```bash
export SAPPHIRE_GLASSNODE_LIVE=1
export GLASSNODE_API_KEY=...
/usr/local/bin/python3 services/onchain_intel/run.py run-once --assets BTC --backfill-days 7 --no-write
```

Santiment:

```bash
export SAPPHIRE_SANTIMENT_LIVE=1
export SANTIMENT_API_KEY=...
/usr/local/bin/python3 services/onchain_intel/run.py run-once --assets BTC --backfill-days 7 --no-write
```

Ethereum RPC:

```bash
export SAPPHIRE_ETH_NODE_LIVE=1
export ETH_RPC_URL=https://example-read-only-rpc
/usr/local/bin/python3 services/onchain_intel/run.py run-once --assets ETH --backfill-days 1 --no-write
```

Solana RPC:

```bash
export SAPPHIRE_SOL_NODE_LIVE=1
export SOL_RPC_URL=https://example-read-only-rpc
/usr/local/bin/python3 services/onchain_intel/run.py run-once --assets SOL --backfill-days 1 --no-write
```

Never put wallet seed phrases, private keys, or signing-service credentials in these env vars. RPC URLs should be project/read-only endpoints. If a provider's API returns schema changes, the client should fail closed into warnings rather than fabricating values.

## Caps And Usage Ledger

The local live-call ledger is at:

```text
~/.sapphire/onchain_intel/usage.json
```

Default limits:

- 60 calls per provider per hour.
- 100,000 calls per provider per day.
- 730 days maximum backfill.

In tests or disposable sandboxes, override the ledger path:

```bash
export SAPPHIRE_ONCHAIN_USAGE_FILE=/tmp/sapphire-onchain-usage.json
```

Do not override the ledger path in production scheduling unless you are intentionally isolating an experiment. The ledger is the protection against repeated agent/tool invocations spending through provider quotas.

## Writes And Provenance

With writes enabled, the service writes:

- latest snapshot: `data/intelligence/latest/onchain_intel.json`
- latest sidecar: `data/intelligence/latest/onchain_intel.json.envelope.json`
- archive snapshot: `data/onchain_intel/onchain_intel_<timestamp>.json`
- archive sidecar: adjacent `.envelope.json`

These are runtime artifacts. Do not commit generated snapshots unless an operator explicitly asks for a fixture or handoff artifact. The sidecars are written through `lib.core.provenance.write_envelope_sidecar` and identify the aggregator source.

## Event Bus Publishing

Publishing is off by default. Passing `--publish` is not enough. The environment must also include:

```bash
export SAPPHIRE_ONCHAIN_LIVE_BUS=1
```

The published topic is:

```text
onchain.snapshot.updated
```

If the event bus is unavailable, collection still succeeds and the response includes a publish error. This keeps data collection from becoming dependent on local Redis or event-bus health.

## LaunchAgent

The template lives at:

```text
services/onchain_intel/launchagent/com.sapphire.onchain-intel.plist.template
```

It is not installed by this PR. Before installing, verify:

```bash
plutil -lint services/onchain_intel/launchagent/com.sapphire.onchain-intel.plist.template
/usr/local/bin/python3 services/onchain_intel/run.py run-once --no-write
```

The default cadence is 30 minutes. Keep live provider gates unset until you have run at least one fixture smoke and one provider-specific live smoke manually.

## Verification

Run focused tests:

```bash
/usr/local/bin/python3 -m pytest \
  tests/unit/test_chain_providers.py \
  tests/unit/test_onchain_aggregator.py \
  tests/unit/test_onchain_node_providers.py \
  tests/unit/test_onchain_intel_service.py \
  plugins/claw-sapphire/tests/test_onchain_intel_tool.py \
  -q --tb=short
```

Run registry validation:

```bash
/usr/local/bin/python3 scripts/validate_tool_registry.py
```

Before opening a PR, use the broader Sapphire gates: ruff, full `tests/unit/`, full `plugins/claw-sapphire/tests/`, registry validation, and `production_readiness_sweep.py --no-external`.

## Triage

If a provider returns fixture mode unexpectedly, check for missing gate or missing credential. Both are required. If a live provider raises `RateCapError`, inspect the usage ledger and wait for the next hour/day boundary. If a node RPC rejects a method, confirm the method is read-only. Mutating methods are intentionally blocked.

If snapshot writes fail, inspect filesystem permissions under `data/intelligence/latest` and `data/onchain_intel`. If event publishing fails, check `SAPPHIRE_ONCHAIN_LIVE_BUS` and the local event-bus process, but do not retry in a tight loop. The daemon should stay boring: one snapshot every 30 minutes, no surprise spends, no surprise trades.

## Provider-Specific Notes

Glassnode should be introduced first with a short BTC-only smoke because each asset snapshot can call several metric endpoints. Watch the usage ledger after the first run and confirm it remains below the hourly cap. If a metric endpoint is unavailable on the account plan, the provider error should appear in the snapshot warnings. Do not patch around that by inventing substitute values; either document the missing metric or adjust the provider path after checking the actual Glassnode contract.

Santiment should be introduced after Glassnode because the GraphQL path is easy to inspect but can be plan-sensitive. The fixture covers social volume, social dominance, age consumed, network growth, developer activity, and exchange open interest. In live mode, verify one metric at a time if the provider returns GraphQL errors. The service should remain useful when one metric fails, but a repeated plan-denied error should be documented in the operator handoff.

Ethereum RPC and Solana RPC should use read-only project URLs. If the RPC vendor has a dashboard, check request counts after a smoke run. The clients reject transaction-broadcast methods by name, but the operator should still avoid authenticated wallet endpoints or URLs tied to hot-wallet infrastructure. Treat RPC URLs as operational secrets and do not log them in PR bodies or handoff docs.

## Integration Checklist

Before wiring this lane into narrative synthesis or observability, verify:

- `onchain_intel` is present in `infra/tool-registry.yaml`.
- `services/onchain_intel/run.py status` returns fixture mode with all live gates off.
- `services/onchain_intel/run.py run-once --no-write` returns `wallet_keys_required=false`.
- `plugins/claw-sapphire/tools/onchain_intel.py` returns equivalent status.
- Generated snapshot sidecars verify if writes are enabled.
- Full Sapphire unit and plugin suites still pass separately.

The integration pass should consume only the snapshot output. It should not import provider clients directly, and it should not read provider credentials. That keeps the dependency direction clean: provider clients gather data, the aggregator normalizes it, downstream intelligence consumes the normalized artifact.

## Incident Response

If a live key is accidentally enabled, unset the relevant gate first, then rotate or revoke the provider credential if there is any chance it was exposed. Check the usage ledger for call volume and provider dashboards for billing impact. If generated snapshots were committed accidentally and contain sensitive provider metadata, stop and ask for a cleanup plan before rewriting history. The current snapshot code does not include secret values, but caution is the right default.

If the daemon loops too quickly, unload the LaunchAgent or kill the process, then inspect the command arguments. The template uses a 30-minute cadence. Anything materially shorter should have an explicit reason in a handoff note. If the event bus receives duplicate `onchain.snapshot.updated` events, disable `SAPPHIRE_ONCHAIN_LIVE_BUS` and debug locally with `--no-write`.

## Maintenance

Keep this lane boring. Update provider metric names only after checking the provider's current documentation or a live plan response. Add tests for every new metric path and every new safety gate. When adding provider data to dashboards, show mode and freshness next to the metric so an operator can tell fixture/demo data from live source data. When adding narrative prompts, pass summarized snapshot fields, not raw provider payloads, to control prompt length and avoid leaking operational details.

## Handoff Notes

When handing this lane to another operator, include the canonical commit SHA, the provider gates that were enabled during the run, whether any live provider dashboard showed billable calls, and the exact verification commands used. Do not include API keys, RPC URLs, account IDs, or screenshots that expose provider quotas tied to a private account. If a live smoke used a non-default usage ledger path, include that path only if it is disposable and does not reveal secrets.

For acquisition or diligence demos, say "fixture-backed unless explicitly live-gated" in the demo script. That avoids ambiguity when a buyer sees realistic BTC/ETH/SOL numbers. Fixture data is useful for proving the schema and safety posture; it is not evidence of current market state. If current market state matters, run a live smoke immediately before the demo and note the provider modes in the output.

## Common Good States

A healthy fixture response has zero live providers, no warnings, populated BTC/ETH/SOL asset rows, Ethereum and Solana read-only node blocks, sidecars after writes, and `trading_enabled=false`. A healthy live response has exactly the provider you enabled in `live_providers`, usage ledger increments for that provider only, and no wallet material in the JSON output. Anything outside those patterns deserves a pause before scheduling.

## Rollback

Disable all live gates:

```bash
unset SAPPHIRE_GLASSNODE_LIVE SAPPHIRE_SANTIMENT_LIVE
unset SAPPHIRE_ETH_NODE_LIVE SAPPHIRE_SOL_NODE_LIVE
unset SAPPHIRE_ONCHAIN_LIVE_BUS
```

Stop any LaunchAgent if installed by the operator. In fixture mode, the service remains safe to run because it performs no live provider calls and touches no wallet material.
