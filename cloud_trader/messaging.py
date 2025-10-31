"""Redis Streams utilities for decision and position telemetry."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

import redis.asyncio as redis

from .config import Settings


class RedisStreamsClient:
    """Wrapper around Redis Streams for lean telemetry."""

    def __init__(self, settings: Settings) -> None:
        self._url = settings.redis_url
        self._decisions_stream = settings.decisions_stream
        self._positions_stream = settings.positions_stream
        self._reasoning_stream = settings.reasoning_stream
        self._maxlen = settings.redis_stream_maxlen
        self._client: Optional[redis.Redis] = None

    async def connect(self) -> None:
        if self._client is None and self._url:
            self._client = redis.from_url(self._url, decode_responses=True)

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    async def publish_decision(self, payload: Dict[str, str]) -> None:
        client = await self._ensure()
        await client.xadd(self._decisions_stream, payload, maxlen=self._maxlen, approximate=True)

    async def publish_reasoning(self, payload: Dict[str, str]) -> None:
        client = await self._ensure()
        await client.xadd(self._reasoning_stream, payload, maxlen=self._maxlen, approximate=True)

    async def publish_position(self, payload: Dict[str, str]) -> None:
        client = await self._ensure()
        await client.xadd(self._positions_stream, payload, maxlen=self._maxlen, approximate=True)

    async def read_latest(self, stream: str, count: int = 50) -> List[Dict[str, str]]:
        client = await self._ensure()
        entries = await client.xrevrange(stream, count=count)
        parsed: List[Dict[str, str]] = []
        for entry_id, payload in entries:
            data = dict(payload)
            data["id"] = entry_id
            parsed.append(data)
        return list(reversed(parsed))

    async def _ensure(self) -> redis.Redis:
        if self._client is None:
            await self.connect()
        if self._client is None:
            raise RuntimeError("Redis client not configured (REDIS_URL missing)")
        return self._client


def timestamp() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

