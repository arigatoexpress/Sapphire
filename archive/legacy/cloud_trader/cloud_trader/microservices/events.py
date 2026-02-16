"""Event publishing and aggregation for microservices architecture.

This module provides:
1. ServiceEvent - standardized event schema
2. ServiceEventPublisher - publishes events to PubSub
3. ServiceStateAggregator - subscribes and aggregates state from all services
"""

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from google.cloud import firestore, pubsub_v1

from .identity import ServiceIdentity, get_service_identity

logger = logging.getLogger(__name__)


class ServiceEventType(str, Enum):
    """Types of events published by microservices."""

    # Lifecycle events
    HEARTBEAT = "heartbeat"
    SERVICE_STARTED = "service_started"
    SERVICE_STOPPED = "service_stopped"
    SERVICE_ERROR = "service_error"

    # Trading events
    BALANCE_UPDATE = "balance_update"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    POSITION_UPDATED = "position_updated"
    TRADE_EXECUTED = "trade_executed"
    ORDER_PLACED = "order_placed"
    ORDER_CANCELLED = "order_cancelled"

    # Risk events
    RISK_LIMIT_BREACHED = "risk_limit_breached"
    CIRCUIT_BREAKER_TRIGGERED = "circuit_breaker_triggered"

    # Agent events
    AGENT_DECISION = "agent_decision"
    CONSENSUS_REACHED = "consensus_reached"


@dataclass
class ServiceEvent:
    """Standardized event emitted by microservices.

    All services publish events in this format for aggregation.
    """

    event_type: ServiceEventType
    service_name: str
    service_type: str
    timestamp: float
    region: str

    # Event payload (platform-specific data)
    payload: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    event_id: Optional[str] = None
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "event_type": self.event_type.value,
            "service_name": self.service_name,
            "service_type": self.service_type,
            "timestamp": self.timestamp,
            "region": self.region,
            "payload": self.payload,
            "event_id": self.event_id,
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServiceEvent":
        """Create from dictionary."""
        return cls(
            event_type=ServiceEventType(data["event_type"]),
            service_name=data["service_name"],
            service_type=data["service_type"],
            timestamp=data["timestamp"],
            region=data["region"],
            payload=data.get("payload", {}),
            event_id=data.get("event_id"),
            correlation_id=data.get("correlation_id"),
        )


class ServiceEventPublisher:
    """Publishes service events to Google Cloud PubSub.

    Each trading service publishes:
    - Heartbeats (every 30s)
    - Balance updates (on change)
    - Trade events (on execution)
    - Position updates (on change)
    """

    def __init__(
        self,
        project_id: str,
        topic_name: str = "sapphire-service-events",
        enable_pubsub: bool = True,
    ):
        """Initialize publisher.

        Args:
            project_id: GCP project ID
            topic_name: PubSub topic name
            enable_pubsub: If False, events are logged but not published (dev mode)
        """
        self.project_id = project_id
        self.topic_name = topic_name
        self.enable_pubsub = enable_pubsub
        self.identity = get_service_identity()

        self._publisher: Optional[pubsub_v1.PublisherClient] = None
        self._topic_path: Optional[str] = None
        self._publish_count = 0
        self._last_heartbeat = 0.0

        if self.enable_pubsub:
            try:
                self._publisher = pubsub_v1.PublisherClient()
                self._topic_path = self._publisher.topic_path(project_id, topic_name)
                logger.info(f"✅ Event publisher initialized: {self._topic_path}")
            except Exception as e:
                logger.error(f"❌ Failed to initialize PubSub publisher: {e}")
                self.enable_pubsub = False
        else:
            logger.info("📝 Event publisher in LOG-ONLY mode (PubSub disabled)")

    async def publish_event(
        self,
        event_type: ServiceEventType,
        payload: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> None:
        """Publish an event to PubSub.

        Args:
            event_type: Type of event
            payload: Event-specific data
            correlation_id: Optional correlation ID for tracing
        """
        event = ServiceEvent(
            event_type=event_type,
            service_name=self.identity.service_name,
            service_type=self.identity.service_type.value,
            timestamp=time.time(),
            region=self.identity.region,
            payload=payload,
            event_id=f"{self.identity.service_name}-{int(time.time()*1000)}",
            correlation_id=correlation_id,
        )

        if not self.enable_pubsub:
            logger.debug(f"📝 [EVENT] {event_type.value}: {payload}")
            return

        try:
            # Publish to PubSub
            message_data = json.dumps(event.to_dict()).encode("utf-8")
            future = self._publisher.publish(self._topic_path, message_data)

            # Don't await - fire and forget for performance
            # future.result(timeout=1.0)  # Commented out for async publish

            self._publish_count += 1

            if self._publish_count % 100 == 0:
                logger.info(
                    f"📡 Published {self._publish_count} events from {self.identity.service_name}"
                )

        except Exception as e:
            logger.error(f"❌ Failed to publish event {event_type.value}: {e}")

    async def publish_heartbeat(self, stats: Optional[Dict[str, Any]] = None) -> None:
        """Publish a heartbeat event with service health stats."""
        now = time.time()

        # Rate limit: only publish heartbeat every 30 seconds
        if now - self._last_heartbeat < 30.0:
            return

        self._last_heartbeat = now

        await self.publish_event(
            ServiceEventType.HEARTBEAT,
            payload={
                "status": "healthy",
                "stats": stats or {},
                "uptime_seconds": now - (stats or {}).get("start_time", now),
            },
        )

    async def publish_balance_update(
        self,
        platform: str,
        balance: float,
        equity: Optional[float] = None,
        available_margin: Optional[float] = None,
    ) -> None:
        """Publish balance update event."""
        await self.publish_event(
            ServiceEventType.BALANCE_UPDATE,
            payload={
                "platform": platform,
                "balance": balance,
                "equity": equity,
                "available_margin": available_margin,
            },
        )

    async def publish_trade_executed(
        self,
        symbol: str,
        side: str,
        size: float,
        price: float,
        realized_pnl: Optional[float] = None,
    ) -> None:
        """Publish trade execution event."""
        await self.publish_event(
            ServiceEventType.TRADE_EXECUTED,
            payload={
                "symbol": symbol,
                "side": side,
                "size": size,
                "price": price,
                "realized_pnl": realized_pnl,
            },
        )

    async def publish_position_update(
        self,
        symbol: str,
        size: float,
        entry_price: float,
        unrealized_pnl: Optional[float] = None,
        leverage: Optional[float] = None,
    ) -> None:
        """Publish position update event."""
        event_type = (
            ServiceEventType.POSITION_OPENED
            if size != 0
            else ServiceEventType.POSITION_CLOSED
        )

        await self.publish_event(
            event_type,
            payload={
                "symbol": symbol,
                "size": size,
                "entry_price": entry_price,
                "unrealized_pnl": unrealized_pnl,
                "leverage": leverage,
            },
        )

    async def close(self):
        """Cleanup publisher resources."""
        if self._publisher:
            # PubSub publisher doesn't need explicit cleanup in v2
            pass


class ServiceStateAggregator:
    """Aggregates state from all microservices.

    This runs in sapphire-web to:
    1. Subscribe to PubSub events from all trading services
    2. Maintain in-memory shadow state of the fleet
    3. Provide unified API for the dashboard

    State is also persisted to Firestore for:
    - Cross-instance consistency
    - Historical queries
    - Crash recovery
    """

    def __init__(
        self,
        project_id: str,
        subscription_name: str = "sapphire-web-events",
        topic_name: str = "sapphire-service-events",
        enable_firestore: bool = True,
    ):
        """Initialize aggregator.

        Args:
            project_id: GCP project ID
            subscription_name: PubSub subscription name
            topic_name: PubSub topic name
            enable_firestore: Enable Firestore persistence
        """
        self.project_id = project_id
        self.subscription_name = subscription_name
        self.topic_name = topic_name
        self.enable_firestore = enable_firestore

        # In-memory shadow state
        self._service_states: Dict[str, Dict[str, Any]] = {}
        self._balances: Dict[str, float] = {}  # service_name -> balance
        self._positions: Dict[str, List[Dict[str, Any]]] = {}  # service_name -> positions
        self._last_heartbeat: Dict[str, float] = {}  # service_name -> timestamp
        self._events: List[ServiceEvent] = []  # Recent events (rolling window)

        # Firestore client
        self._firestore_client: Optional[firestore.Client] = None
        if self.enable_firestore:
            try:
                self._firestore_client = firestore.Client(project=project_id)
                logger.info("✅ Firestore client initialized for state persistence")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Firestore: {e}")
                self.enable_firestore = False

        # PubSub subscriber
        self._subscriber: Optional[pubsub_v1.SubscriberClient] = None
        self._subscription_path: Optional[str] = None
        self._streaming_pull_future = None

        # Callbacks for real-time updates
        self._event_callbacks: List[Callable[[ServiceEvent], None]] = []

    async def start(self):
        """Start subscribing to PubSub events."""
        try:
            self._subscriber = pubsub_v1.SubscriberClient()
            self._subscription_path = self._subscriber.subscription_path(
                self.project_id, self.subscription_name
            )

            # Start background task for pulling messages
            asyncio.create_task(self._pull_messages())

            logger.info(f"✅ Aggregator subscribed to: {self._subscription_path}")

        except Exception as e:
            logger.error(f"❌ Failed to start aggregator: {e}")

    async def _pull_messages(self):
        """Background task to pull and process PubSub messages."""
        if not self._subscriber or not self._subscription_path:
            return

        def callback(message: pubsub_v1.subscriber.message.Message):
            try:
                # Parse event
                data = json.loads(message.data.decode("utf-8"))
                event = ServiceEvent.from_dict(data)

                # Process event
                asyncio.create_task(self._process_event(event))

                # Acknowledge
                message.ack()

            except Exception as e:
                logger.error(f"❌ Failed to process message: {e}")
                message.nack()

        # Start streaming pull
        self._streaming_pull_future = self._subscriber.subscribe(
            self._subscription_path, callback=callback
        )

        logger.info("🔄 Started streaming pull from PubSub")

        try:
            # Keep alive
            await asyncio.Future()  # Run forever
        except Exception as e:
            logger.error(f"❌ Streaming pull error: {e}")
            if self._streaming_pull_future:
                self._streaming_pull_future.cancel()

    async def _process_event(self, event: ServiceEvent):
        """Process an incoming event and update shadow state."""
        service_name = event.service_name

        # Update heartbeat
        if event.event_type == ServiceEventType.HEARTBEAT:
            self._last_heartbeat[service_name] = event.timestamp
            self._service_states[service_name] = event.payload.get("stats", {})

        # Update balance
        elif event.event_type == ServiceEventType.BALANCE_UPDATE:
            balance = event.payload.get("balance", 0.0)
            self._balances[service_name] = balance

            # Persist to Firestore
            if self.enable_firestore:
                await self._persist_balance(service_name, event.payload)

        # Update positions
        elif event.event_type in [
            ServiceEventType.POSITION_OPENED,
            ServiceEventType.POSITION_UPDATED,
        ]:
            if service_name not in self._positions:
                self._positions[service_name] = []

            # Find or create position
            symbol = event.payload.get("symbol")
            position = next(
                (p for p in self._positions[service_name] if p.get("symbol") == symbol),
                None,
            )

            if position:
                position.update(event.payload)
            else:
                self._positions[service_name].append(event.payload)

        elif event.event_type == ServiceEventType.POSITION_CLOSED:
            symbol = event.payload.get("symbol")
            if service_name in self._positions:
                self._positions[service_name] = [
                    p for p in self._positions[service_name] if p.get("symbol") != symbol
                ]

        # Store recent events (last 1000)
        self._events.append(event)
        if len(self._events) > 1000:
            self._events.pop(0)

        # Trigger callbacks
        for callback in self._event_callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"❌ Event callback error: {e}")

    async def _persist_balance(self, service_name: str, balance_data: Dict[str, Any]):
        """Persist balance to Firestore for durability."""
        if not self._firestore_client:
            return

        try:
            doc_ref = self._firestore_client.collection("service_balances").document(
                service_name
            )
            await asyncio.get_event_loop().run_in_executor(
                None,
                doc_ref.set,
                {
                    **balance_data,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
            )
        except Exception as e:
            logger.error(f"❌ Failed to persist balance to Firestore: {e}")

    def get_total_equity(self) -> float:
        """Get total equity across all services."""
        return sum(self._balances.values())

    def get_all_positions(self) -> List[Dict[str, Any]]:
        """Get all positions across all services."""
        all_positions = []
        for service_name, positions in self._positions.items():
            for position in positions:
                all_positions.append({**position, "service": service_name})
        return all_positions

    def get_service_health(self) -> Dict[str, Any]:
        """Get health status of all services."""
        now = time.time()
        health = {}

        for service_name, last_beat in self._last_heartbeat.items():
            age = now - last_beat
            health[service_name] = {
                "status": "healthy" if age < 60 else "stale" if age < 300 else "down",
                "last_heartbeat": last_beat,
                "age_seconds": age,
            }

        return health

    def get_fleet_summary(self) -> Dict[str, Any]:
        """Get summary of the entire fleet."""
        return {
            "total_equity": self.get_total_equity(),
            "total_positions": len(self.get_all_positions()),
            "services": {
                service: {
                    "balance": self._balances.get(service, 0.0),
                    "positions": len(self._positions.get(service, [])),
                    "health": self.get_service_health().get(service, {}),
                }
                for service in set(
                    list(self._balances.keys())
                    + list(self._positions.keys())
                    + list(self._last_heartbeat.keys())
                )
            },
            "timestamp": time.time(),
        }

    def register_event_callback(self, callback: Callable[[ServiceEvent], None]):
        """Register a callback for real-time event notifications."""
        self._event_callbacks.append(callback)

    async def close(self):
        """Cleanup resources."""
        if self._streaming_pull_future:
            self._streaming_pull_future.cancel()

        if self._subscriber:
            await asyncio.get_event_loop().run_in_executor(None, self._subscriber.close)
