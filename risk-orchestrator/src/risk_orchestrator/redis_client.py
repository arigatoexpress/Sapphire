from __future__ import annotations

import json
from typing import Any, Dict, Optional

try:  # pragma: no cover - optional dependency
    import redis.asyncio as redis
except Exception:  # pragma: no cover
    redis = None  # type: ignore

from .config import settings


class RedisClient:
    # Shared connection pool for all instances
    _pool: Optional[redis.ConnectionPool] = None
    _pool_url: Optional[str] = None

    def __init__(self) -> None:
        self._redis = self._build_redis_client(settings.REDIS_URL)
        self._portfolio_cache: Dict[str, Any] = {}
        self._pending_orders: Dict[str, float] = {}
        self._events: list[Dict[str, Any]] = []
        self._portfolio_timestamp: Optional[float] = None

    @classmethod
    def _build_redis_client(cls, url: Optional[str]):
        """Build Redis client with connection pooling."""
        if not url or redis is None:
            return None
        try:
            # Create or reuse connection pool
            if cls._pool is None or cls._pool_url != url:
                cls._pool = redis.ConnectionPool.from_url(
                    url,
                    decode_responses=True,
                    max_connections=100,
                    retry_on_timeout=True,
                )
                cls._pool_url = url

            return redis.Redis(connection_pool=cls._pool)
        except Exception:
            return None

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()

    async def set_portfolio(self, data: Dict[str, Any]) -> None:
        import time

        self._portfolio_cache = data
        self._portfolio_timestamp = time.time()
        if self._redis:
            try:
                await self._redis.set("portfolio:current", json.dumps(data), ex=300)  # 5 minutes
                await self._redis.set("portfolio:timestamp", str(self._portfolio_timestamp), ex=300)
            except Exception:
                pass

    async def get_portfolio(self) -> Dict[str, Any]:
        if self._redis:
            try:
                payload = await self._redis.get("portfolio:current")
                if payload:
                    self._portfolio_cache = json.loads(payload)
            except Exception:
                pass
        return self._portfolio_cache

    async def get_portfolio_age(self) -> Optional[float]:
        """Return age of portfolio cache in seconds, or None if no cache."""
        import time

        if self._redis:
            try:
                timestamp_str = await self._redis.get("portfolio:timestamp")
                if timestamp_str:
                    return time.time() - float(timestamp_str)
            except Exception:
                pass
        if self._portfolio_timestamp is not None:
            return time.time() - self._portfolio_timestamp
        return None

    async def add_pending_order(self, order_id: str) -> None:
        if self._redis:
            try:
                await self._redis.sadd("orders:pending", order_id)
                await self._redis.expire("orders:pending", 3600)
                return
            except Exception:
                pass
        self._pending_orders[order_id] = 1.0

    async def is_duplicate(self, order_id: str) -> bool:
        if self._redis:
            try:
                exists = await self._redis.sismember("orders:pending", order_id)
                if exists:
                    return True
            except Exception:
                pass
        return order_id in self._pending_orders

    async def remove_pending_order(self, order_id: str) -> None:
        if self._redis:
            try:
                await self._redis.srem("orders:pending", order_id)
                return
            except Exception:
                pass
        self._pending_orders.pop(order_id, None)

    async def log_event(self, event: Dict[str, Any]) -> None:
        if self._redis:
            try:
                await self._redis.lpush("events:recent", json.dumps(event))
                await self._redis.ltrim("events:recent", 0, 99)
                return
            except Exception:
                pass
        self._events.insert(0, event)
        self._events = self._events[:100]

    def has_redis(self) -> bool:
        return self._redis is not None

