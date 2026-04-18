"""Free-tier third-party on-chain data clients.

Each provider is a thin, stdlib-only wrapper following the same contract
as ``lib.chain.sources``:

* Synchronous. Caller layers concurrency.
* 5-minute in-process cache (shared with ``sources`` so a cold call
  doesn't double-charge the rate limit).
* Raises :class:`lib.chain.sources.SourceError` on failure.
* Credentials come from env vars named ``<PROVIDER>_API_KEY``.

Providers wired here:
    BGeometrics, Santiment, Dune Analytics, Whale Alert, CoinAPI, Coinglass.

Checkonchain has no public API; it is documented in
``docs/web-integrations.md`` but not clientable.
"""

from __future__ import annotations

from .bgeometrics import BGeometricsClient
from .coinapi import CoinAPIClient
from .coinglass import CoinglassClient
from .dune import DuneClient
from .santiment import SantimentClient
from .whale_alert import WhaleAlertClient

__all__ = [
    "BGeometricsClient",
    "SantimentClient",
    "DuneClient",
    "WhaleAlertClient",
    "CoinAPIClient",
    "CoinglassClient",
]
