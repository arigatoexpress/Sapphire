"""Pub/Sub utilities for event publishing."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from google.cloud import pubsub_v1
from google.api_core.exceptions import NotFound

import logging

from .config import Settings
from .metrics import PUBSUB_PUBLISH_FAILURES


logger = logging.getLogger(__name__)

class PubSubClient:
    """Wrapper around Google Cloud Pub/Sub for event publishing."""

    def __init__(self, settings: Settings):
        self._project_id = settings.gcp_project_id
        self._decisions_topic = settings.decisions_topic
        self._positions_topic = settings.positions_topic
        self._reasoning_topic = settings.reasoning_topic
        self._publisher: Optional[pubsub_v1.PublisherClient] = None

    async def connect(self) -> None:
        """Instantiate the Pub/Sub publisher client."""
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

    # The stream_events functionality is not directly replicable with Pub/Sub in the same way.
    # Pub/Sub is a message bus, not a persistent log like Redis Streams.
    # To get recent events, we would need a subscriber that saves them to a database.
    # For now, we will leave this functionality out, as it's primarily for the dashboard,
    # and we can address dashboard data sourcing separately.
    async def stream_events(self, stream_name: str, limit: int) -> list:
        return []
