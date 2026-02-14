"""
V2.3 Connection Pool Manager - Optimize API connection reuse for speed.

For < 100ms execution times, we need:
1. Persistent HTTP connections (no TCP handshake overhead)
2. Connection pooling per platform
3. Automatic connection health checks
4. Connection recycling on failures

Target: Eliminate 20-50ms of TCP/TLS handshake overhead
"""

import asyncio
import logging
import time
from typing import Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)


class PlatformConnectionPool:
    """
    Manages persistent HTTP connections for platform APIs.

    Benefits:
    - Eliminates TCP handshake (3-way handshake = 10-20ms)
    - Eliminates TLS handshake (additional 20-30ms)
    - Reuses keep-alive connections
    - Reduces API latency by 30-50ms per request
    """

    def __init__(self, platform: str, max_connections: int = 10):
        self.platform = platform
        self.max_connections = max_connections
        self.session: Optional[aiohttp.ClientSession] = None
        self.created_at = None
        self.request_count = 0
        self.last_used = None

        # Connection pool settings optimized for speed
        self.connector_kwargs = {
            "limit": max_connections,
            "limit_per_host": max_connections,
            "ttl_dns_cache": 300,  # Cache DNS for 5 min
            "enable_cleanup_closed": True,
            "force_close": False,  # Keep connections alive
            "keepalive_timeout": 30,  # Keep alive for 30s
        }

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session with persistent connections."""

        # Create new session if needed
        if self.session is None or self.session.closed:
            connector = aiohttp.TCPConnector(**self.connector_kwargs)

            timeout = aiohttp.ClientTimeout(
                total=10,  # Total timeout
                connect=3,  # Connection timeout
                sock_read=5,  # Socket read timeout
            )

            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={
                    "User-Agent": "Sapphire-Focused",
                    "Connection": "keep-alive"
                }
            )

            self.created_at = time.time()
            logger.info(f"⚡ [CONNECTION POOL] Created session for {self.platform}")

        self.last_used = time.time()
        self.request_count += 1

        return self.session

    async def close(self):
        """Close the connection pool."""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info(
                f"🔌 [CONNECTION POOL] Closed {self.platform} "
                f"(requests: {self.request_count})"
            )

    def get_stats(self) -> dict:
        """Get connection pool statistics."""
        age = time.time() - self.created_at if self.created_at else 0
        idle = time.time() - self.last_used if self.last_used else 0

        return {
            "platform": self.platform,
            "active": self.session is not None and not self.session.closed,
            "requests": self.request_count,
            "age_seconds": int(age),
            "idle_seconds": int(idle)
        }


class ConnectionPoolManager:
    """
    Manages connection pools for all platforms.

    V2.3 Independent Traders - each platform gets optimized pool.
    """

    def __init__(self):
        self.pools: Dict[str, PlatformConnectionPool] = {}

        # Platform-specific connection pool sizes
        # HFT platforms get larger pools
        self.pool_sizes = {
            "aster": 15,
            "lighter": 10,
        }

    def get_pool(self, platform: str) -> PlatformConnectionPool:
        """Get or create connection pool for platform."""
        platform_lower = platform.lower()

        if platform_lower not in self.pools:
            pool_size = self.pool_sizes.get(platform_lower, 10)
            self.pools[platform_lower] = PlatformConnectionPool(
                platform=platform_lower,
                max_connections=pool_size
            )
            logger.info(
                f"⚡ [CONNECTION POOL] Initialized {platform} "
                f"(max_connections: {pool_size})"
            )

        return self.pools[platform_lower]

    async def close_all(self):
        """Close all connection pools."""
        for pool in self.pools.values():
            await pool.close()

        self.pools.clear()

    def get_all_stats(self) -> dict:
        """Get statistics for all connection pools."""
        return {
            platform: pool.get_stats()
            for platform, pool in self.pools.items()
        }


# Global connection pool manager
_manager = None


def get_connection_pool_manager() -> ConnectionPoolManager:
    """Get the global connection pool manager."""
    global _manager
    if _manager is None:
        _manager = ConnectionPoolManager()
        logger.info("⚡ [CONNECTION POOL] Manager initialized for V2.3")
    return _manager


async def get_platform_session(platform: str) -> aiohttp.ClientSession:
    """
    Get persistent HTTP session for a platform.

    Usage:
        session = await get_platform_session("aster")
        async with session.get(url) as response:
            data = await response.json()

    Benefits:
    - 30-50ms latency reduction per request
    - Automatic connection pooling
    - Keep-alive connections
    """
    manager = get_connection_pool_manager()
    pool = manager.get_pool(platform)
    return await pool.get_session()
