"""Redis Streams publisher helpers for telemetry and decision flow."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

import orjson
from redis.asyncio import Redis


logger = logging.getLogger(__name__)


class RedisEventPublisher:
    def __init__(
        self,
        redis_url: str,
        *,
        decisions_stream: str,
        positions_stream: str,
        reasoning_stream: str,
        maxlen: int = 2000,
    ) -> None:
        self._redis = Redis.from_url(redis_url, encoding=None, decode_responses=False)
        self._streams = {
            "decision": decisions_stream,
            "position": positions_stream,
            "reasoning": reasoning_stream,
        }
        self._maxlen = maxlen
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        await self._redis.close()

    async def publish(self, kind: str, payload: Dict[str, Any]) -> None:
        stream = self._streams.get(kind)
        if not stream:
            logger.debug("No stream configured for kind='%s'", kind)
            return

        data = orjson.dumps(payload)
        async with self._lock:
            await self._redis.xadd(stream, {b"payload": data}, maxlen=self._maxlen, approximate=True)

    async def publish_decision(self, payload: Dict[str, Any]) -> None:
        await self.publish("decision", payload)

    async def publish_position(self, payload: Dict[str, Any]) -> None:
        await self.publish("position", payload)

    async def publish_reasoning(self, payload: Dict[str, Any]) -> None:
        await self.publish("reasoning", payload)


class NullEventPublisher(RedisEventPublisher):
    def __init__(self) -> None:  # type: ignore[override]
        pass

    async def close(self) -> None:  # type: ignore[override]
        return None

    async def publish(self, kind: str, payload: Dict[str, Any]) -> None:  # type: ignore[override]
        return None

    async def publish_decision(self, payload: Dict[str, Any]) -> None:  # type: ignore[override]
        return None

    async def publish_position(self, payload: Dict[str, Any]) -> None:  # type: ignore[override]
        return None

    async def publish_reasoning(self, payload: Dict[str, Any]) -> None:  # type: ignore[override]
        return None

