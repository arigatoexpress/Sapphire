"""Re-export the shared ``TypedContract`` base class.

The MegaETH and Arbitrum chain packages both use the exact same
selector/encode/decode plumbing — duplicating it would let the two
copies drift apart silently. The Protocol it depends on
(``_MegaETHCallable``, named for historical reasons) is structural,
so :class:`~lib.chains.arbitrum.client.ArbitrumClient` satisfies it
the same way :class:`MegaETHClient` does.

If/when we move the base into a chain-agnostic location (e.g.
``lib/chains/_evm/contracts/base.py``), update the re-export here so
no consumer of this module has to change.
"""

from __future__ import annotations

from lib.chains.megaeth.contracts.base import (  # noqa: F401 — re-export
    TypedContract,
    _AbiFunction,
    _canonicalize_type,
    _index_abi,
    _MegaETHCallable as _ChainCallable,
)

__all__ = ("TypedContract", "_ChainCallable")
