"""Vector clock implementation for distributed agent coordination."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from .time_sync import get_timestamp_us

logger = logging.getLogger(__name__)


class VectorClock:
    """Lamport vector clock for distributed event ordering."""

    def __init__(self, node_id: str, initial_time: Optional[int] = None):
        self.node_id = node_id
        self.clock: Dict[str, int] = defaultdict(int)
        self.clock[node_id] = initial_time or get_timestamp_us()

    def increment(self) -> None:
        """Increment this node's logical clock."""
        self.clock[self.node_id] += 1

    def update(self, other_clock: Dict[str, int]) -> None:
        """Update clock with values from another clock (receive event)."""
        self.increment()  # Local event (receiving)
        for node, time in other_clock.items():
            self.clock[node] = max(self.clock[node], time)

    def merge(self, other_clock: "VectorClock") -> None:
        """Merge with another vector clock."""
        self.increment()
        for node, time in other_clock.clock.items():
            self.clock[node] = max(self.clock[node], time)

    def compare(self, other_clock: Dict[str, int]) -> int:
        """
        Compare vector clocks.
        Returns:
        -1 if self < other (self happened before other)
         0 if concurrent
         1 if self > other (self happened after other)
        """
        self_greater = False
        other_greater = False

        all_nodes = set(self.clock.keys()) | set(other_clock.keys())

        for node in all_nodes:
            self_time = self.clock.get(node, 0)
            other_time = other_clock.get(node, 0)

            if self_time > other_time:
                self_greater = True
            elif other_time > self_time:
                other_greater = True

        if self_greater and not other_greater:
            return 1
        elif other_greater and not self_greater:
            return -1
        else:
            return 0

    def copy(self) -> "VectorClock":
        """Create a copy of this vector clock."""
        new_clock = VectorClock(self.node_id)
        new_clock.clock = self.clock.copy()
        return new_clock

    def to_dict(self) -> Dict[str, int]:
        """Convert to dictionary for serialization."""
        return dict(self.clock)

    @classmethod
    def from_dict(cls, node_id: str, clock_dict: Dict[str, int]) -> "VectorClock":
        """Create vector clock from dictionary."""
        clock = cls(node_id)
        clock.clock.update(clock_dict)
        return clock

    def __str__(self) -> str:
        return f"VC({self.node_id}: {dict(self.clock)})"

    def __repr__(self) -> str:
        return self.__str__()


class DistributedEvent:
    """Distributed event with vector clock timestamp."""

    def __init__(
        self,
        event_id: str,
        node_id: str,
        event_type: str,
        data: Dict,
        vector_clock: Optional[VectorClock] = None,
    ):
        self.event_id = event_id
        self.node_id = node_id
        self.event_type = event_type
        self.data = data
        self.timestamp_us = get_timestamp_us()
        self.vector_clock = vector_clock or VectorClock(node_id)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "node_id": self.node_id,
            "event_type": self.event_type,
            "data": self.data,
            "timestamp_us": self.timestamp_us,
            "vector_clock": self.vector_clock.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "DistributedEvent":
        """Create event from dictionary."""
        vector_clock = VectorClock.from_dict(data["node_id"], data["vector_clock"])
        event = cls(
            event_id=data["event_id"],
            node_id=data["node_id"],
            event_type=data["event_type"],
            data=data["data"],
            vector_clock=vector_clock,
        )
        event.timestamp_us = data["timestamp_us"]
        return event


class AgentCoordinator:
    """Coordinates distributed agents using vector clocks."""

    def __init__(self, node_id: str):
        self.node_id = node_id
        self.vector_clock = VectorClock(node_id)
        self.pending_events: Dict[str, DistributedEvent] = {}
        self.delivered_events: Set[str] = set()
        self.event_queue: asyncio.Queue = asyncio.Queue()

    async def send_event(self, event_type: str, data: Dict) -> DistributedEvent:
        """Send a new event with updated vector clock."""
        self.vector_clock.increment()
        event_id = f"{self.node_id}_{self.vector_clock.clock[self.node_id]}_{get_timestamp_us()}"

        event = DistributedEvent(event_id, self.node_id, event_type, data, self.vector_clock.copy())
        await self.event_queue.put(event)
        return event

    async def receive_event(self, event_dict: Dict) -> None:
        """Receive and process a distributed event."""
        event = DistributedEvent.from_dict(event_dict)

        # Update local vector clock
        self.vector_clock.update(event.vector_clock.to_dict())

        # Add to pending events for causal ordering
        self.pending_events[event.event_id] = event

        # Try to deliver events that are now causally ready
        await self._deliver_ready_events()

    async def _deliver_ready_events(self) -> None:
        """Deliver events that are causally ready."""
        to_deliver = []

        for event_id, event in self.pending_events.items():
            if event_id in self.delivered_events:
                continue

            # Check if this event can be delivered (all causal dependencies satisfied)
            can_deliver = True
            for node, time in event.vector_clock.clock.items():
                if node == event.node_id:
                    # For the sender, we need time <= current clock + 1
                    if time > self.vector_clock.clock.get(node, 0) + 1:
                        can_deliver = False
                        break
                else:
                    # For other nodes, we need time <= current clock
                    if time > self.vector_clock.clock.get(node, 0):
                        can_deliver = False
                        break

            if can_deliver:
                to_deliver.append(event_id)

        # Deliver events in causal order
        for event_id in sorted(to_deliver, key=lambda x: self.pending_events[x].timestamp_us):
            event = self.pending_events[event_id]
            await self._process_event(event)
            self.delivered_events.add(event_id)
            del self.pending_events[event_id]

    async def _process_event(self, event: DistributedEvent) -> None:
        """Process a delivered event."""
        logger.debug(
            f"Processing event: {event.event_id} ({event.event_type}) from {event.node_id}"
        )

        # Handle different event types
        if event.event_type == "trade_signal":
            await self._handle_trade_signal(event)
        elif event.event_type == "position_update":
            await self._handle_position_update(event)
        elif event.event_type == "risk_alert":
            await self._handle_risk_alert(event)

    async def _handle_trade_signal(self, event: DistributedEvent) -> None:
        """Handle trade signal event."""
        # Implement trade signal coordination logic
        signal_data = event.data
        logger.info(f"Coordinated trade signal from {event.node_id}: {signal_data}")

    async def _handle_position_update(self, event: DistributedEvent) -> None:
        """Handle position update event."""
        # Implement position update coordination logic
        position_data = event.data
        logger.info(f"Coordinated position update from {event.node_id}: {position_data}")

    async def _handle_risk_alert(self, event: DistributedEvent) -> None:
        """Handle risk alert event."""
        # Implement risk alert coordination logic
        alert_data = event.data
        logger.warning(f"Coordinated risk alert from {event.node_id}: {alert_data}")

    def get_coordination_stats(self) -> Dict:
        """Get coordination statistics."""
        return {
            "node_id": self.node_id,
            "vector_clock": self.vector_clock.to_dict(),
            "pending_events": len(self.pending_events),
            "delivered_events": len(self.delivered_events),
            "queue_size": self.event_queue.qsize(),
        }


# Global coordinator instance
_coordinator: Optional[AgentCoordinator] = None


async def get_agent_coordinator(node_id: str) -> AgentCoordinator:
    """Get global agent coordinator instance."""
    global _coordinator
    if _coordinator is None:
        _coordinator = AgentCoordinator(node_id)
    return _coordinator
