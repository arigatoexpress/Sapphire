"""WebSocket manager for real-time frontend updates."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import structlog
from fastapi import WebSocket, WebSocketDisconnect

from .time_sync import get_timestamp_us

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Types of WebSocket messages."""

    TRADE_UPDATE = "trade_update"
    AGENT_STATUS = "agent_status"
    CONSENSUS_DECISION = "consensus_decision"
    PORTFOLIO_UPDATE = "portfolio_update"
    MARKET_DATA = "market_data"
    PERFORMANCE_METRICS = "performance_metrics"
    SYSTEM_HEALTH = "system_health"
    MEMORY_UPDATE = "memory_update"
    ALERT = "alert"
    MARKET_REGIME = "market_regime"
    PLATFORM_ROUTER_STATUS = "platform_router_status"  # NEW: Real-time platform router updates


class SubscriptionType(Enum):
    """Types of subscriptions clients can make."""

    ALL_TRADES = "all_trades"
    AGENT_UPDATES = "agent_updates"
    CONSENSUS_VOTES = "consensus_votes"
    PORTFOLIO_CHANGES = "portfolio_changes"
    MARKET_FEED = "market_feed"
    PERFORMANCE_STATS = "performance_stats"
    SYSTEM_ALERTS = "system_alerts"
    AGENT_MEMORY = "agent_memory"
    MARKET_REGIME = "market_regime"
    PLATFORM_ROUTER = "platform_router"  # NEW: Platform router health/metrics updates


@dataclass
class WebSocketClient:
    """A connected WebSocket client."""

    websocket: WebSocket
    client_id: str
    subscriptions: Set[SubscriptionType] = field(default_factory=set)
    connected_at: int = field(default_factory=get_timestamp_us)
    last_activity: int = field(default_factory=get_timestamp_us)
    metadata: Dict[str, Any] = field(default_factory=dict)

    async def send_message(self, message_type: MessageType, data: Dict[str, Any]) -> bool:
        """Send a message to this client."""
        try:
            message = {"type": message_type.value, "timestamp_us": get_timestamp_us(), "data": data}
            await self.websocket.send_json(message)
            self.last_activity = get_timestamp_us()
            return True
        except Exception as e:
            logger.error(f"Failed to send message to client {self.client_id}: {e}")
            return False

    async def ping(self) -> bool:
        """Send a ping to check if client is still connected."""
        try:
            await self.websocket.send_json({"type": "ping", "timestamp_us": get_timestamp_us()})
            self.last_activity = get_timestamp_us()
            return True
        except Exception:
            return False


@dataclass
class WebSocketMessage:
    """A message to be broadcast to subscribers."""

    message_type: MessageType
    subscription_type: SubscriptionType
    data: Dict[str, Any]
    priority: int = 1  # 1=low, 2=normal, 3=high, 4=critical
    target_clients: Optional[Set[str]] = None  # Specific clients, None = all subscribers
    created_at: int = field(default_factory=get_timestamp_us)


class WebSocketManager:
    """
    Advanced WebSocket manager for real-time updates.

    Features:
    - Subscription-based messaging
    - Client connection management
    - Message prioritization and queuing
    - Heartbeat monitoring
    - Performance metrics
    """

    def __init__(self):
        self.clients: Dict[str, WebSocketClient] = {}
        self.subscriptions: Dict[SubscriptionType, Set[str]] = defaultdict(
            set
        )  # subscription_type -> client_ids

        # Message queues by priority
        self.message_queues: Dict[int, asyncio.Queue] = {
            1: asyncio.Queue(maxsize=1000),  # Low
            2: asyncio.Queue(maxsize=1000),  # Normal
            3: asyncio.Queue(maxsize=1000),  # High
            4: asyncio.Queue(maxsize=1000),  # Critical
        }

        # Background tasks
        self._broadcast_task: Optional[asyncio.Task[None]] = None
        self._heartbeat_task: Optional[asyncio.Task[None]] = None
        self._cleanup_task: Optional[asyncio.Task[None]] = None

        # Statistics
        self.stats = {
            "total_clients": 0,
            "active_clients": 0,
            "messages_sent": 0,
            "messages_failed": 0,
            "bytes_sent": 0,
            "uptime_seconds": 0,
        }

        # Callbacks for different message types
        self.message_callbacks: Dict[MessageType, List[Callable[[WebSocketMessage], None]]] = (
            defaultdict(list)
        )

        # Shutdown event
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start the WebSocket manager."""
        if self._broadcast_task and not self._broadcast_task.done():
            return

        self._shutdown_event.clear()
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        logger.info("WebSocket manager started")

    async def stop(self) -> None:
        """Stop the WebSocket manager."""
        self._shutdown_event.set()

        # Disconnect all clients
        disconnect_tasks = []
        for client in list(self.clients.values()):
            disconnect_tasks.append(self._disconnect_client(client.client_id, "server_shutdown"))

        if disconnect_tasks:
            await asyncio.gather(*disconnect_tasks, return_exceptions=True)

        # Wait for background tasks
        tasks_to_wait = []
        if self._broadcast_task:
            tasks_to_wait.append(self._broadcast_task)
        if self._heartbeat_task:
            tasks_to_wait.append(self._heartbeat_task)
        if self._cleanup_task:
            tasks_to_wait.append(self._cleanup_task)

        if tasks_to_wait:
            await asyncio.gather(*tasks_to_wait, return_exceptions=True)

        logger.info("WebSocket manager stopped")

    async def add_client(
        self, websocket: WebSocket, client_id: str, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Add a new WebSocket client."""
        try:
            await websocket.accept()

            client = WebSocketClient(
                websocket=websocket, client_id=client_id, metadata=metadata or {}
            )

            self.clients[client_id] = client
            self.stats["total_clients"] += 1
            self.stats["active_clients"] += 1

            # Send welcome message
            await client.send_message(
                MessageType.SYSTEM_HEALTH,
                {
                    "message": "Connected to Sapphire Trading WebSocket",
                    "client_id": client_id,
                    "server_time_us": get_timestamp_us(),
                },
            )

            logger.info(f"WebSocket client connected: {client_id}")
            return client_id

        except Exception as e:
            logger.error(f"Failed to add WebSocket client {client_id}: {e}")
            raise

    async def remove_client(self, client_id: str, reason: str = "unknown") -> None:
        """Remove a WebSocket client."""
        await self._disconnect_client(client_id, reason)

    async def _disconnect_client(self, client_id: str, reason: str) -> None:
        """Disconnect a client."""
        if client_id not in self.clients:
            return

        client = self.clients[client_id]

        # Remove from subscriptions
        for subscription_type in list(client.subscriptions):
            self.subscriptions[subscription_type].discard(client_id)

        # Close WebSocket
        try:
            await client.websocket.close(code=1000, reason=reason)
        except Exception as e:
            logger.debug(f"Error closing WebSocket for client {client_id}: {e}")

        # Remove client
        del self.clients[client_id]
        self.stats["active_clients"] -= 1

        logger.info(f"WebSocket client disconnected: {client_id} (reason: {reason})")

    async def subscribe_client(self, client_id: str, subscription_type: SubscriptionType) -> bool:
        """Subscribe a client to a message type."""
        if client_id not in self.clients:
            return False

        client = self.clients[client_id]
        client.subscriptions.add(subscription_type)
        self.subscriptions[subscription_type].add(client_id)

        logger.debug(f"Client {client_id} subscribed to {subscription_type.value}")
        return True

    async def unsubscribe_client(self, client_id: str, subscription_type: SubscriptionType) -> bool:
        """Unsubscribe a client from a message type."""
        if client_id not in self.clients:
            return False

        client = self.clients[client_id]
        client.subscriptions.discard(subscription_type)
        self.subscriptions[subscription_type].discard(client_id)

        logger.debug(f"Client {client_id} unsubscribed from {subscription_type.value}")
        return True

    async def broadcast_message(self, message: WebSocketMessage) -> None:
        """Broadcast a message to subscribed clients."""
        try:
            # Add to appropriate priority queue
            await self.message_queues[message.priority].put(message)
        except asyncio.QueueFull:
            logger.warning(f"Message queue full for priority {message.priority}, dropping message")

    async def send_to_client(
        self, client_id: str, message_type: MessageType, data: Dict[str, Any]
    ) -> bool:
        """Send a message to a specific client."""
        if client_id not in self.clients:
            return False

        client = self.clients[client_id]
        return await client.send_message(message_type, data)

    def add_message_callback(
        self, message_type: MessageType, callback: Callable[[WebSocketMessage], None]
    ) -> None:
        """Add a callback for a specific message type."""
        self.message_callbacks[message_type].append(callback)

    async def _broadcast_loop(self) -> None:
        """Main broadcast loop processing messages from all priority queues."""
        while not self._shutdown_event.is_set():
            try:
                # Process messages in priority order (highest first)
                message = None

                for priority in range(4, 0, -1):  # 4, 3, 2, 1
                    try:
                        message = self.message_queues[priority].get_nowait()
                        self.message_queues[priority].task_done()
                        break
                    except asyncio.QueueEmpty:
                        continue

                if message:
                    await self._process_message(message)

                # Small delay to prevent busy waiting
                await asyncio.sleep(0.01)

            except Exception as e:
                logger.error(f"Error in broadcast loop: {e}")

    async def _process_message(self, message: WebSocketMessage) -> None:
        """Process a single message."""
        # Call callbacks
        for callback in self.message_callbacks[message.message_type]:
            try:
                callback(message)
            except Exception as e:
                logger.error(f"Error in message callback for {message.message_type.value}: {e}")

        # Determine target clients
        if message.target_clients:
            target_client_ids = message.target_clients
        else:
            target_client_ids = self.subscriptions[message.subscription_type]

        if not target_client_ids:
            return  # No subscribers

        # Send to all target clients
        send_tasks = []
        for client_id in target_client_ids:
            if client_id in self.clients:
                client = self.clients[client_id]
                send_tasks.append(client.send_message(message.message_type, message.data))

        if send_tasks:
            results = await asyncio.gather(*send_tasks, return_exceptions=True)

            success_count = sum(1 for r in results if r is True)
            self.stats["messages_sent"] += success_count
            self.stats["messages_failed"] += len(results) - success_count

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats to clients."""
        while not self._shutdown_event.is_set():
            try:
                # Ping all clients
                ping_tasks = []
                for client in list(self.clients.values()):
                    ping_tasks.append(client.ping())

                if ping_tasks:
                    results = await asyncio.gather(*ping_tasks, return_exceptions=True)

                    # Disconnect unresponsive clients
                    disconnected = []
                    for i, result in enumerate(results):
                        if isinstance(result, Exception) or result is False:
                            client_id = list(self.clients.keys())[i]
                            disconnected.append(client_id)

                    for client_id in disconnected:
                        await self._disconnect_client(client_id, "ping_timeout")

                # Wait 30 seconds between heartbeats
                await asyncio.sleep(30)

            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")

    async def _cleanup_loop(self) -> None:
        """Periodic cleanup of stale connections."""
        while not self._shutdown_event.is_set():
            try:
                current_time = get_timestamp_us()
                stale_threshold = 5 * 60 * 1_000_000  # 5 minutes

                # Find stale clients
                stale_clients = []
                for client_id, client in list(self.clients.items()):
                    if (current_time - client.last_activity) > stale_threshold:
                        stale_clients.append(client_id)

                # Disconnect stale clients
                for client_id in stale_clients:
                    await self._disconnect_client(client_id, "inactivity_timeout")

                # Update uptime
                self.stats["uptime_seconds"] += 60

                # Wait 1 minute between cleanup cycles
                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get WebSocket manager statistics."""
        subscription_counts = {
            sub.value: len(clients) for sub, clients in self.subscriptions.items()
        }

        return {
            "stats": self.stats.copy(),
            "active_clients": len(self.clients),
            "subscription_counts": subscription_counts,
            "queue_sizes": {f"priority_{p}": q.qsize() for p, q in self.message_queues.items()},
            "timestamp_us": get_timestamp_us(),
        }


# Global WebSocket manager instance
_websocket_manager: Optional[WebSocketManager] = None


async def get_websocket_manager() -> WebSocketManager:
    """Get global WebSocket manager instance."""
    global _websocket_manager
    if _websocket_manager is None:
        _websocket_manager = WebSocketManager()
        await _websocket_manager.start()
    return _websocket_manager


# Utility functions for common message types


async def broadcast_trade_update(trade_data: Dict[str, Any], priority: int = 2) -> None:
    """Broadcast a trade update to subscribed clients."""
    manager = await get_websocket_manager()
    message = WebSocketMessage(
        message_type=MessageType.TRADE_UPDATE,
        subscription_type=SubscriptionType.ALL_TRADES,
        data=trade_data,
        priority=priority,
    )
    await manager.broadcast_message(message)


async def broadcast_agent_status(agent_id: str, status_data: Dict[str, Any]) -> None:
    """Broadcast agent status update."""
    manager = await get_websocket_manager()
    message = WebSocketMessage(
        message_type=MessageType.AGENT_STATUS,
        subscription_type=SubscriptionType.AGENT_UPDATES,
        data={"agent_id": agent_id, **status_data},
        priority=2,
    )
    await manager.broadcast_message(message)


async def broadcast_consensus_decision(decision_data: Dict[str, Any]) -> None:
    """Broadcast consensus decision."""
    manager = await get_websocket_manager()
    message = WebSocketMessage(
        message_type=MessageType.CONSENSUS_DECISION,
        subscription_type=SubscriptionType.CONSENSUS_VOTES,
        data=decision_data,
        priority=3,  # High priority for consensus decisions
    )
    await manager.broadcast_message(message)


async def broadcast_portfolio_update(portfolio_data: Dict[str, Any]) -> None:
    """Broadcast portfolio update."""
    manager = await get_websocket_manager()
    message = WebSocketMessage(
        message_type=MessageType.PORTFOLIO_UPDATE,
        subscription_type=SubscriptionType.PORTFOLIO_CHANGES,
        data=portfolio_data,
        priority=2,
    )
    await manager.broadcast_message(message)


async def broadcast_system_alert(alert_data: Dict[str, Any], priority: int = 4) -> None:
    """Broadcast system alert (high priority)."""
    manager = await get_websocket_manager()
    message = WebSocketMessage(
        message_type=MessageType.ALERT,
        subscription_type=SubscriptionType.SYSTEM_ALERTS,
        data=alert_data,
        priority=priority,
    )
    await manager.broadcast_message(message)


async def broadcast_market_regime(regime_data: Dict[str, Any]) -> None:
    """Broadcast market regime update."""
    try:
        print(f"📡 Broadcasting Market Regime: {regime_data.get('regime', 'UNKNOWN')}")
        manager = await get_websocket_manager()
        message = WebSocketMessage(
            message_type=MessageType.MARKET_REGIME,
            subscription_type=SubscriptionType.MARKET_REGIME,
            data=regime_data,
            priority=2,
        )
        await manager.broadcast_message(message)
        print("✅ Market Regime broadcasted successfully")
    except Exception as e:
        print(f"❌ Failed to broadcast market regime: {e}")


async def broadcast_platform_router_status(status_data: Dict[str, Any]) -> None:
    """Broadcast platform router status update (health, metrics, circuit breaker)."""
    try:
        manager = await get_websocket_manager()
        message = WebSocketMessage(
            message_type=MessageType.PLATFORM_ROUTER_STATUS,
            subscription_type=SubscriptionType.PLATFORM_ROUTER,
            data=status_data,
            priority=3,  # High priority for platform health updates
        )
        await manager.broadcast_message(message)
    except Exception as e:
        print(f"❌ Failed to broadcast platform router status: {e}")
