"""Optimized multi-level caching system for cloud native AI."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import pickle
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Dict, Optional, Union

try:
    import aioredis  # type: ignore
except ImportError:
    aioredis = None

from .config import get_settings
from .optimized_config import get_optimized_settings

logger = logging.getLogger(__name__)


class OptimizedCache:
    """Multi-level caching system (L1: Memory, L2: Redis, L3: BigQuery)."""

    def __init__(self, settings=None, optimized_settings=None):
        self._settings = settings or get_settings()
        self._optimized_settings = optimized_settings or get_optimized_settings()

        # L1: In-memory cache
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._l1_ttl = self._optimized_settings.l1_cache_ttl

        # L2: Redis cache
        self._redis_client = None
        self._l2_ttl = self._optimized_settings.l2_cache_ttl

        # L3: BigQuery fallback (lazy loaded)
        self._bigquery_streamer = None

        # Cache statistics
        self._stats = {
            "l1_hits": 0,
            "l1_misses": 0,
            "l2_hits": 0,
            "l2_misses": 0,
            "l3_hits": 0,
            "l3_misses": 0,
        }

    async def initialize(self) -> None:
        """Initialize cache layers."""
        # Initialize Redis if available
        if aioredis and self._settings.redis_url:
            try:
                self._redis_client = aioredis.from_url(
                    self._settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    max_connections=20,
                    retry_on_timeout=True,
                )
                logger.info("✅ Redis cache initialized")
            except Exception as e:
                logger.warning(f"Redis cache initialization failed: {e}")

        # Start cleanup task
        asyncio.create_task(self._cleanup_expired_entries())

        logger.info("✅ Optimized cache initialized")

    def _make_cache_key(self, *args, **kwargs) -> str:
        """Create deterministic cache key from function arguments."""
        key_data = {"args": args, "kwargs": sorted(kwargs.items())}
        key_str = json.dumps(key_data, default=str, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()[:16]

    async def get(self, key: str) -> Optional[Any]:
        """Get value from multi-level cache."""
        try:
            # Validate input
            if not key or not isinstance(key, str):
                logger.warning(f"Invalid cache key: {key}")
                return None

            # L1: Memory cache
            if key in self._memory_cache:
                entry = self._memory_cache[key]
                if datetime.now() < entry["expires"]:
                    self._stats["l1_hits"] += 1
                    return entry["value"]
                else:
                    # Clean up expired entry
                    try:
                        del self._memory_cache[key]
                    except KeyError:
                        pass  # Already removed

            # L2: Redis cache
            if self._redis_client:
                try:
                    redis_data = await asyncio.wait_for(
                        self._redis_client.get(f"cache:{key}"),
                        timeout=2.0,  # 2 second timeout for Redis
                    )
                    if redis_data:
                        self._stats["l2_hits"] += 1
                        try:
                            data = json.loads(redis_data)
                            # Validate data structure
                            if isinstance(data, dict) and "value" in data and "expires" in data:
                                # Promote to L1
                                self._memory_cache[key] = {
                                    "value": data["value"],
                                    "expires": datetime.fromisoformat(data["expires"]),
                                }
                                return data["value"]
                            else:
                                logger.warning(f"Invalid Redis data structure for key {key}")
                        except (json.JSONDecodeError, ValueError, KeyError) as e:
                            logger.warning(f"Failed to parse Redis data for key {key}: {e}")
                except asyncio.TimeoutError:
                    logger.warning(f"Redis get timeout for key {key}")
                    self._stats["l2_misses"] += 1
                except Exception as e:
                    logger.warning(f"Redis get error for key {key}: {e}")
                    self._stats["l2_misses"] += 1

            # L3: BigQuery (not implemented for reads in this version)
            self._stats["l3_misses"] += 1
            return None

        except Exception as e:
            logger.error(f"Unexpected error in cache get for key {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> bool:
        """Set value in multi-level cache."""
        try:
            # Validate inputs
            if not key or not isinstance(key, str):
                logger.warning(f"Invalid cache key: {key}")
                return False

            if ttl_seconds is None:
                ttl_seconds = self._l1_ttl
            elif ttl_seconds <= 0:
                logger.warning(f"Invalid TTL for key {key}: {ttl_seconds}")
                return False

            expires = datetime.now() + timedelta(seconds=ttl_seconds)

            # L1: Memory cache (always try this first)
            try:
                self._memory_cache[key] = {"value": value, "expires": expires}
            except Exception as e:
                logger.error(f"Failed to set L1 cache for key {key}: {e}")
                return False

            # L2: Redis cache
            if self._redis_client:
                try:
                    cache_data = {"value": value, "expires": expires.isoformat()}
                    await asyncio.wait_for(
                        self._redis_client.setex(
                            f"cache:{key}", ttl_seconds, json.dumps(cache_data, default=str)
                        ),
                        timeout=2.0,  # 2 second timeout
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"Redis set timeout for key {key}")
                except Exception as e:
                    logger.warning(f"Redis set error for key {key}: {e}")

            # L3: BigQuery (async write, not blocking)
            if self._bigquery_streamer:
                try:
                    asyncio.create_task(self._write_to_bigquery(key, value, expires))
                except Exception as e:
                    logger.debug(f"Failed to queue BigQuery write for key {key}: {e}")

            return True

        except Exception as e:
            logger.error(f"Unexpected error in cache set for key {key}: {e}")
            return False

    async def delete(self, key: str) -> None:
        """Delete value from all cache levels."""
        # L1
        self._memory_cache.pop(key, None)

        # L2
        if self._redis_client:
            try:
                await self._redis_client.delete(f"cache:{key}")
            except Exception as e:
                logger.debug(f"Redis delete error: {e}")

    async def clear(self) -> None:
        """Clear all cache levels."""
        # L1
        self._memory_cache.clear()

        # L2
        if self._redis_client:
            try:
                await self._redis_client.flushdb()
            except Exception as e:
                logger.debug(f"Redis clear error: {e}")

    async def _cleanup_expired_entries(self) -> None:
        """Background task to clean expired L1 entries."""
        while True:
            try:
                await asyncio.sleep(60)  # Clean every minute

                now = datetime.now()
                expired_keys = [
                    key for key, entry in self._memory_cache.items() if now >= entry["expires"]
                ]

                for key in expired_keys:
                    del self._memory_cache[key]

                if expired_keys:
                    logger.debug(f"Cleaned {len(expired_keys)} expired cache entries")

            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")
                await asyncio.sleep(5)

    async def _write_to_bigquery(self, key: str, value: Any, expires: datetime) -> None:
        """Write cache entry to BigQuery for persistence."""
        if not self._bigquery_streamer:
            return

        try:
            await self._bigquery_streamer.stream_optimized(
                "cache_entries",
                timestamp=datetime.now(),
                data={
                    "cache_key": key,
                    "value": json.dumps(value, default=str),
                    "expires": expires,
                    "size_bytes": len(pickle.dumps(value)),
                },
            )
        except Exception as e:
            logger.debug(f"BigQuery cache write error: {e}")

    def get_stats(self) -> Dict[str, int]:
        """Get cache performance statistics."""
        total_requests = sum(self._stats.values())
        if total_requests == 0:
            hit_rate = 0.0
        else:
            hits = self._stats["l1_hits"] + self._stats["l2_hits"] + self._stats["l3_hits"]
            hit_rate = hits / total_requests

        return {
            **self._stats,
            "total_requests": total_requests,
            "hit_rate": hit_rate,
            "memory_entries": len(self._memory_cache),
        }


def optimized_cache(ttl_seconds: Optional[int] = None, key_func: Optional[Callable] = None):
    """Decorator for optimized caching of async functions."""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Skip caching for certain conditions
            if kwargs.get("no_cache", False):
                return await func(*args, **kwargs)

            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__name__}:{_make_cache_key(*args, **kwargs)}"

            # Get from cache
            cache = _global_cache
            if cache:
                cached_result = await cache.get(cache_key)
                if cached_result is not None:
                    return cached_result

            # Execute function
            result = await func(*args, **kwargs)

            # Cache result
            if cache and result is not None:
                await cache.set(cache_key, result, ttl_seconds)

            return result

        return wrapper

    return decorator


def _make_cache_key(*args, **kwargs) -> str:
    """Create cache key from function arguments."""
    key_data = {"args": args, "kwargs": sorted(kwargs.items())}
    key_str = json.dumps(key_data, default=str, sort_keys=True)
    return hashlib.sha256(key_str.encode()).hexdigest()[:16]


# Global cache instance
_global_cache: Optional[OptimizedCache] = None


async def get_optimized_cache() -> OptimizedCache:
    """Get or create optimized cache instance."""
    global _global_cache
    if _global_cache is None:
        _global_cache = OptimizedCache()
        await _global_cache.initialize()
    return _global_cache


async def close_optimized_cache() -> None:
    """Close optimized cache."""
    global _global_cache
    if _global_cache:
        await _global_cache.close()
        _global_cache = None


# Example usage decorators
@optimized_cache(ttl_seconds=300)  # 5 minutes
async def get_market_data(symbol: str, timeframe: str) -> Dict[str, Any]:
    """Example cached function for market data."""
    # Implementation would fetch from exchange
    return {"symbol": symbol, "price": 50000.0}


@optimized_cache(ttl_seconds=60)  # 1 minute
async def get_portfolio_status() -> Dict[str, Any]:
    """Example cached function for portfolio status."""
    # Implementation would calculate portfolio metrics
    return {"total_value": 100000.0, "pnl": 5000.0}


if __name__ == "__main__":
    # Test cache initialization
    async def test():
        cache = await get_optimized_cache()
        print("✅ Optimized cache initialized")
        print(f"Stats: {cache.get_stats()}")

        # Test basic operations
        await cache.set("test_key", {"data": "test_value"})
        result = await cache.get("test_key")
        print(f"Cache test result: {result}")

        await close_optimized_cache()

    asyncio.run(test())
