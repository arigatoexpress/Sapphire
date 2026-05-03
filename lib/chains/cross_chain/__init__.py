"""Cross-chain primitives composed over the per-chain protocol facades.

The per-chain packages (``lib/chains/megaeth``, ``lib/chains/arbitrum``,
``lib/chains/optimism``) each expose a self-contained read layer. This
package is where Sapphire joins those reads across chains — the
multi-chain stack proves out only when something actively consumes
data from more than one chain at once.

Modules here should:

* compose 2+ per-chain facades (never less — that's a single-chain
  signal, not a cross-chain primitive)
* be read-only (signals only, never executors)
* fail open / graceful — if one chain's RPC dies, downgrade to
  whichever chains responded and surface the unavailability flag
  on the signal rather than raising

Current modules:

* :mod:`pyth_divergence` — cross-chain Pyth oracle price divergence
  detector. Surfaces basis-point divergence between the on-chain Pyth
  cached price across MegaETH / Arbitrum / Optimism for a given
  underlying (BTC, ETH, SOL, USDC, USDT). Companion to the Aave APY
  arb signal: same "alpha invisible to single-chain tools" thesis,
  but on the *price* axis instead of the rate axis.
"""

from __future__ import annotations

__all__: tuple[str, ...] = ()
