"""
Event Bus - Decoupled Event-Driven Communication

Implements Redis Pub/Sub for cross-instance messaging with local fallback.
Enables loose coupling between services while maintaining real-time communication.
"""

import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """Base event class for all system events."""

    event_type: str
    data: Dict[str, Any]
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    source: str = "unknown"
    trace_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp,
            "source": self.source,
            "trace_id": self.trace_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        return cls(
            event_type=data["event_type"],
            data=data["data"],
            timestamp=data.get("timestamp", datetime.now().timestamp()),
            source=data.get("source", "unknown"),
            trace_id=data.get("trace_id"),
        )


# Event type constants
class EventTypes:
    """Standard event types for the trading system."""

    TRADE_EXECUTED = "trade.executed"
    TRADE_FAILED = "trade.failed"
    POSITION_OPENED = "position.opened"
    POSITION_CLOSED = "position.closed"
    AGENT_DECISION = "agent.decision"
    AGENT_CONSENSUS = "agent.consensus"
    MARKET_REGIME_CHANGED = "market.regime_changed"
    PLATFORM_HEALTH_CHANGED = "platform.health_changed"
    SYSTEM_ALERT = "system.alert"
    PORTFOLIO_UPDATED = "portfolio.updated"


EventCallback = Callable[[Event], None]


class EventBus:
    """
    Event Bus for decoupled inter-service communication.

    Features:
    - Local pub/sub for same-instance communication
    - Redis Pub/Sub for cross-instance communication (when available)
    - Event history for debugging
    - Async-native design

    Usage:
        bus = await get_event_bus()

        # Subscribe to events
        bus.subscribe(EventTypes.TRADE_EXECUTED, on_trade_executed)

        # Publish events
        await bus.publish(Event(
            event_type=EventTypes.TRADE_EXECUTED,
            data={"symbol": "BTC-USDC", "side": "BUY"},
            source="platform_router"
        ))
    """

    def __init__(self, instance_id: str = "default"):
        self.instance_id = instance_id
        self._subscribers: Dict[str, List[EventCallback]] = defaultdict(list)
        self._redis = None
        self._pubsub = None
        self._listener_task: Optional[asyncio.Task] = None
        self._history: List[Event] = []
        self._history_limit = 1000
        self._shutdown_event = asyncio.Event()

        # Statistics
        self.stats = {
            "events_published": 0,
            "events_received": 0,
            "callbacks_executed": 0,
            "callback_errors": 0,
            "redis_connected": False,
        }

    async def init(self) -> None:
        """Initialize the event bus, optionally connecting to Redis."""
        try:
            from .cache import REDIS_AVAILABLE, get_cache

            if REDIS_AVAILABLE:
                cache = await get_cache()
                if hasattr(cache, "_redis") and cache._redis:
                    self._redis = cache._redis
                    self._pubsub = cache._redis.pubsub()
                    self.stats["redis_connected"] = True
                    logger.info("✅ EventBus connected to Redis Pub/Sub")
        except Exception as e:
            logger.warning(f"⚠️ EventBus Redis connection failed, using local-only mode: {e}")

    async def start(self) -> None:
        """Start the event bus listener."""
        if self._redis and self._pubsub:
            self._listener_task = asyncio.create_task(self._redis_listener())
            logger.info("🚀 EventBus Redis listener started")

    async def stop(self) -> None:
        """Stop the event bus."""
        self._shutdown_event.set()

        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        if self._pubsub:
            await self._pubsub.close()

        logger.info("🛑 EventBus stopped")

    def subscribe(self, event_type: str, callback: EventCallback) -> None:
        """Subscribe to an event type."""
        self._subscribers[event_type].append(callback)
        logger.debug(f"📩 Subscribed to {event_type}: {callback.__qualname__}")

        # Also subscribe to Redis channel if connected
        if self._redis and self._pubsub:
            asyncio.create_task(self._pubsub.subscribe(event_type))

    def unsubscribe(self, event_type: str, callback: EventCallback) -> bool:
        """Unsubscribe from an event type."""
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(callback)
                return True
            except ValueError:
                return False
        return False

    async def publish(self, event: Event) -> None:
        """Publish an event to all subscribers."""
        self.stats["events_published"] += 1

        # Add to history
        self._history.append(event)
        if len(self._history) > self._history_limit:
            self._history = self._history[-self._history_limit :]

        # Publish to Redis if connected
        if self._redis:
            try:
                await self._redis.publish(event.event_type, json.dumps(event.to_dict()))
            except Exception as e:
                logger.debug(f"Redis publish failed: {e}")

        # Local delivery
        await self._deliver_event(event)

    async def _deliver_event(self, event: Event) -> None:
        """Deliver event to local subscribers."""
        self.stats["events_received"] += 1

        callbacks = self._subscribers.get(event.event_type, [])
        callbacks += self._subscribers.get("*", [])  # Wildcard subscribers

        for callback in callbacks:
            try:
                self.stats["callbacks_executed"] += 1
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                self.stats["callback_errors"] += 1
                logger.error(f"❌ EventBus callback error for {event.event_type}: {e}")

    async def _redis_listener(self) -> None:
        """Listen for Redis Pub/Sub messages."""
        if not self._pubsub:
            return

        try:
            async for message in self._pubsub.listen():
                if self._shutdown_event.is_set():
                    break

                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        event = Event.from_dict(data)

                        # Don't re-deliver events from this instance
                        if event.source != self.instance_id:
                            await self._deliver_event(event)
                    except Exception as e:
                        logger.debug(f"Failed to process Redis message: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"❌ Redis listener error: {e}")

    def get_history(
        self, event_type: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent event history."""
        events = self._history

        if event_type:
            events = [e for e in events if e.event_type == event_type]

        return [e.to_dict() for e in events[-limit:]]

    def get_stats(self) -> Dict[str, Any]:
        """Get event bus statistics."""
        return {
            **self.stats,
            "instance_id": self.instance_id,
            "subscriber_count": sum(len(cbs) for cbs in self._subscribers.values()),
            "history_size": len(self._history),
        }


# Global event bus instance
_event_bus: Optional[EventBus] = None


async def get_event_bus() -> EventBus:
    """Get or create the global event bus instance."""
    global _event_bus

    if _event_bus is None:
        import uuid

        _event_bus = EventBus(instance_id=str(uuid.uuid4())[:8])
        await _event_bus.init()
        await _event_bus.start()

    return _event_bus


async def close_event_bus() -> None:
    """Close the global event bus."""
    global _event_bus

    if _event_bus:
        await _event_bus.stop()
        _event_bus = None


# Convenience functions for common events
async def emit_trade_executed(
    symbol: str, side: str, quantity: float, platform: str, order_id: Optional[str] = None, **extra
) -> None:
    """Emit a trade executed event."""
    bus = await get_event_bus()
    await bus.publish(
        Event(
            event_type=EventTypes.TRADE_EXECUTED,
            data={
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "platform": platform,
                "order_id": order_id,
                **extra,
            },
            source="platform_router",
        )
    )


async def emit_platform_health_changed(
    platform: str,
    is_healthy: bool,
    consecutive_failures: int = 0,
    error_message: Optional[str] = None,
) -> None:
    """Emit a platform health changed event."""
    bus = await get_event_bus()
    await bus.publish(
        Event(
            event_type=EventTypes.PLATFORM_HEALTH_CHANGED,
            data={
                "platform": platform,
                "is_healthy": is_healthy,
                "consecutive_failures": consecutive_failures,
                "error_message": error_message,
            },
            source="platform_router",
        )
    )


async def emit_system_alert(level: str, message: str, component: str, **extra) -> None:
    """Emit a system alert event."""
    bus = await get_event_bus()
    await bus.publish(
        Event(
            event_type=EventTypes.SYSTEM_ALERT,
            data={"level": level, "message": message, "component": component, **extra},
            source="system",
        )
    )
