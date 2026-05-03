"""Cross-chain primitives composed over the per-chain protocol facades.

The per-chain packages (``lib/chains/megaeth``, ``lib/chains/arbitrum``,
``lib/chains/optimism``) each expose a self-contained read layer. This
package is the *first* primitive that joins those reads across chains —
the multi-chain stack proves out only when something actively consumes
data from more than one chain at once.

Modules here should:

* compose, never embed — they take per-chain facades / clients as
  constructor arguments rather than instantiating them
* be read-only on this side of the wall — write paths route through
  per-chain gated executors
* be graceful: a single chain RPC failure should degrade the result,
  not crash the cross-chain consumer

First module: ``aave_apy_arb`` — detects Aave V3 supply/borrow APY
spreads between MegaETH / Arbitrum / Optimism that exceed a configurable
basis-point threshold (signal generator only; does not execute).
"""
