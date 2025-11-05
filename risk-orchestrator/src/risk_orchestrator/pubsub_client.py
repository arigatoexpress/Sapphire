"""Pub/Sub utilities for the Risk Orchestrator."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from google.cloud import pubsub_v1
from .config import settings

class PubSubClient:
    """Wrapper around Google Cloud Pub/Sub for event publishing."""

    def __init__(self):
        self._project_id = settings.GCP_PROJECT_ID
        self._publisher: Optional[pubsub_v1.PublisherClient] = None

    def connect(self):
        """Instantiate the Pub/Sub publisher client."""
        if self._publisher is None and self._project_id:
            self._publisher = pubsub_v1.PublisherClient()

    def close(self):
        if self._publisher:
            self._publisher.stop()

    async def log_event(self, event: Dict[str, Any]):
        """
        Publishes an event to a dynamic topic based on the event content.
        For now, we'll route all events to a single 'positions' topic for simplicity.
        """
        if not self._publisher or not self._project_id:
            return

        topic_name = settings.POSITIONS_TOPIC # Or choose based on event type
        topic_path = self._publisher.topic_path(self._project_id, topic_name)
        data = json.dumps(event, default=str).encode("utf-8")
        
        future = self._publisher.publish(topic_path, data)
        # Fire-and-forget
