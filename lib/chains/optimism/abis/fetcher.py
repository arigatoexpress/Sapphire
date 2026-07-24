"""Optimism ABI fetcher — minimal pinned-ABI loader."""

from __future__ import annotations

import json
import pathlib
from typing import Any


class AbiFetchError(Exception):
    """Raised when an ABI cannot be loaded or fetched."""


def load_pinned_abi(rel_path: str, *, base_dir: pathlib.Path | None = None) -> list[dict[str, Any]]:
    """Load a checked-in ABI by path relative to ``lib/chains/optimism/abis/``."""
    root = base_dir or pathlib.Path(__file__).parent
    target = root / rel_path
    if not target.exists():
        raise AbiFetchError(f"pinned ABI missing: {target}")
    return json.loads(target.read_text(encoding="utf-8"))
