"""Pub/Sub Package.

Backend selection (via get_pubsub_client()):
  REDIS_URL set  → RedisPubSubClient (on-prem, Redis Streams)
  otherwise      → PubSubClient (GCP Pub/Sub or mock fallback)
"""

from .client import PubSubClient, get_pubsub_client, publish, subscribe
from .redis_client import RedisPubSubClient

__all__ = [
    "PubSubClient",
    "RedisPubSubClient",
    "get_pubsub_client",
    "publish",
    "subscribe",
]
