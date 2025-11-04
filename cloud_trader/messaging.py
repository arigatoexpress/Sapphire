"""Redis Streams utilities for decision and position telemetry."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

import redis.asyncio as redis

from .config import Settings


class RedisStreamsClient:
    """Wrapper around Redis Streams for lean telemetry with connection pooling."""

    # Shared connection pool for all instances
    _pool: Optional[redis.ConnectionPool] = None
    _pool_url: Optional[str] = None

    def __init__(self, settings: Settings) -> None:
        self._url = settings.redis_url
        self._decisions_stream = settings.decisions_stream
        self._positions_stream = settings.positions_stream
        self._reasoning_stream = settings.reasoning_stream
        self._maxlen = settings.redis_stream_maxlen
        self._client: Optional[redis.Redis] = None

    async def connect(self) -> None:
        """Connect to Redis using connection pooling."""
        if self._client is None and self._url:
            try:
                # Create or reuse connection pool
                if RedisStreamsClient._pool is None or RedisStreamsClient._pool_url != self._url:
                    RedisStreamsClient._pool = redis.ConnectionPool.from_url(
                        self._url,
                        decode_responses=True,
                        max_connections=100,
                        retry_on_timeout=True,
                    )
                    RedisStreamsClient._pool_url = self._url
                
                client = redis.Redis(connection_pool=RedisStreamsClient._pool)
                await client.ping()
            except Exception:
                self._client = None
            else:
                self._client = client

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    def is_connected(self) -> bool:
        return self._client is not None

    async def publish_decision(self, payload: Dict[str, str]) -> None:
        client = await self._ensure()
        if client:
            await client.xadd(self._decisions_stream, payload, maxlen=self._maxlen, approximate=True)

    async def publish_reasoning(self, payload: Dict[str, str]) -> None:
        client = await self._ensure()
        if client:
            await client.xadd(self._reasoning_stream, payload, maxlen=self._maxlen, approximate=True)

    async def publish_position(self, payload: Dict[str, str]) -> None:
        client = await self._ensure()
        if client:
            await client.xadd(self._positions_stream, payload, maxlen=self._maxlen, approximate=True)

    async def read_latest(self, stream: str, count: int = 50) -> List[Dict[str, str]]:
        client = await self._ensure()
        if not client:
            return []
        entries = await client.xrevrange(stream, count=count)
        parsed: List[Dict[str, str]] = []
        for entry_id, payload in entries:
            data = dict(payload)
            data["id"] = entry_id
            parsed.append(data)
        return list(reversed(parsed))

    async def _ensure(self) -> Optional[redis.Redis]:
        if not self._url:
            return None
        if self._client is None:
            await self.connect()
        return self._client


def timestamp() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

