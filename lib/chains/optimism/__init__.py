"""Optimism mainnet (chain id 10) programmatic-access layer for Sapphire.

Mirror of ``lib/chains/arbitrum`` adapted for OP mainnet. Reuses the
``TypedContract`` base, the Aave V3 ray-rate helper, and the
``ReserveData`` shape — the only Optimism-specific pieces are the RPC
default, the address bundle, and the registry yaml.

Read-only on purpose. Write paths are deliberately out of scope and will
land in their own gated executor (mirroring the MegaETH wave-C pattern).

Public API:

* :class:`~lib.chains.optimism.registry.ProtocolRegistry` —
  typed accessor over ``config/optimism_protocols.yaml``.
* :class:`~lib.chains.optimism.contracts.aave_v3.AaveV3Optimism` —
  typed read wrapper around the Aave V3 deployment on OP mainnet.
* :class:`~lib.chains.optimism.protocols.OptimismProtocols` —
  intent-level facade (lend / oracle / etc.). Read-only.
"""

from __future__ import annotations

__all__ = (
    "ProtocolEntry",
    "ProtocolRegistry",
    "AaveV3Optimism",
    "AaveV3Addresses",
    "OptimismProtocols",
)


def __getattr__(name: str):  # pragma: no cover — pass-through resolver
    if name in ("ProtocolEntry", "ProtocolRegistry"):
        from . import registry as _registry

        return getattr(_registry, name)
    if name in ("AaveV3Optimism", "AaveV3Addresses", "ReserveData", "UserAccountData"):
        from .contracts import aave_v3 as _aave

        return getattr(_aave, name)
    if name == "OptimismProtocols":
        from . import protocols as _protocols

        return _protocols.OptimismProtocols
    raise AttributeError(name)
