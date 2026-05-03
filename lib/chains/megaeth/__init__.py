"""MegaETH (chain id 4326) programmatic-access layer for Sapphire.

Wave A scope (this PR): ABI fetcher + registry + Aave V3 typed wrapper +
read-only intent facade. **Read-only.** No signing, no tx building.
Write paths land in Wave C and route through
``plugins/claw-sapphire/tools/internal/megaeth_executor.py``.

The transport layer is the existing ``MegaETHClient`` from
``plugins.claw_sapphire.tools.internal.megaeth`` (PR #529); we re-use it
verbatim so JSON-RPC plumbing isn't duplicated.

Public API:

* :class:`~lib.chains.megaeth.registry.ProtocolRegistry` —
  typed accessor over ``config/megaeth_protocols.yaml``.
* :class:`~lib.chains.megaeth.contracts.aave_v3.AaveV3` —
  typed read wrapper around the Aave V3 deployment.
* :class:`~lib.chains.megaeth.protocols.MegaETHProtocols` —
  intent-level facade (lend / oracle / etc.). Read-only on Wave A.
"""

from __future__ import annotations

# Re-exports kept lazy to avoid pulling in optional deps at import time;
# call-sites that need a class import from the submodule directly.
__all__ = (
    "ProtocolEntry",
    "ProtocolRegistry",
    "AaveV3",
    "AaveV3Addresses",
    "MegaETHProtocols",
)


def __getattr__(name: str):  # pragma: no cover — pass-through resolver
    if name in ("ProtocolEntry", "ProtocolRegistry"):
        from . import registry as _registry

        return getattr(_registry, name)
    if name in ("AaveV3", "AaveV3Addresses", "ReserveData", "UserAccountData"):
        from .contracts import aave_v3 as _aave

        return getattr(_aave, name)
    if name == "MegaETHProtocols":
        from . import protocols as _protocols

        return _protocols.MegaETHProtocols
    raise AttributeError(name)
