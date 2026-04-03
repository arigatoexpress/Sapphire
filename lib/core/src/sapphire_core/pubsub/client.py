"""
Pub/Sub Helper for Sapphire Trading Platform

Provides a unified interface for publishing and subscribing to events
across all bot services using GCP Pub/Sub.
"""

import asyncio
import json
import logging
import os
from collections.abc import Callable
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

try:
    from google.cloud import pubsub_v1
except ImportError:
    pubsub_v1 = None

logger = logging.getLogger(__name__)

# Check if we're using emulator (for local development)
PUBSUB_EMULATOR_HOST = os.getenv("PUBSUB_EMULATOR_HOST")

# GCP Project ID
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "sapphire-479610")
SUBSCRIPTION_ACK_DEADLINE_SECONDS = max(
    10,
    min(int(os.getenv("PUBSUB_SUB_ACK_DEADLINE_SECONDS", "60")), 600),
)
PUBLISH_RESULT_TIMEOUT_SECONDS = max(
    5.0, float(os.getenv("PUBSUB_PUBLISH_RESULT_TIMEOUT_SECONDS", "20"))
)
FIRE_AND_FORGET_TOPICS = {"position-updates", "balance-updates"}


def _resolve_runtime_service_name() -> str:
    """
    Resolve a stable runtime service name for subscription fanout isolation.

    Priority:
      1) explicit SERVICE_NAME env
      2) Cloud Run K_SERVICE
      3) local HOSTNAME fallback
    """
    candidates = [
        os.getenv("SERVICE_NAME"),
        os.getenv("K_SERVICE"),
        os.getenv("HOSTNAME"),
    ]
    for candidate in candidates:
        if candidate:
            value = str(candidate).strip()
            if value:
                return value
    return "unknown"


class PubSubClient:
    """
    Unified Pub/Sub client for inter-service communication.

    Supports both GCP Pub/Sub (production) and emulator (local dev).
    """

    # Topic definitions
    TOPICS = {
        "trading-signals": f"projects/{PROJECT_ID}/topics/trading-signals",
        "trade-executed": f"projects/{PROJECT_ID}/topics/trade-executed",
        "position-updates": f"projects/{PROJECT_ID}/topics/position-updates",
        "balance-updates": f"projects/{PROJECT_ID}/topics/balance-updates",
        "risk-alerts": f"projects/{PROJECT_ID}/topics/risk-alerts",
    }

    def __init__(self):
        self._publisher = None
        self._subscriber = None
        self._subscriptions: dict[str, Any] = {}
        self._handlers: dict[str, list[Callable]] = {}
        self._pull_tasks: list[asyncio.Task] = []
        self._closing = False
        self._initialized = False

    async def initialize(self):
        """Initialize Pub/Sub clients."""
        if self._initialized:
            return

        try:
            # Create clients in the background
            loop = asyncio.get_event_loop()
            self._publisher = await loop.run_in_executor(None, pubsub_v1.PublisherClient)
            self._subscriber = await loop.run_in_executor(None, pubsub_v1.SubscriberClient)
            self._initialized = True
            self._closing = False

            logger.info("✅ Pub/Sub client initialized (non-blocking)")

            if PUBSUB_EMULATOR_HOST:
                logger.info(f"🔧 Using Pub/Sub emulator at {PUBSUB_EMULATOR_HOST}")

        except ImportError:
            logger.warning("⚠️ google-cloud-pubsub not installed, using mock mode")
            self._initialized = True
        except Exception as e:
            logger.error(f"❌ Failed to initialize Pub/Sub: {e}")
            # Continue without Pub/Sub for resilience
            self._initialized = True

    async def publish(self, topic: str, message: Any) -> str | None:
        """
        Publish a message to a topic.

        Args:
            topic: Topic name (e.g., "trading-signals")
            message: Message data (dict, dataclass, or JSON-serializable object)

        Returns:
            Message ID if successful, None otherwise
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Serialize message
            if is_dataclass(message):
                data = asdict(message)
            elif isinstance(message, dict):
                data = message
            else:
                data = {"value": message}

            # Handle datetime serialization
            data = self._serialize_datetimes(data)

            # Convert to JSON bytes
            message_bytes = json.dumps(data).encode("utf-8")

            # Get full topic path
            topic_path = self.TOPICS.get(topic, f"projects/{PROJECT_ID}/topics/{topic}")

            if self._publisher:
                # Publish to GCP Pub/Sub in thread
                future = await asyncio.to_thread(self._publisher.publish, topic_path, message_bytes)
                if topic in FIRE_AND_FORGET_TOPICS:
                    # High-frequency telemetry should never block critical loops
                    # (or shutdown) while waiting for broker acknowledgement.
                    logger.debug("📤 Queued telemetry publish to %s", topic)
                    return None
                try:
                    message_id = await asyncio.to_thread(
                        future.result,
                        timeout=PUBLISH_RESULT_TIMEOUT_SECONDS,
                    )
                    logger.debug(f"📤 Published to {topic}: {message_id}")
                    return message_id
                except FuturesTimeoutError:
                    # Timeout waiting for publish acknowledgement is not always a
                    # delivery failure; under CPU/network pressure the future can
                    # still complete shortly after. We keep this non-fatal.
                    logger.warning(
                        "⚠️ Publish ack timeout on %s after %.1fs (message may still publish)",
                        topic,
                        PUBLISH_RESULT_TIMEOUT_SECONDS,
                    )
                    return None
            else:
                # Mock mode - just log
                logger.info(f"📤 [MOCK] Would publish to {topic}: {data}")
                return "mock-message-id"

        except Exception as e:
            logger.error(
                "❌ Failed to publish to %s: %s (%r)",
                topic,
                type(e).__name__,
                e,
            )
            return None

    async def subscribe(
        self,
        topic: str,
        handler: Callable[[dict[str, Any]], Any],
        subscription_name: str | None = None,
    ):
        """
        Subscribe to a topic with a message handler.

        Args:
            topic: Topic name
            handler: Async function to handle messages
            subscription_name: Optional custom subscription name
        """
        if not self._initialized:
            await self.initialize()

        # Store handler
        if topic not in self._handlers:
            self._handlers[topic] = []
        self._handlers[topic].append(handler)

        # Create subscription name
        service_name = _resolve_runtime_service_name()
        sub_name = subscription_name or f"{topic}-{service_name}-sub"
        subscription_path = f"projects/{PROJECT_ID}/subscriptions/{sub_name}"

        if self._subscriber:
            try:
                # Create subscription if it doesn't exist
                topic_path = self.TOPICS.get(topic, f"projects/{PROJECT_ID}/topics/{topic}")

                # Use thread for create_subscription (network call)
                try:
                    await asyncio.to_thread(
                        self._subscriber.create_subscription,
                        name=subscription_path,
                        topic=topic_path,
                        ack_deadline_seconds=SUBSCRIPTION_ACK_DEADLINE_SECONDS,
                    )
                    logger.info(f"📥 Created subscription: {sub_name}")
                except Exception:
                    pass  # Subscription already exists

                # Enforce ack deadline on existing subscriptions as well.
                try:
                    await asyncio.to_thread(
                        self._subscriber.update_subscription,
                        request={
                            "subscription": {
                                "name": subscription_path,
                                "ack_deadline_seconds": SUBSCRIPTION_ACK_DEADLINE_SECONDS,
                            },
                            "update_mask": {"paths": ["ack_deadline_seconds"]},
                        },
                    )
                except Exception as exc:
                    logger.debug(f"Could not update ack deadline for {sub_name}: {exc}")

                # Start pulling messages in background
                task = asyncio.create_task(self._pull_messages(subscription_path, topic))
                self._pull_tasks.append(task)
                logger.info(f"📥 Subscribed to {topic}")
            except Exception as e:
                logger.error(f"❌ Failed to subscribe to {topic}: {e}")
        else:
            logger.info(f"📥 [MOCK] Would subscribe to {topic}")

    async def _pull_messages(self, subscription_path: str, topic: str):
        """Background task to pull and process messages."""
        while not self._closing:
            try:
                # Blocking Pull call
                response = await asyncio.to_thread(
                    self._subscriber.pull,
                    subscription=subscription_path,
                    max_messages=10,
                    timeout=20,
                )

                for msg in response.received_messages:
                    try:
                        data = json.loads(msg.message.data.decode("utf-8"))

                        # Call all handlers for this topic
                        for handler in self._handlers.get(topic, []):
                            try:
                                result = handler(data)
                                if asyncio.iscoroutine(result):
                                    await result
                            except Exception as e:
                                logger.error(f"Handler error for {topic}: {e}")

                        # Acknowledge the message (blocking network call)
                        await asyncio.to_thread(
                            self._subscriber.acknowledge,
                            subscription=subscription_path,
                            ack_ids=[msg.ack_id],
                        )

                    except Exception as e:
                        logger.error(f"Message processing error: {e}")

            except Exception as e:
                if isinstance(e, asyncio.CancelledError):
                    break
                error_str = str(e)
                # Only log unexpected errors, not timeouts or missing subscriptions
                if "Deadline Exceeded" not in error_str and "NOT_FOUND" not in error_str:
                    logger.error(f"Pull error from {subscription_path}: {e}")
                elif "NOT_FOUND" in error_str:
                    logger.debug(f"Subscription {subscription_path} not found, skipping")
                    await asyncio.sleep(60)  # Wait longer if subscription doesn't exist
                await asyncio.sleep(5)  # Wait before retry

            await asyncio.sleep(0.1)  # Small delay between pulls

    async def close(self) -> None:
        """Gracefully stop pull workers and close Pub/Sub transports."""
        self._closing = True

        tasks = [t for t in self._pull_tasks if t is not None and not t.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._pull_tasks = []

        for client_attr in ("_subscriber", "_publisher"):
            client = getattr(self, client_attr, None)
            if client is None:
                continue
            try:
                close_fn = getattr(client, "close", None)
                if callable(close_fn):
                    maybe = close_fn()
                    if asyncio.iscoroutine(maybe):
                        await maybe
            except Exception as exc:
                logger.debug("Pub/Sub %s close warning: %s", client_attr, exc)
            finally:
                setattr(self, client_attr, None)

        self._subscriptions = {}
        self._handlers = {}
        self._initialized = False

    def _serialize_datetimes(self, data: dict) -> dict:
        """Convert datetime objects to ISO format strings."""
        result = {}
        for key, value in data.items():
            if isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, dict):
                result[key] = self._serialize_datetimes(value)
            elif isinstance(value, list):
                result[key] = [
                    (
                        self._serialize_datetimes(v)
                        if isinstance(v, dict)
                        else v.isoformat() if isinstance(v, datetime) else v
                    )
                    for v in value
                ]
            else:
                result[key] = value
        return result


# Singleton instance
_client: PubSubClient | None = None


def get_pubsub_client() -> PubSubClient:
    """Get or create the singleton Pub/Sub client.

    Auto-selects backend:
      - REDIS_URL set  → RedisPubSubClient (on-prem, no GCP)
      - Otherwise      → PubSubClient (GCP Pub/Sub or mock fallback)
    """
    global _client
    if _client is None:
        redis_url = (os.getenv("REDIS_URL") or "").strip()
        if redis_url:
            from sapphire_core.pubsub.redis_client import RedisPubSubClient
            _client = RedisPubSubClient(redis_url)  # type: ignore[assignment]
        else:
            _client = PubSubClient()
    return _client


# Convenience functions
async def publish(topic: str, message: Any) -> str | None:
    """Publish a message to a topic."""
    client = get_pubsub_client()
    return await client.publish(topic, message)


async def subscribe(topic: str, handler: Callable[[dict[str, Any]], Any]):
    """Subscribe to a topic with a handler."""
    client = get_pubsub_client()
    await client.subscribe(topic, handler)
