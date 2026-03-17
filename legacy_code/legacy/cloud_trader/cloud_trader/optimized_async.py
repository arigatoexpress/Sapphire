"""Optimized async architecture with connection pooling and concurrency."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypeVar

import aiohttp
import httpx
from aiohttp import ClientTimeout, TCPConnector

from .config import get_settings
from .optimized_config import get_optimized_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class OptimizedHTTPClient:
    """Optimized HTTP client with connection pooling and intelligent retries."""

    def __init__(self, settings=None, optimized_settings=None):
        self._settings = settings or get_settings()
        self._optimized_settings = optimized_settings or get_optimized_settings()

        # Connection pool configuration
        self._connector = TCPConnector(
            limit=self._optimized_settings.connection_pool_size,
            limit_per_host=self._optimized_settings.connection_pool_size // 2,
            ttl_dns_cache=300,
            use_dns_cache=True,
            keepalive_timeout=60,
            enable_cleanup_closed=True,
        )

        self._timeout = ClientTimeout(
            total=self._optimized_settings.network_timeout,
            connect=self._optimized_settings.network_timeout * 0.3,
            sock_read=self._optimized_settings.network_timeout * 0.7,
        )

        self._session: Optional[aiohttp.ClientSession] = None

        # Request statistics
        self._stats = {
            "requests_total": 0,
            "requests_success": 0,
            "requests_error": 0,
            "avg_response_time": 0.0,
        }

    async def initialize(self) -> None:
        """Initialize HTTP client session."""
        try:
            if self._session is None:
                self._session = aiohttp.ClientSession(
                    connector=self._connector,
                    timeout=self._timeout,
                    headers={
                        "User-Agent": "SapphireTrader/1.0",
                        "Accept-Encoding": "gzip, deflate",
                    },
                )
            logger.info("✅ Optimized HTTP client initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize HTTP client: {e}")
            raise

    async def close(self) -> None:
        """Close HTTP client session."""
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("✅ Optimized HTTP client closed")

    @asynccontextmanager
    async def request(self, method: str, url: str, **kwargs):
        """Context manager for optimized HTTP requests."""
        if not self._session:
            try:
                await self.initialize()
            except Exception as init_error:
                logger.error(
                    f"Failed to initialize session for request {method} {url}: {init_error}"
                )
                raise

        start_time = asyncio.get_event_loop().time()

        try:
            self._stats["requests_total"] += 1

            async with self._session.request(method, url, **kwargs) as response:
                response_time = asyncio.get_event_loop().time() - start_time

                # Update statistics
                if response.status < 400:
                    self._stats["requests_success"] += 1
                else:
                    self._stats["requests_error"] += 1

                # Update average response time
                total_requests = self._stats["requests_total"]
                self._stats["avg_response_time"] = (
                    (self._stats["avg_response_time"] * (total_requests - 1)) + response_time
                ) / total_requests

                response.raise_for_status()
                yield response

        except aiohttp.ClientError as client_error:
            logger.warning(f"HTTP client error for {method} {url}: {client_error}")
            # Increment error stats
            self._stats["requests_error"] += 1
            raise
        except asyncio.TimeoutError as timeout_error:
            logger.warning(f"HTTP timeout for {method} {url}: {timeout_error}")
            self._stats["requests_error"] += 1
            raise
        except Exception as e:
            logger.error(f"Unexpected HTTP request error for {method} {url}: {e}")
            self._stats["requests_error"] += 1
            raise

    async def get(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """Optimized GET request."""
        async with self.request("GET", url, **kwargs) as response:
            return response

    async def post(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """Optimized POST request."""
        async with self.request("POST", url, **kwargs) as response:
            return response

    def get_stats(self) -> Dict[str, Any]:
        """Get HTTP client statistics."""
        return self._stats.copy()


class OptimizedAsyncPool:
    """Optimized async worker pool for CPU-intensive tasks."""

    def __init__(self, max_workers: Optional[int] = None, optimized_settings=None):
        self._optimized_settings = optimized_settings or get_optimized_settings()
        self._max_workers = max_workers or self._optimized_settings.async_workers
        self._semaphore = asyncio.Semaphore(self._max_workers)
        self._executor = None  # For CPU-bound tasks

        self._active_tasks = 0
        self._completed_tasks = 0
        self._stats = {
            "active_tasks": 0,
            "completed_tasks": 0,
            "queued_tasks": 0,
            "avg_completion_time": 0.0,
        }

    async def submit(self, coro: Callable[[], Awaitable[T]]) -> T:
        """Submit async task with concurrency control."""
        async with self._semaphore:
            self._active_tasks += 1
            self._stats["active_tasks"] = self._active_tasks

            start_time = asyncio.get_event_loop().time()

            try:
                result = await coro()
                completion_time = asyncio.get_event_loop().time() - start_time

                # Update statistics
                self._completed_tasks += 1
                total_completed = self._stats["completed_tasks"] + 1
                self._stats["completed_tasks"] = total_completed
                self._stats["avg_completion_time"] = (
                    (self._stats["avg_completion_time"] * (total_completed - 1)) + completion_time
                ) / total_completed

                return result

            finally:
                self._active_tasks -= 1
                self._stats["active_tasks"] = self._active_tasks

    async def map(self, coro_func: Callable[[Any], Awaitable[T]], items: List[Any]) -> List[T]:
        """Map async function over items with concurrency control."""
        tasks = [self.submit(lambda item=item: coro_func(item)) for item in items]
        return await asyncio.gather(*tasks, return_exceptions=True)

    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        return self._stats.copy()


class OptimizedMCPClient:
    """Optimized MCP client with connection pooling and batching."""

    def __init__(self, base_url: str, optimized_settings=None):
        self._base_url = base_url.rstrip("/")
        self._optimized_settings = optimized_settings or get_optimized_settings()

        # HTTP client for requests
        self._http_client = OptimizedHTTPClient(optimized_settings=self._optimized_settings)

        # Async pool for concurrent operations
        self._async_pool = OptimizedAsyncPool(
            max_workers=self._optimized_settings.async_workers,
            optimized_settings=self._optimized_settings,
        )

        # Message batching
        self._message_batch: List[Dict[str, Any]] = []
        self._batch_size = self._optimized_settings.message_batch_size

        # Session management
        self._session_id: Optional[str] = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize optimized MCP client."""
        await self._http_client.initialize()
        logger.info("✅ Optimized MCP client initialized")

    async def close(self) -> None:
        """Close optimized MCP client."""
        # Flush any pending messages
        if self._message_batch:
            await self._flush_batch()

        await self._http_client.close()
        logger.info("✅ Optimized MCP client closed")

    async def publish_optimized(self, message: Dict[str, Any]) -> None:
        """Publish message with batching optimization."""
        self._message_batch.append(message)

        if len(self._message_batch) >= self._batch_size:
            await self._flush_batch()

    async def _flush_batch(self) -> None:
        """Flush message batch to MCP coordinator."""
        if not self._message_batch:
            return

        batch = self._message_batch.copy()
        self._message_batch.clear()

        async def send_batch():
            try:
                payload = {
                    "messages": batch,
                    "compressed": self._optimized_settings.message_compression,
                }

                async with self._http_client.post(
                    f"{self._base_url}/batch", json=payload
                ) as response:
                    return await response.json()

            except Exception as e:
                logger.error(f"Batch publish failed: {e}")
                # Re-queue failed messages
                self._message_batch.extend(batch)
                raise

        await self._async_pool.submit(send_batch)

    async def get_status(self) -> Dict[str, Any]:
        """Get optimized status from MCP coordinator."""

        async def fetch_status():
            async with self._http_client.get(f"{self._base_url}/status") as response:
                return await response.json()

        return await self._async_pool.submit(fetch_status)

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive client statistics."""
        return {
            "http_client": self._http_client.get_stats(),
            "async_pool": self._async_pool.get_stats(),
            "batched_messages": len(self._message_batch),
            "batch_size": self._batch_size,
        }


class OptimizedPubSubClient:
    """Optimized Pub/Sub client with batching and connection pooling."""

    def __init__(self, settings=None, optimized_settings=None):
        self._settings = settings or get_settings()
        self._optimized_settings = optimized_settings or get_optimized_settings()

        # Batch message queues
        self._message_queues: Dict[str, List[Dict[str, Any]]] = {}
        self._batch_sizes: Dict[str, int] = {}

        # Async pool for publishing
        self._publish_pool = OptimizedAsyncPool(
            max_workers=self._optimized_settings.async_io_workers,
            optimized_settings=self._optimized_settings,
        )

        # Statistics
        self._stats = {
            "messages_published": 0,
            "batches_sent": 0,
            "publish_errors": 0,
        }

    async def initialize(self) -> None:
        """Initialize optimized Pub/Sub client."""
        # Initialize topic batch sizes
        self._batch_sizes = {
            "decisions": self._optimized_settings.message_batch_size,
            "positions": self._optimized_settings.message_batch_size,
            "reasoning": self._optimized_settings.message_batch_size,
        }

        # Initialize queues
        for topic in self._batch_sizes.keys():
            self._message_queues[topic] = []

        logger.info("✅ Optimized Pub/Sub client initialized")

    async def publish_batch(self, topic: str, message: Dict[str, Any]) -> None:
        """Publish message with batching optimization."""
        if topic not in self._message_queues:
            self._message_queues[topic] = []
            self._batch_sizes[topic] = self._optimized_settings.message_batch_size

        self._message_queues[topic].append(message)
        self._stats["messages_published"] += 1

        # Flush if batch is full
        if len(self._message_queues[topic]) >= self._batch_sizes[topic]:
            await self._flush_topic_batch(topic)

    async def _flush_topic_batch(self, topic: str) -> None:
        """Flush batch for specific topic."""
        if topic not in self._message_queues or not self._message_queues[topic]:
            return

        batch = self._message_queues[topic].copy()
        self._message_queues[topic].clear()

        async def publish_batch():
            try:
                # Compress batch if enabled
                if self._optimized_settings.message_compression:
                    # Implement compression logic here
                    pass

                # Publish to Pub/Sub (placeholder - implement actual publishing)
                logger.debug(f"Publishing batch of {len(batch)} messages to {topic}")

                self._stats["batches_sent"] += 1
                return True

            except Exception as e:
                logger.error(f"Batch publish failed for {topic}: {e}")
                self._stats["publish_errors"] += 1
                # Re-queue failed messages
                self._message_queues[topic].extend(batch)
                return False

        await self._publish_pool.submit(publish_batch)

    async def flush_all_batches(self) -> None:
        """Flush all pending message batches."""
        tasks = []
        for topic in self._message_queues.keys():
            if self._message_queues[topic]:
                tasks.append(self._flush_topic_batch(topic))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive client statistics."""
        return {
            **self._stats,
            "async_pool": self._publish_pool.get_stats(),
            "queued_messages": {topic: len(queue) for topic, queue in self._message_queues.items()},
        }


# Global instances
_http_client: Optional[OptimizedHTTPClient] = None
_mcp_client: Optional[OptimizedMCPClient] = None
_pubsub_client: Optional[OptimizedPubSubClient] = None


async def get_optimized_http_client() -> OptimizedHTTPClient:
    """Get or create optimized HTTP client."""
    global _http_client
    if _http_client is None:
        _http_client = OptimizedHTTPClient()
        await _http_client.initialize()
    return _http_client


async def get_optimized_mcp_client(base_url: str) -> OptimizedMCPClient:
    """Get or create optimized MCP client."""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = OptimizedMCPClient(base_url)
        await _mcp_client.initialize()
    return _mcp_client


async def get_optimized_pubsub_client() -> OptimizedPubSubClient:
    """Get or create optimized Pub/Sub client."""
    global _pubsub_client
    if _pubsub_client is None:
        _pubsub_client = OptimizedPubSubClient()
        await _pubsub_client.initialize()
    return _pubsub_client


async def close_optimized_clients() -> None:
    """Close all optimized clients."""
    global _http_client, _mcp_client, _pubsub_client

    tasks = []
    if _http_client:
        tasks.append(_http_client.close())
    if _mcp_client:
        tasks.append(_mcp_client.close())
    if _pubsub_client:
        tasks.append(_pubsub_client.flush_all_batches())

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    _http_client = None
    _mcp_client = None
    _pubsub_client = None


if __name__ == "__main__":
    # Test optimized async components
    async def test():
        # Test HTTP client
        http_client = await get_optimized_http_client()
        print("✅ Optimized HTTP client initialized")
        print(f"HTTP stats: {http_client.get_stats()}")

        # Test MCP client
        mcp_client = await get_optimized_mcp_client("http://localhost:8081")
        print("✅ Optimized MCP client initialized")
        print(f"MCP stats: {mcp_client.get_stats()}")

        # Test Pub/Sub client
        pubsub_client = await get_optimized_pubsub_client()
        print("✅ Optimized Pub/Sub client initialized")
        print(f"Pub/Sub stats: {pubsub_client.get_stats()}")

        await close_optimized_clients()
        print("✅ All optimized clients closed")

    asyncio.run(test())
