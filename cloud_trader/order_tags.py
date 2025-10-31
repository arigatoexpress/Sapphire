"""Helpers for deterministic client order identifiers."""

from __future__ import annotations

import hashlib
import time


def generate_order_tag(bot_id: str, symbol: str, seed: str | None = None) -> str:
    """Return a deterministic idempotent tag for exchanges supporting clientOrderId.

    Parameters
    ----------
    bot_id: str
        Identifier for the strategy/bot emitting the order.
    symbol: str
        Trading pair identifier.
    seed: str | None
        Optional string to increase determinism (e.g., decision hash).
    """

    salt = seed or str(time.time_ns())
    digest = hashlib.sha1(f"{bot_id}:{symbol}:{salt}".encode("utf-8")).hexdigest()[:20]
    return f"{bot_id}_{symbol}_{digest}"

