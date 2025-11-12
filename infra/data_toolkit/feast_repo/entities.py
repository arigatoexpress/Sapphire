from __future__ import annotations

from feast import Entity
from feast import ValueType

market = Entity(
    name="market",
    join_keys=["symbol"],
    description="Unique identifier per perpetual futures contract",
)

agent_entity = Entity(
    name="agent",
    join_keys=["agent"],
    description="Trading agent identifier",
)

__all__ = ["market", "agent_entity"]

