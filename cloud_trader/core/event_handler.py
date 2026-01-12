"""
Event Handler Module
Manages Pub/Sub subscriptions for event-driven trading.
"""

import asyncio
import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Lazy import for Pub/Sub
_pubsub_client = None


def _get_pubsub_client():
    """Get or create Pub/Sub client singleton."""
    global _pubsub_client
    if _pubsub_client is not None:
        return _pubsub_client
    
    try:
        from google.cloud import pubsub_v1
        _pubsub_client = pubsub_v1.SubscriberClient()
        logger.info("🔗 Connected to Google Cloud Pub/Sub")
        return _pubsub_client
    except Exception as e:
        logger.warning(f"⚠️ Pub/Sub not available: {e}")
        return None


def _get_publisher():
    """Get Pub/Sub publisher client."""
    try:
        from google.cloud import pubsub_v1
        return pubsub_v1.PublisherClient()
    except Exception:
        return None


class EventHandler:
    """
    Handles event-driven messaging via Google Cloud Pub/Sub.
    """

    def __init__(self, project_id: Optional[str] = None):
        self.project_id = project_id or os.getenv("GCP_PROJECT_ID", "sapphire-trading")
        self.subscriber = _get_pubsub_client()
        self.publisher = _get_publisher()
        
        self._subscriptions: Dict[str, Any] = {}
        self._callbacks: Dict[str, List[Callable]] = {}
        self._executor = ThreadPoolExecutor(max_workers=5)
        self._running = False

    # --- Publishing ---

    async def publish(self, topic: str, message: Dict[str, Any], ordering_key: Optional[str] = None) -> bool:
        """
        Publish a message to a Pub/Sub topic.
        
        Args:
            topic: Topic name (without project prefix)
            message: Message data (JSON-serializable)
            ordering_key: Optional key for ordered delivery
        
        Returns:
            True if published successfully
        """
        if not self.publisher:
            logger.warning(f"Pub/Sub not available, cannot publish to {topic}")
            return False
        
        topic_path = self.publisher.topic_path(self.project_id, topic)
        data = json.dumps(message).encode("utf-8")
        
        try:
            future = self.publisher.publish(topic_path, data, ordering_key=ordering_key or "")
            # Wait for acknowledgment (with timeout)
            message_id = await asyncio.get_event_loop().run_in_executor(
                self._executor, future.result, 10
            )
            logger.debug(f"Published message {message_id} to {topic}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to publish to {topic}: {e}")
            return False

    # --- Subscribing ---

    def subscribe(self, subscription: str, callback: Callable[[Dict], None]):
        """
        Subscribe to a Pub/Sub subscription.
        
        Args:
            subscription: Subscription name
            callback: Async function to handle messages
        """
        if subscription not in self._callbacks:
            self._callbacks[subscription] = []
        self._callbacks[subscription].append(callback)
        
        logger.info(f"📡 Registered callback for subscription: {subscription}")

    async def start_listening(self):
        """Start listening to all registered subscriptions."""
        if not self.subscriber:
            logger.warning("Pub/Sub not available, running in mock mode")
            self._running = True
            return
        
        self._running = True
        
        for subscription_name, callbacks in self._callbacks.items():
            subscription_path = self.subscriber.subscription_path(
                self.project_id, subscription_name
            )
            
            def create_callback(cbs):
                def callback(message):
                    try:
                        data = json.loads(message.data.decode("utf-8"))
                        logger.debug(f"Received message: {data}")
                        
                        # Invoke all registered callbacks
                        for cb in cbs:
                            try:
                                # Handle both sync and async callbacks
                                result = cb(data)
                                if asyncio.iscoroutine(result):
                                    asyncio.get_event_loop().run_until_complete(result)
                            except Exception as e:
                                logger.error(f"Callback error: {e}")
                        
                        # Acknowledge message
                        message.ack()
                        
                    except Exception as e:
                        logger.error(f"Message processing failed: {e}")
                        # Nack for retry
                        message.nack()
                
                return callback
            
            streaming_pull_future = self.subscriber.subscribe(
                subscription_path,
                callback=create_callback(callbacks)
            )
            
            self._subscriptions[subscription_name] = streaming_pull_future
            logger.info(f"🎧 Listening to subscription: {subscription_name}")

    async def stop_listening(self):
        """Stop all subscriptions."""
        self._running = False
        
        for name, future in self._subscriptions.items():
            future.cancel()
            logger.info(f"🛑 Stopped subscription: {name}")
        
        self._subscriptions.clear()

    # --- Local Event Simulation (for testing) ---

    async def simulate_event(self, subscription: str, event_data: Dict):
        """Simulate receiving an event (for testing without Pub/Sub)."""
        callbacks = self._callbacks.get(subscription, [])
        
        for cb in callbacks:
            try:
                result = cb(event_data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Simulated event callback error: {e}")


class MarketEventTypes:
    """Constants for market event types."""
    PRICE_UPDATE = "price_update"
    VOLUME_SPIKE = "volume_spike"
    SIGNAL_GENERATED = "signal_generated"
    ORDER_FILL = "order_fill"
    POSITION_CHANGE = "position_change"
    LIQUIDATION_RISK = "liquidation_risk"


def create_market_event(event_type: str, symbol: str, data: Dict) -> Dict:
    """Helper to create standardized market events."""
    import time
    return {
        "type": event_type,
        "symbol": symbol,
        "timestamp": time.time(),
        "data": data
    }
