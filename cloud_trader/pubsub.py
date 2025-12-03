"""Pub/Sub utilities for event publishing."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

try:
    from google.cloud import pubsub_v1
    from google.api_core.exceptions import NotFound
except ImportError:
    pubsub_v1 = None
    class NotFound(Exception):
        pass
    print("⚠️ PubSub not found. Messaging disabled.")

from .config import Settings
from .metrics import PUBSUB_PUBLISH_FAILURES

logger = logging.getLogger(__name__)


class PubSubClient:
    """Google Cloud Pub/Sub client wrapper."""
    
    def __init__(self, project_id: str, topic_id: str, subscription_id: str):
        self.project_id = project_id
        self.topic_id = topic_id
        self.subscription_id = subscription_id
        self.publisher = None
        self.subscriber = None
        
        if pubsub_v1:
            try:
                self.publisher = pubsub_v1.PublisherClient()
                self.subscriber = pubsub_v1.SubscriberClient()
                self.topic_path = self.publisher.topic_path(project_id, topic_id)
                self.subscription_path = self.subscriber.subscription_path(project_id, subscription_id)
            except Exception as e:
                print(f"⚠️ Failed to init PubSub: {e}")

    async def connect(self) -> None:
        """Instantiate the Pub/Sub publisher client."""
        if not self._settings.enable_pubsub:
            logger.info("Pub/Sub disabled by configuration")
            return

        if self._publisher is None and self._project_id:
            try:
                self._publisher = pubsub_v1.PublisherClient()
                # You might want to verify topics exist here, but for now we assume they do.
            except Exception:
                self._publisher = None

    async def close(self) -> None:
        if self._publisher:
            self._publisher.stop()
            self._publisher = None

    def is_connected(self) -> bool:
        return self._publisher is not None

    async def _publish(self, topic_name: str, payload: Dict[str, Any]) -> None:
        if not self._publisher or not self._project_id:
            return

        topic_path = self._publisher.topic_path(self._project_id, topic_name)
        data = json.dumps(payload, default=str).encode("utf-8")
        try:
            future = self._publisher.publish(topic_path, data)
        except Exception as exc:
            PUBSUB_PUBLISH_FAILURES.labels(topic=topic_name).inc()
            logger.error("Failed to publish to Pub/Sub topic %s: %s", topic_name, exc)
            return

        def _on_publish_done(result_future: Any) -> None:
            exception = result_future.exception()
            if exception is not None:
                PUBSUB_PUBLISH_FAILURES.labels(topic=topic_name).inc()
                logger.error("Pub/Sub publish future failed for %s: %s", topic_name, exception)

        future.add_done_callback(_on_publish_done)
        # We can optionally await the future to ensure the message is published.
        # For a fire-and-forget approach, we can just let it run in the background.
        # future.result()

    async def publish_decision(self, payload: Dict[str, Any]) -> None:
        await self._publish(self._decisions_topic, payload)

    async def publish_position(self, payload: Dict[str, Any]) -> None:
        await self._publish(self._positions_topic, payload)

    async def publish_trade_execution(self, payload: Dict[str, Any]) -> None:
        """Publish detailed trade execution analytics to the positions topic."""
        await self._publish(self._positions_topic, payload)

    async def publish_reasoning(self, payload: Dict[str, Any]) -> None:
        await self._publish(self._reasoning_topic, payload)

    async def publish_hft_signal(self, payload: Dict[str, Any]) -> None:
        """Publish HFT trading signal."""
        await self._publish(self._decisions_topic, payload)

    async def publish_market_data(self, payload: Dict[str, Any]) -> None:
        """Publish market data update."""
        await self._publish(self._reasoning_topic, payload)

    async def publish_order_execution(self, payload: Dict[str, Any]) -> None:
        """Publish order execution notification."""
        await self._publish(self._positions_topic, payload)

    async def publish_risk_update(self, payload: Dict[str, Any]) -> None:
        """Publish risk management update."""
        await self._publish(self._positions_topic, payload)

    async def publish_strategy_adjustment(self, payload: Dict[str, Any]) -> None:
        """Publish strategy parameter adjustment."""
        await self._publish(self._reasoning_topic, payload)

    async def publish_liquidity_update(self, payload: Dict[str, Any]) -> None:
        """Publish liquidity provision update."""
        await self._publish(self._reasoning_topic, payload)

    async def publish_market_making_status(self, payload: Dict[str, Any]) -> None:
        """Publish market making operational status."""
        await self._publish(self._reasoning_topic, payload)

    async def publish_portfolio_rebalance(self, payload: Dict[str, Any]) -> None:
        """Publish portfolio rebalancing instructions."""
        await self._publish(self._decisions_topic, payload)

    async def publish_strategy_performance(self, payload: Dict[str, Any]) -> None:
        """Publish strategy performance metrics."""
        await self._publish(self._reasoning_topic, payload)

    # The stream_events functionality is not directly replicable with Pub/Sub in the same way.
    # Pub/Sub is a message bus, not a persistent log like Redis Streams.
    # To get recent events, we would need a subscriber that saves them to a database.
    # For now, we will leave this functionality out, as it's primarily for the dashboard,
    # and we can address dashboard data sourcing separately.
    async def stream_events(self, stream_name: str, limit: int) -> list:
        return []

    async def subscribe(self, topic_name: str, callback: Any) -> None:
        """Subscribe to a topic with a callback function.
        
        Note: In Cloud Run, pulling messages is generally done via push subscriptions 
        triggering an HTTP endpoint, or a background worker. This implementation 
        assumes a background worker context where streaming pull is feasible.
        """
        if not self._settings.enable_pubsub or not self._project_id:
            logger.warning(f"Pub/Sub disabled, cannot subscribe to {topic_name}")
            return

        # Basic subscription logic - simplified for now as we primarily use push events
        # or this service is mainly a publisher.
        # A real implementation would need a SubscriberClient and proper flow control.
        logger.warning(f"Subscribe called for {topic_name} but standard client is publisher-only. Use dedicated subscriber if needed.")
        return
