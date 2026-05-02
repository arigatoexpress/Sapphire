"""Arbitrum One (chain id 42161) programmatic-access layer for Sapphire.

Mirror of ``lib/chains/megaeth`` adapted for Arbitrum One. Reuses the
``TypedContract`` base, the Aave V3 ray-rate helper, and the ``ReserveData``
shape — the only Arbitrum-specific code is the RPC default, the Arbiscan
ABI fetcher (different shape from Blockscout), and the address bundle.

Read-only on purpose. Write paths are deliberately out of scope and will
land in their own gated executor (mirroring the MegaETH wave-C pattern).

Public API:

* :class:`~lib.chains.arbitrum.registry.ProtocolRegistry` —
  typed accessor over ``config/arbitrum_protocols.yaml``.
* :class:`~lib.chains.arbitrum.contracts.aave_v3.AaveV3Arbitrum` —
  typed read wrapper around the Aave V3 deployment on Arbitrum One.
* :class:`~lib.chains.arbitrum.protocols.ArbitrumProtocols` —
  intent-level facade (lend / oracle / etc.). Read-only.
"""

from __future__ import annotations

__all__ = (
    "ProtocolEntry",
    "ProtocolRegistry",
    "AaveV3Arbitrum",
    "AaveV3Addresses",
    "ArbitrumProtocols",
)


def __getattr__(name: str):  # pragma: no cover — pass-through resolver
    if name in ("ProtocolEntry", "ProtocolRegistry"):
        from . import registry as _registry

        return getattr(_registry, name)
    if name in ("AaveV3Arbitrum", "AaveV3Addresses", "ReserveData", "UserAccountData"):
        from .contracts import aave_v3 as _aave

        return getattr(_aave, name)
    if name == "ArbitrumProtocols":
        from . import protocols as _protocols

        return _protocols.ArbitrumProtocols
    raise AttributeError(name)
