# Contributing to sapphire-sentinel-gate

## Vendoring trade-off

This package is a **vendored snapshot** of the chain-health primitive from
the [Sapphire](https://github.com/arigatoexpress/Sapphire) monorepo. The
upstream files live at:

- `lib/hackathon/chain_health_gate.py` — the dispatcher and `ChainHealthVerdict` shape
- `lib/hackathon/arbitrum_chain_health.py` — the pure Arbitrum classifier
- `lib/chains/megaeth/contracts/peg_monitor.py` — the `PegBreak` enum (one symbol vendored)

Vendoring (vs. `from lib.hackathon import ...`) means this package is
installable standalone, with no dependency on the Sapphire monorepo. The
trade-off is a small amount of duplicated code that has to be re-synced
when the upstream primitive evolves.

## Sync workflow

When `lib/hackathon/chain_health_gate.py` (or its dependencies) change
upstream, run:

```bash
# TODO: scripts/sync_sentinel_gate_package.sh — to be written
# Tracked in: https://github.com/arigatoexpress/Sapphire/issues
```

The sync is mostly mechanical:

1. Copy the upstream file into `src/sentinel_gate/_internal/`.
2. Strip the `from lib.chains.megaeth...` imports — replace with the
   local enum + duck-typed protocol stubs vendored in this package.
3. Re-run the test suite (`pytest tests/`) to confirm the classifier
   still produces the expected verdicts on the fixture inputs.
4. Bump the package version per semver — patch for upstream-compatible
   classifier changes, minor for new chain support, major for verdict
   shape changes.

## Honest scope

This package only ships the **classifier and dispatcher**. The live RPC
client + chain-specific protocol facades (Aave V3 reads, USDM peg
monitor, Kumbaya pool quotes) are NOT vendored — they would balloon the
package surface 10x and tie users to Sapphire's contract registry. Users
who want the live MegaETH integration either:

- depend on the full `sapphire-os` package (heavy), or
- supply their own duck-typed client to `ChainHealthGate(client_factory=...)`.

The duck-typed contract is documented in the README under "Bring your
own client".
