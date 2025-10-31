from __future__ import annotations

from feast import Entity

market = Entity(
    name="market",
    join_keys=["symbol"],
    description="Unique identifier per perpetual futures contract",
)

__all__ = ["market"]

