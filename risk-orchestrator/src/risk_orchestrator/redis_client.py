from __future__ import annotations

import json
from typing import Any, Dict

import redis.asyncio as redis

from .config import settings


class RedisClient:
    def __init__(self) -> None:
        self._redis = redis.from_url(settings.REDIS_URL, decode_responses=True)

    async def close(self) -> None:
        await self._redis.close()

    async def set_portfolio(self, data: Dict[str, Any]) -> None:
        await self._redis.set("portfolio:current", json.dumps(data), ex=5)

    async def get_portfolio(self) -> Dict[str, Any]:
        payload = await self._redis.get("portfolio:current")
        if not payload:
            return {}
        return json.loads(payload)

    async def add_pending_order(self, order_id: str) -> None:
        await self._redis.sadd("orders:pending", order_id)
        await self._redis.expire("orders:pending", 3600)

    async def is_duplicate(self, order_id: str) -> bool:
        return bool(await self._redis.sismember("orders:pending", order_id))

    async def log_event(self, event: Dict[str, Any]) -> None:
        await self._redis.xadd("events:log", event)

