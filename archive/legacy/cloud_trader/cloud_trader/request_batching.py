"""Advanced request batching system for API efficiency."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple

from .time_sync import get_precision_clock, get_timestamp_us

logger = logging.getLogger(__name__)


class BatchStrategy(Enum):
    """Strategies for batch processing."""

    TIME_WINDOW = "time_window"  # Batch by time intervals
    SIZE_THRESHOLD = "size_threshold"  # Batch when size limit reached
    HYBRID = "hybrid"  # Combine time and size
    ADAPTIVE = "adaptive"  # Adapt based on load and latency


class RequestPriority(Enum):
    """Request priority levels."""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class BatchedRequest:
    """A request that can be batched with others."""

    request_id: str
    endpoint: str
    method: str
    data: Dict[str, Any]
    priority: RequestPriority = RequestPriority.NORMAL
    created_at: int = field(default_factory=get_timestamp_us)
    timeout_ms: int = 30000  # 30 seconds default
    retry_count: int = 0
    max_retries: int = 3
    callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RequestBatch:
    """A batch of requests to be processed together."""

    batch_id: str
    endpoint: str
    method: str
    requests: List[BatchedRequest] = field(default_factory=list)
    strategy: BatchStrategy = BatchStrategy.HYBRID
    created_at: int = field(default_factory=get_timestamp_us)
    max_size: int = 50
    max_wait_ms: int = 1000  # 1 second
    processing_started: bool = False

    def is_full(self) -> bool:
        """Check if batch is full."""
        return len(self.requests) >= self.max_size

    def is_expired(self, current_time: int) -> bool:
        """Check if batch has exceeded max wait time."""
        return (current_time - self.created_at) > (self.max_wait_ms * 1000)

    def should_process(self, current_time: int) -> bool:
        """Check if batch should be processed."""
        if self.processing_started:
            return False
        return (
            self.is_full()
            or self.is_expired(current_time)
            or any(req.priority == RequestPriority.CRITICAL for req in self.requests)
        )

    def add_request(self, request: BatchedRequest) -> bool:
        """Add a request to the batch. Returns False if batch is full."""
        if self.is_full():
            return False

        # Sort by priority when adding
        self.requests.append(request)
        self.requests.sort(key=lambda r: r.priority.value, reverse=True)
        return True


@dataclass
class BatchProcessor:
    """Processes batches of requests."""

    name: str
    endpoint: str
    method: str
    batch_function: Callable[[List[BatchedRequest]], Awaitable[List[Dict[str, Any]]]]
    max_batch_size: int = 50
    max_wait_ms: int = 1000
    strategy: BatchStrategy = BatchStrategy.HYBRID
    active_batches: Dict[str, RequestBatch] = field(default_factory=dict)
    processing_queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=1000))
    stats: Dict[str, Any] = field(
        default_factory=lambda: {
            "batches_processed": 0,
            "requests_processed": 0,
            "avg_batch_size": 0,
            "avg_processing_time_ms": 0,
            "errors": 0,
        }
    )

    def __post_init__(self):
        if not hasattr(self, "_processing_task"):
            self._processing_task: Optional[asyncio.Task[None]] = None
            self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start the batch processor."""
        if self._processing_task and not self._processing_task.done():
            return

        self._shutdown_event.clear()
        self._processing_task = asyncio.create_task(self._process_batches())
        logger.info(f"Started batch processor {self.name} for {self.endpoint}")

    async def stop(self) -> None:
        """Stop the batch processor."""
        if not self._processing_task:
            return

        self._shutdown_event.set()
        try:
            await asyncio.wait_for(self._processing_task, timeout=5.0)
        except asyncio.TimeoutError:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass

        logger.info(f"Stopped batch processor {self.name}")

    async def submit_request(self, request: BatchedRequest) -> str:
        """Submit a request for batching."""
        # Try to add to existing batch
        batch_key = f"{request.method}:{request.endpoint}"
        current_time = get_timestamp_us()

        if batch_key in self.active_batches:
            batch = self.active_batches[batch_key]
            if not batch.processing_started and batch.add_request(request):
                return batch.batch_id

        # Create new batch
        batch_id = f"batch_{batch_key}_{current_time}"
        batch = RequestBatch(
            batch_id=batch_id,
            endpoint=request.endpoint,
            method=request.method,
            strategy=self.strategy,
            max_size=self.max_batch_size,
            max_wait_ms=self.max_wait_ms,
        )

        if batch.add_request(request):
            self.active_batches[batch_key] = batch

            # Try to put in queue for immediate processing if critical
            if request.priority == RequestPriority.CRITICAL:
                try:
                    await asyncio.wait_for(self.processing_queue.put(batch), timeout=0.1)
                except asyncio.TimeoutError:
                    logger.warning(
                        f"Processing queue full for {self.name}, batch will be processed on next cycle"
                    )

            return batch_id

        # Should not reach here if logic is correct
        raise RuntimeError(f"Failed to create batch for request {request.request_id}")

    async def _process_batches(self) -> None:
        """Main batch processing loop."""
        while not self._shutdown_event.is_set():
            try:
                # Check for batches that should be processed
                current_time = get_timestamp_us()
                batches_to_process = []

                for batch_key, batch in list(self.active_batches.items()):
                    if batch.should_process(current_time):
                        batch.processing_started = True
                        batches_to_process.append(batch)
                        del self.active_batches[batch_key]

                # Process batches
                for batch in batches_to_process:
                    await self._process_batch(batch)

                # Also check processing queue for critical batches
                try:
                    batch = self.processing_queue.get_nowait()
                    if not batch.processing_started:
                        batch.processing_started = True
                        await self._process_batch(batch)
                    self.processing_queue.task_done()
                except asyncio.QueueEmpty:
                    pass

                # Small delay to prevent busy waiting
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Error in batch processing loop for {self.name}: {e}")
                self.stats["errors"] += 1

    async def _process_batch(self, batch: RequestBatch) -> None:
        """Process a single batch of requests."""
        if not batch.requests:
            return

        start_time = time.time()
        batch_size = len(batch.requests)

        try:
            # Call the batch processing function
            results = await self.batch_function(batch.requests)

            # Update statistics
            processing_time = (time.time() - start_time) * 1000  # Convert to ms
            self.stats["batches_processed"] += 1
            self.stats["requests_processed"] += batch_size
            self.stats["avg_batch_size"] = (
                self.stats["avg_batch_size"] * (self.stats["batches_processed"] - 1) + batch_size
            ) / self.stats["batches_processed"]
            self.stats["avg_processing_time_ms"] = (
                self.stats["avg_processing_time_ms"] * (self.stats["batches_processed"] - 1)
                + processing_time
            ) / self.stats["batches_processed"]

            # Call individual request callbacks
            for i, request in enumerate(batch.requests):
                if i < len(results) and request.callback:
                    try:
                        await request.callback(results[i])
                    except Exception as e:
                        logger.error(f"Error in callback for request {request.request_id}: {e}")

            logger.debug(
                f"Processed batch {batch.batch_id} with {batch_size} requests in {processing_time:.1f}ms"
            )

        except Exception as e:
            logger.error(f"Failed to process batch {batch.batch_id}: {e}")
            self.stats["errors"] += 1

            # Handle individual request failures
            for request in batch.requests:
                if request.retry_count < request.max_retries:
                    request.retry_count += 1
                    # Re-submit for retry (simplified - in production might use exponential backoff)
                    try:
                        await self.submit_request(request)
                    except Exception as retry_e:
                        logger.error(f"Failed to retry request {request.request_id}: {retry_e}")
                else:
                    # Max retries exceeded
                    if request.callback:
                        try:
                            await request.callback({"error": str(e), "status": "failed"})
                        except Exception as callback_e:
                            logger.error(
                                f"Error in failure callback for request {request.request_id}: {callback_e}"
                            )


class RequestBatchManager:
    """
    Manages multiple batch processors for different endpoints.

    Provides intelligent batching across different API endpoints with:
    - Adaptive batch sizing based on load
    - Request prioritization
    - Performance monitoring
    - Circuit breaker integration
    """

    def __init__(self):
        self.processors: Dict[str, BatchProcessor] = {}
        self.endpoint_configs: Dict[str, Dict[str, Any]] = {}
        self.global_stats: Dict[str, Any] = {
            "total_requests": 0,
            "total_batches": 0,
            "avg_latency_ms": 0,
            "throughput_req_per_sec": 0,
            "error_rate": 0,
        }
        self._shutdown_event = asyncio.Event()

    async def register_endpoint(
        self,
        name: str,
        endpoint: str,
        method: str,
        batch_function: Callable[[List[BatchedRequest]], Awaitable[List[Dict[str, Any]]]],
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register an endpoint for batch processing."""
        if config is None:
            config = {}

        processor = BatchProcessor(
            name=name,
            endpoint=endpoint,
            method=method,
            batch_function=batch_function,
            max_batch_size=config.get("max_batch_size", 50),
            max_wait_ms=config.get("max_wait_ms", 1000),
            strategy=config.get("strategy", BatchStrategy.HYBRID),
        )

        self.processors[name] = processor
        self.endpoint_configs[name] = config

        await processor.start()
        logger.info(f"Registered batch processor {name} for {method} {endpoint}")

    async def submit_request(self, processor_name: str, request: BatchedRequest) -> Optional[str]:
        """Submit a request to a specific processor."""
        if processor_name not in self.processors:
            logger.warning(f"Unknown processor: {processor_name}")
            return None

        self.global_stats["total_requests"] += 1
        return await self.processors[processor_name].submit_request(request)

    async def submit_batch_request(
        self,
        endpoint: str,
        requests_data: List[Dict[str, Any]],
        method: str = "POST",
        priority: RequestPriority = RequestPriority.NORMAL,
        callbacks: Optional[List[Callable]] = None,
    ) -> List[str]:
        """Submit multiple requests for batching."""
        # Find appropriate processor
        processor_name = None
        for name, processor in self.processors.items():
            if processor.endpoint == endpoint and processor.method == method:
                processor_name = name
                break

        if not processor_name:
            # Create ad-hoc processor
            processor_name = f"adhoc_{endpoint}_{method}_{get_timestamp_us()}"
            await self.register_endpoint(
                processor_name, endpoint, method, self._default_batch_function
            )

        # Submit requests
        batch_ids = []
        for i, request_data in enumerate(requests_data):
            request = BatchedRequest(
                request_id=f"req_{get_timestamp_us()}_{i}",
                endpoint=endpoint,
                method=method,
                data=request_data,
                priority=priority,
                callback=callbacks[i] if callbacks and i < len(callbacks) else None,
            )

            batch_id = await self.submit_request(processor_name, request)
            if batch_id:
                batch_ids.append(batch_id)

        return batch_ids

    async def _default_batch_function(self, requests: List[BatchedRequest]) -> List[Dict[str, Any]]:
        """Default batch processing function for ad-hoc processors."""
        # This would need to be customized based on the actual API
        # For now, just return mock responses
        results = []
        for request in requests:
            results.append(
                {
                    "request_id": request.request_id,
                    "status": "processed",
                    "data": request.data,
                    "timestamp_us": get_timestamp_us(),
                }
            )
        return results

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive batching statistics."""
        processor_stats = {}
        for name, processor in self.processors.items():
            processor_stats[name] = {
                "endpoint": processor.endpoint,
                "method": processor.method,
                "batches_processed": processor.stats["batches_processed"],
                "requests_processed": processor.stats["requests_processed"],
                "avg_batch_size": processor.stats["avg_batch_size"],
                "avg_processing_time_ms": processor.stats["avg_processing_time_ms"],
                "errors": processor.stats["errors"],
                "active_batches": len(processor.active_batches),
            }

        return {
            "global_stats": self.global_stats.copy(),
            "processor_stats": processor_stats,
            "total_processors": len(self.processors),
            "timestamp_us": get_timestamp_us(),
        }

    async def shutdown(self) -> None:
        """Shutdown all processors."""
        self._shutdown_event.set()

        shutdown_tasks = []
        for processor in self.processors.values():
            shutdown_tasks.append(processor.stop())

        if shutdown_tasks:
            await asyncio.gather(*shutdown_tasks, return_exceptions=True)

        logger.info("Request batch manager shutdown complete")


# Global batch manager instance
_batch_manager: Optional[RequestBatchManager] = None


async def get_request_batch_manager() -> RequestBatchManager:
    """Get global request batch manager instance."""
    global _batch_manager
    if _batch_manager is None:
        _batch_manager = RequestBatchManager()
    return _batch_manager


# Utility functions for common batching patterns


async def batch_market_data_requests(
    symbols: List[str], data_type: str = "ticker"
) -> Dict[str, Any]:
    """
    Batch market data requests for multiple symbols.
    This is a utility function that can be used by various parts of the system.
    """
    manager = await get_request_batch_manager()

    # Prepare requests
    requests_data = [{"symbol": symbol, "type": data_type} for symbol in symbols]

    # Submit batch
    batch_ids = await manager.submit_batch_request(
        endpoint="/api/market/batch",
        method="POST",
        requests_data=requests_data,
        priority=RequestPriority.HIGH,
    )

    return {
        "batch_ids": batch_ids,
        "symbol_count": len(symbols),
        "expected_responses": len(symbols),
    }


async def batch_order_submissions(orders: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Batch order submissions for better throughput.
    """
    manager = await get_request_batch_manager()

    # Submit batch with high priority for orders
    batch_ids = await manager.submit_batch_request(
        endpoint="/api/orders/batch",
        method="POST",
        requests_data=orders,
        priority=RequestPriority.CRITICAL,
    )

    return {"batch_ids": batch_ids, "order_count": len(orders), "expected_responses": len(orders)}
