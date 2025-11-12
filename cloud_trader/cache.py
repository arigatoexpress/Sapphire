"""Caching layer for market data and computations."""
from __future__ import annotations

import asyncio
import json
import logging
import pickle
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from fnmatch import fnmatch
from typing import Any, Dict, List, Optional, Tuple, Union

try:  # pragma: no cover - optional dependency
    import redis.asyncio as redis
    from redis.asyncio import ConnectionPool
    REDIS_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    redis = None  # type: ignore
    ConnectionPool = None  # type: ignore
    REDIS_AVAILABLE = False

from .config import Settings, get_settings
from .strategy import MarketSnapshot

logger = logging.getLogger(__name__)


class CacheKeys:
    """Standardized cache key formats."""

    MARKET_SNAPSHOT = "market:snapshot:{symbol}"
    SYMBOL_INFO = "symbol:info:{symbol}"
    HISTORICAL_DATA = "historical:{symbol}:{interval}:{limit}"
    AGENT_DECISION = "agent:decision:{agent_id}:{symbol}"
    STRATEGY_SIGNAL = "strategy:signal:{strategy}:{symbol}"
    ORDER_BOOK = "orderbook:{symbol}"
    FUNDING_RATE = "funding:{symbol}"
    ATR = "atr:{symbol}:{period}"
    PORTFOLIO_STATE = "portfolio:state"
    AGENT_PERFORMANCE = "agent:performance:{agent_id}"


class BaseCache(ABC):
    """Abstract cache interface used by specific backends."""

    backend: str = "base"

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()
        self.ttls: Dict[str, int] = {
            "market_snapshot": 10,
            "symbol_info": 3600,
            "historical_data": 86400,
            "agent_decision": 0,
            "strategy_signal": 5,
            "order_book": 1,
            "funding_rate": 300,
            "atr": 300,
            "portfolio_state": 0,
            "agent_performance": 60,
        }

    @abstractmethod
    async def connect(self) -> None:
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        ...

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        ...

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        ...

    @abstractmethod
    async def delete(self, key: str) -> bool:
        ...

    @abstractmethod
    async def clear_pattern(self, pattern: str) -> int:
        ...

    async def get_stats(self) -> Optional[Dict[str, Any]]:
        return None

    async def get_market_snapshot(self, symbol: str) -> Optional[MarketSnapshot]:
        key = CacheKeys.MARKET_SNAPSHOT.format(symbol=symbol)
        data = await self.get(key)
        if not data:
            return None
        if isinstance(data, MarketSnapshot):
            return data
        return MarketSnapshot(**data)

    async def set_market_snapshot(self, symbol: str, snapshot: MarketSnapshot) -> bool:
        key = CacheKeys.MARKET_SNAPSHOT.format(symbol=symbol)
        payload = {
            "symbol": snapshot.symbol,
            "price": snapshot.price,
            "volume": snapshot.volume,
            "change_24h": snapshot.change_24h,
        }
        return await self.set(key, payload, self.ttls["market_snapshot"])

    async def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        key = CacheKeys.SYMBOL_INFO.format(symbol=symbol)
        return await self.get(key)

    async def set_symbol_info(self, symbol: str, info: Dict[str, Any]) -> bool:
        key = CacheKeys.SYMBOL_INFO.format(symbol=symbol)
        return await self.set(key, info, self.ttls["symbol_info"])

    async def get_historical_data(self, symbol: str, interval: str, limit: int) -> Optional[Any]:
        key = CacheKeys.HISTORICAL_DATA.format(symbol=symbol, interval=interval, limit=limit)
        return await self.get(key)

    async def set_historical_data(
        self, symbol: str, interval: str, limit: int, data: Any
    ) -> bool:
        key = CacheKeys.HISTORICAL_DATA.format(symbol=symbol, interval=interval, limit=limit)
        return await self.set(key, data, self.ttls["historical_data"])

    async def get_strategy_signal(self, strategy: str, symbol: str) -> Optional[Dict[str, Any]]:
        key = CacheKeys.STRATEGY_SIGNAL.format(strategy=strategy, symbol=symbol)
        return await self.get(key)

    async def set_strategy_signal(self, strategy: str, symbol: str, signal: Dict[str, Any]) -> bool:
        key = CacheKeys.STRATEGY_SIGNAL.format(strategy=strategy, symbol=symbol)
        return await self.set(key, signal, self.ttls["strategy_signal"])

    async def cache_order_book(self, symbol: str, order_book: Dict[str, Any]) -> bool:
        key = CacheKeys.ORDER_BOOK.format(symbol=symbol)
        return await self.set(key, order_book, self.ttls["order_book"])

    async def get_order_book(self, symbol: str) -> Optional[Dict[str, Any]]:
        key = CacheKeys.ORDER_BOOK.format(symbol=symbol)
        return await self.get(key)

    async def cache_funding_rate(self, symbol: str, funding_rate: float) -> bool:
        key = CacheKeys.FUNDING_RATE.format(symbol=symbol)
        return await self.set(key, {"funding_rate": funding_rate}, self.ttls["funding_rate"])

    async def get_funding_rate(self, symbol: str) -> Optional[float]:
        key = CacheKeys.FUNDING_RATE.format(symbol=symbol)
        data = await self.get(key)
        if data and isinstance(data, dict):
            return data.get("funding_rate")
        return None

    async def cache_atr(self, symbol: str, period: int, atr_value: float) -> bool:
        key = CacheKeys.ATR.format(symbol=symbol, period=period)
        return await self.set(key, {"atr": atr_value}, self.ttls["atr"])

    async def get_atr(self, symbol: str, period: int) -> Optional[float]:
        key = CacheKeys.ATR.format(symbol=symbol, period=period)
        data = await self.get(key)
        if data and isinstance(data, dict):
            return data.get("atr")
        return None

    async def cache_portfolio_state(self, portfolio: Dict[str, Any]) -> bool:
        return await self.set(CacheKeys.PORTFOLIO_STATE, portfolio, self.ttls["portfolio_state"])

    async def get_portfolio_state(self) -> Optional[Dict[str, Any]]:
        return await self.get(CacheKeys.PORTFOLIO_STATE)

    async def cache_agent_performance(self, agent_id: str, performance: Dict[str, Any]) -> bool:
        key = CacheKeys.AGENT_PERFORMANCE.format(agent_id=agent_id)
        return await self.set(key, performance, self.ttls["agent_performance"])

    async def get_agent_performance(self, agent_id: str) -> Optional[Dict[str, Any]]:
        key = CacheKeys.AGENT_PERFORMANCE.format(agent_id=agent_id)
        return await self.get(key)

    async def set_many(self, data: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        results = await asyncio.gather(
            *(self.set(key, value, ttl) for key, value in data.items()),
            return_exceptions=True,
        )
        return all(result is True for result in results)


class InMemoryCache(BaseCache):
    """Simple in-memory cache with TTL support."""

    backend = "memory"

    def __init__(self, settings: Optional[Settings] = None) -> None:
        super().__init__(settings=settings)
        self._store: Dict[str, Tuple[Any, Optional[float]]] = {}
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        logger.info("Using in-memory cache backend")

    async def disconnect(self) -> None:
        async with self._lock:
            self._store.clear()

    def is_connected(self) -> bool:
        return True

    def _purge_expired(self) -> None:
        now = time.time()
        expired = [key for key, (_, expiry) in self._store.items() if expiry and expiry <= now]
        for key in expired:
            self._store.pop(key, None)

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            self._purge_expired()
            entry = self._store.get(key)
            if not entry:
                return None
            value, expiry = entry
            if expiry and expiry <= time.time():
                self._store.pop(key, None)
                return None
            return value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        expires_at = time.time() + ttl if ttl and ttl > 0 else None
        async with self._lock:
            self._store[key] = (value, expires_at)
        return True

    async def delete(self, key: str) -> bool:
        async with self._lock:
            removed = self._store.pop(key, None) is not None
        return removed

    async def clear_pattern(self, pattern: str) -> int:
        async with self._lock:
            self._purge_expired()
            matched = [key for key in self._store if fnmatch(key, pattern)]
            for key in matched:
                self._store.pop(key, None)
        return len(matched)

    async def get_stats(self) -> Optional[Dict[str, Any]]:
        async with self._lock:
            self._purge_expired()
            return {"backend": "memory", "entries": len(self._store)}


class RedisCache(BaseCache):
    """Redis cache manager (optional backend)."""

    backend = "redis"

    def __init__(self, settings: Optional[Settings] = None) -> None:
        super().__init__(settings=settings)
        self._redis: Optional[redis.Redis] = None  # type: ignore[attr-defined]
        self._pool: Optional[ConnectionPool] = None  # type: ignore[attr-defined]

    async def connect(self) -> None:
        if not REDIS_AVAILABLE:
            logger.warning("Redis backend requested but redis client is unavailable.")
            return

        redis_url = self._settings.redis_url
        if not redis_url:
            logger.warning("REDIS_URL not configured, skipping Redis cache initialization.")
            return

        try:
            self._pool = ConnectionPool.from_url(  # type: ignore[attr-defined]
                redis_url,
                max_connections=50,
                decode_responses=False,
            )
            self._redis = redis.Redis(connection_pool=self._pool)  # type: ignore[attr-defined]
            await self._redis.ping()
            logger.info("Connected to Redis cache backend")
        except Exception as exc:  # pragma: no cover - network failures
            logger.warning("Failed to connect to Redis (%s). Falling back to in-memory cache.", exc)
            self._redis = None
            if self._pool:
                await self._pool.disconnect()  # type: ignore[attr-defined]
            self._pool = None

    async def disconnect(self) -> None:
        if self._redis:
            await self._redis.close()
        if self._pool:
            await self._pool.disconnect()  # type: ignore[attr-defined]
        self._redis = None
        self._pool = None
        logger.info("Disconnected Redis cache backend")

    def is_connected(self) -> bool:
        return self._redis is not None

    async def get(self, key: str) -> Optional[Any]:
        if not self._redis:
            return None
        try:
            value = await self._redis.get(key)
            if value is None:
                return None
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return pickle.loads(value)
        except Exception as exc:  # pragma: no cover - redis failure
            logger.debug("Cache get error for %s: %s", key, exc)
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        if not self._redis:
            return False
        try:
            try:
                serialized = json.dumps(value)
            except (TypeError, ValueError):
                serialized = pickle.dumps(value)
            if ttl is not None and ttl > 0:
                await self._redis.setex(key, ttl, serialized)
            else:
                await self._redis.set(key, serialized)
            return True
        except Exception as exc:  # pragma: no cover - redis failure
            logger.debug("Cache set error for %s: %s", key, exc)
            return False

    async def delete(self, key: str) -> bool:
        if not self._redis:
            return False
        try:
            await self._redis.delete(key)
            return True
        except Exception as exc:  # pragma: no cover - redis failure
            logger.debug("Cache delete error for %s: %s", key, exc)
            return False

    async def clear_pattern(self, pattern: str) -> int:
        if not self._redis:
            return 0
        try:
            keys: List[str] = []
            async for key in self._redis.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                await self._redis.delete(*keys)
            return len(keys)
        except Exception as exc:  # pragma: no cover - redis failure
            logger.debug("Cache pattern clear error for %s: %s", pattern, exc)
            return 0

    async def get_stats(self) -> Optional[Dict[str, Any]]:
        if not self._redis:
            return None
        try:
            info = await self._redis.info()
            return {
                "backend": "redis",
                "used_memory": info.get("used_memory_human", "N/A"),
                "connected_clients": info.get("connected_clients", 0),
                "total_commands": info.get("total_commands_processed", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": info.get("keyspace_hits", 0)
                / max(info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0), 1),
            }
        except Exception as exc:  # pragma: no cover - redis failure
            logger.debug("Failed to fetch Redis stats: %s", exc)
            return None


_cache: Optional[BaseCache] = None


async def get_cache() -> BaseCache:
    """Get or create cache instance based on configuration."""
    global _cache
    if _cache is not None:
        return _cache

    settings = get_settings()
    backend = (settings.cache_backend or "memory").lower()

    if backend == "redis":
        cache: BaseCache = RedisCache(settings=settings)
        await cache.connect()
        if not cache.is_connected():
            logger.warning("Redis backend unavailable, falling back to in-memory cache.")
            cache = InMemoryCache(settings=settings)
            await cache.connect()
    else:
        cache = InMemoryCache(settings=settings)
        await cache.connect()

    _cache = cache
    return _cache


async def close_cache() -> None:
    """Close cache connection."""
    global _cache
    if _cache:
        await _cache.disconnect()
        _cache = None
