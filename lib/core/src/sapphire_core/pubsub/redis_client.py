"""
Redis-backed Pub/Sub client — on-prem replacement for GCP Pub/Sub.

Activated when REDIS_URL env var is set.
Uses Redis Streams (XADD/XREADGROUP) for durable message delivery with
consumer groups — semantically equivalent to GCP Pub/Sub subscriptions.

Usage:
  export REDIS_URL=redis://localhost:6379
  # Then get_pubsub_client() returns RedisPubSubClient automatically.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "")
REDIS_STREAM_MAXLEN = int(os.getenv("REDIS_STREAM_MAXLEN", "10000"))
REDIS_CONSUMER_GROUP = os.getenv("REDIS_CONSUMER_GROUP", "sapphire")


def _serialize(data: Any) -> str:
    if is_dataclass(data):
        data = asdict(data)
    if not isinstance(data, dict):
        data = {"value": data}
    # Convert datetimes to ISO strings
    def _coerce(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _coerce(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_coerce(i) for i in obj]
        if isinstance(obj, datetime):
            return obj.isoformat()
        return obj
    return json.dumps(_coerce(data))


class RedisPubSubClient:
    """
    Drop-in replacement for PubSubClient using Redis Streams.

    Topics map to Redis Stream keys (e.g., "trading-signals" → stream key
    "sapphire:trading-signals"). Each subscriber gets its own consumer
    group entry, matching GCP Pub/Sub fan-out semantics.
    """

    TOPIC_PREFIX = "sapphire"

    def __init__(self, url: str = "") -> None:
        self._url = url or REDIS_URL
        self._redis: Any = None
        self._handlers: dict[str, list[Callable]] = {}
        self._pull_tasks: list[asyncio.Task] = []
        self._closing = False
        self._initialized = False
        self._service_name = self._resolve_service_name()

    def _resolve_service_name(self) -> str:
        for key in ("SERVICE_NAME", "K_SERVICE", "HOSTNAME"):
            v = (os.getenv(key) or "").strip()
            if v:
                return v
        return "unknown"

    def _stream_key(self, topic: str) -> str:
        return f"{self.TOPIC_PREFIX}:{topic}"

    def _group_name(self, topic: str) -> str:
        return f"{REDIS_CONSUMER_GROUP}-{self._service_name}"

    async def initialize(self) -> None:
        if self._initialized:
            return
        try:
            import redis.asyncio as aioredis  # type: ignore
            self._redis = aioredis.from_url(self._url, decode_responses=True)
            await self._redis.ping()
            self._initialized = True
            logger.info("✅ Redis PubSub initialized: %s", self._url)
        except ImportError:
            logger.warning("⚠️ redis package not installed — falling back to mock mode")
            self._initialized = True
        except Exception as exc:
            logger.error("❌ Redis connection failed (%s): %s", self._url, exc)
            self._initialized = True  # Don't crash — mock mode

    async def publish(self, topic: str, message: Any) -> str | None:
        if not self._initialized:
            await self.initialize()
        if self._redis is None:
            logger.info("📤 [MOCK-REDIS] Would publish to %s", topic)
            return "mock-id"
        try:
            key = self._stream_key(topic)
            data = _serialize(message)
            msg_id = await self._redis.xadd(
                key,
                {"data": data},
                maxlen=REDIS_STREAM_MAXLEN,
                approximate=True,
            )
            logger.debug("📤 Redis stream %s → %s", key, msg_id)
            return msg_id
        except Exception as exc:
            logger.error("❌ Redis publish to %s failed: %s", topic, exc)
            return None

    async def subscribe(
        self,
        topic: str,
        handler: Callable[[dict[str, Any]], Any],
        subscription_name: str | None = None,
    ) -> None:
        if not self._initialized:
            await self.initialize()

        if topic not in self._handlers:
            self._handlers[topic] = []
        self._handlers[topic].append(handler)

        if self._redis is None:
            logger.info("📥 [MOCK-REDIS] Would subscribe to %s", topic)
            return

        key = self._stream_key(topic)
        group = self._group_name(topic)

        # Create stream + consumer group (idempotent)
        try:
            await self._redis.xgroup_create(key, group, id="0", mkstream=True)
        except Exception:
            pass  # Already exists

        task = asyncio.create_task(self._read_loop(key, group, topic))
        self._pull_tasks.append(task)
        logger.info("📥 Redis subscribed to %s (stream=%s group=%s)", topic, key, group)

    async def _read_loop(self, key: str, group: str, topic: str) -> None:
        consumer = f"{self._service_name}-{id(self)}"
        while not self._closing:
            try:
                results = await self._redis.xreadgroup(
                    groupname=group,
                    consumername=consumer,
                    streams={key: ">"},
                    count=10,
                    block=2000,  # ms
                )
                if not results:
                    continue
                for _key, messages in results:
                    for msg_id, fields in messages:
                        try:
                            data = json.loads(fields.get("data", "{}"))
                            for handler in self._handlers.get(topic, []):
                                try:
                                    result = handler(data)
                                    if asyncio.iscoroutine(result):
                                        await result
                                except Exception as exc:
                                    logger.error("Handler error for %s: %s", topic, exc)
                            await self._redis.xack(key, group, msg_id)
                        except Exception as exc:
                            logger.error("Message processing error (stream=%s): %s", key, exc)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                if not self._closing:
                    logger.error("Redis read loop error (stream=%s): %s", key, exc)
                    await asyncio.sleep(5)

    async def close(self) -> None:
        self._closing = True
        tasks = [t for t in self._pull_tasks if not t.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._pull_tasks = []
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            self._redis = None
        self._initialized = False
