"""Pinned Aave V3 / Optimism ABIs.

ABIs are checked into git (one JSON per role + a sibling `.meta.json` with
chain_id, source, hash, fetched_at). They are byte-for-byte identical to
the Arbitrum-side ABIs (PR #557) because Aave V3 ships the same protocol
contract code to every L2 it deploys to — only the address bundle and
the underlying RPC endpoint change. Sourcify-equivalent provenance
applies (Aave's contracts are full-match Sourcify on every supported
chain).

The :func:`load_pinned_abi` helper here mirrors the Arbitrum side so the
typed contract wrappers can use the same import path
(``from .abis import load_pinned_abi``).
"""

from __future__ import annotations

import json
import pathlib
from typing import Any


class AbiLoadError(RuntimeError):
    """Raised when a pinned ABI is missing or unparseable."""


def load_pinned_abi(rel_path: str, *, base_dir: pathlib.Path | None = None) -> list[dict[str, Any]]:
    """Load a checked-in ABI by path relative to ``lib/chains/optimism/abis/``.

    Mirror of :func:`lib.chains.arbitrum.abis.fetcher.load_pinned_abi` —
    we keep both signatures compatible so the contract wrappers can be
    swapped with a single import-path change.
    """
    root = base_dir or pathlib.Path(__file__).parent
    target = root / rel_path
    if not target.exists():
        raise AbiLoadError(f"pinned ABI missing: {target}")
    return json.loads(target.read_text())
