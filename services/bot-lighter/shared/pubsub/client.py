"""
Pub/Sub Helper for Sapphire Trading Platform

Provides a unified interface for publishing and subscribing to events
across all bot services using GCP Pub/Sub.
"""

import asyncio
import json
import logging
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

try:
    from google.cloud import pubsub_v1
except ImportError:
    pubsub_v1 = None

logger = logging.getLogger(__name__)

# Check if we're using emulator (for local development)
PUBSUB_EMULATOR_HOST = os.getenv("PUBSUB_EMULATOR_HOST")

# GCP Project ID
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "sapphire-479610")


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
        self._subscriptions: Dict[str, Any] = {}
        self._handlers: Dict[str, List[Callable]] = {}
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

    async def publish(self, topic: str, message: Any) -> Optional[str]:
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
                message_id = await asyncio.to_thread(future.result, timeout=10)
                logger.debug(f"📤 Published to {topic}: {message_id}")
                return message_id
            else:
                # Mock mode - just log
                logger.info(f"📤 [MOCK] Would publish to {topic}: {data}")
                return "mock-message-id"

        except Exception as e:
            logger.error(f"❌ Failed to publish to {topic}: {e}")
            return None

    async def subscribe(
        self,
        topic: str,
        handler: Callable[[Dict[str, Any]], Any],
        subscription_name: Optional[str] = None,
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
        service_name = os.getenv("SERVICE_NAME", "unknown")
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
                    )
                    logger.info(f"📥 Created subscription: {sub_name}")
                except Exception:
                    pass  # Subscription already exists

                # Start pulling messages in background
                asyncio.create_task(self._pull_messages(subscription_path, topic))
                logger.info(f"📥 Subscribed to {topic}")
            except Exception as e:
                logger.error(f"❌ Failed to subscribe to {topic}: {e}")
        else:
            logger.info(f"📥 [MOCK] Would subscribe to {topic}")

    async def _pull_messages(self, subscription_path: str, topic: str):
        """Background task to pull and process messages."""
        while True:
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
                error_str = str(e)
                # Only log unexpected errors, not timeouts or missing subscriptions
                if "Deadline Exceeded" not in error_str and "NOT_FOUND" not in error_str:
                    logger.error(f"Pull error from {subscription_path}: {e}")
                elif "NOT_FOUND" in error_str:
                    logger.debug(f"Subscription {subscription_path} not found, skipping")
                    await asyncio.sleep(60)  # Wait longer if subscription doesn't exist
                await asyncio.sleep(5)  # Wait before retry

            await asyncio.sleep(0.1)  # Small delay between pulls

    def _serialize_datetimes(self, data: Dict) -> Dict:
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
_client: Optional[PubSubClient] = None


def get_pubsub_client() -> PubSubClient:
    """Get or create the singleton Pub/Sub client."""
    global _client
    if _client is None:
        _client = PubSubClient()
    return _client


# Convenience functions
async def publish(topic: str, message: Any) -> Optional[str]:
    """Publish a message to a topic."""
    client = get_pubsub_client()
    return await client.publish(topic, message)


async def subscribe(topic: str, handler: Callable[[Dict[str, Any]], Any]):
    """Subscribe to a topic with a handler."""
    client = get_pubsub_client()
    await client.subscribe(topic, handler)
