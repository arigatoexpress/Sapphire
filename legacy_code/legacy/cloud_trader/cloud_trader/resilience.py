"""
Resilience Utilities - Retry, Backoff, Timeout, and Bulkhead Patterns

World-class resilience patterns for production-grade reliability.
"""

import asyncio
import functools
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Tuple, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,)


@dataclass
class RetryStats:
    """Statistics for retry operations."""

    total_attempts: int = 0
    successful_attempts: int = 0
    failed_attempts: int = 0
    total_retries: int = 0
    total_delay_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_attempts == 0:
            return 0.0
        return self.successful_attempts / self.total_attempts


# Global retry statistics
_retry_stats: dict[str, RetryStats] = {}


def get_retry_stats(func_name: Optional[str] = None) -> dict[str, RetryStats]:
    """Get retry statistics for a function or all functions."""
    if func_name:
        return {func_name: _retry_stats.get(func_name, RetryStats())}
    return _retry_stats.copy()


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None,
):
    """
    Decorator for retry with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts (including first try)
        base_delay: Initial delay in seconds
        max_delay: Maximum delay between retries
        exponential_base: Base for exponential backoff (e.g., 2 = double each time)
        jitter: Add randomness to prevent thundering herd
        retryable_exceptions: Tuple of exception types to retry on
        on_retry: Optional callback called on each retry with (exception, attempt)

    Example:
        @with_retry(max_attempts=3, base_delay=0.5)
        async def fetch_data():
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        func_name = f"{func.__module__}.{func.__qualname__}"

        # Initialize stats
        if func_name not in _retry_stats:
            _retry_stats[func_name] = RetryStats()

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> T:
            stats = _retry_stats[func_name]
            last_exception: Optional[Exception] = None

            for attempt in range(1, max_attempts + 1):
                stats.total_attempts += 1

                try:
                    result = await func(*args, **kwargs)
                    stats.successful_attempts += 1
                    return result

                except retryable_exceptions as e:
                    last_exception = e
                    stats.failed_attempts += 1

                    if attempt < max_attempts:
                        # Calculate delay with exponential backoff
                        delay = min(base_delay * (exponential_base ** (attempt - 1)), max_delay)

                        # Add jitter to prevent thundering herd
                        if jitter:
                            delay *= 0.5 + random.random()

                        stats.total_retries += 1
                        stats.total_delay_seconds += delay

                        logger.warning(
                            f"⚡ Retry {attempt}/{max_attempts} for {func_name}: "
                            f"{type(e).__name__}: {str(e)[:100]}. Waiting {delay:.2f}s"
                        )

                        # Call retry callback if provided
                        if on_retry:
                            try:
                                on_retry(e, attempt)
                            except Exception as callback_err:
                                logger.debug(f"Retry callback error: {callback_err}")

                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"❌ All {max_attempts} attempts failed for {func_name}: "
                            f"{type(e).__name__}: {str(e)[:200]}"
                        )

            # All retries exhausted
            if last_exception:
                raise last_exception
            raise RuntimeError(f"Unexpected state: no result and no exception for {func_name}")

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> T:
            # For sync functions, run in event loop
            return asyncio.get_event_loop().run_until_complete(async_wrapper(*args, **kwargs))

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def with_timeout(seconds: float, error_message: Optional[str] = None):
    """
    Decorator to add timeout to async functions.

    Args:
        seconds: Timeout in seconds
        error_message: Optional custom error message

    Example:
        @with_timeout(5.0)
        async def slow_operation():
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                msg = error_message or f"Operation {func.__qualname__} timed out after {seconds}s"
                logger.error(f"⏱️ {msg}")
                raise asyncio.TimeoutError(msg)

        return wrapper

    return decorator


class Bulkhead:
    """
    Bulkhead pattern to limit concurrent executions.
    Prevents one failing component from exhausting all resources.

    Example:
        bulkhead = Bulkhead(max_concurrent=10)

        async with bulkhead:
            await risky_operation()
    """

    def __init__(self, max_concurrent: int, name: str = "default"):
        self.max_concurrent = max_concurrent
        self.name = name
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active = 0
        self._rejected = 0

    async def __aenter__(self):
        acquired = self._semaphore.locked()
        if acquired:
            self._rejected += 1
            logger.warning(
                f"🚧 Bulkhead '{self.name}' at capacity ({self._active}/{self.max_concurrent})"
            )

        await self._semaphore.acquire()
        self._active += 1
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._active -= 1
        self._semaphore.release()
        return False

    def get_stats(self) -> dict:
        return {
            "name": self.name,
            "max_concurrent": self.max_concurrent,
            "active": self._active,
            "available": self.max_concurrent - self._active,
            "rejected": self._rejected,
        }


# Pre-configured bulkheads for common use cases
exchange_bulkhead = Bulkhead(max_concurrent=20, name="exchange_api")
ai_bulkhead = Bulkhead(max_concurrent=5, name="ai_inference")
database_bulkhead = Bulkhead(max_concurrent=50, name="database")


async def with_fallback(
    primary: Callable[..., T],
    fallback: Callable[..., T],
    *args: Any,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    **kwargs: Any,
) -> T:
    """
    Execute primary function, falling back on failure.

    Args:
        primary: Primary function to execute
        fallback: Fallback function if primary fails
        *args: Arguments to pass to both functions
        exceptions: Exception types that trigger fallback
        **kwargs: Keyword arguments to pass to both functions

    Example:
        result = await with_fallback(
            fetch_from_primary_api,
            fetch_from_backup_api,
            symbol="BTC-USDC"
        )
    """
    try:
        return await primary(*args, **kwargs)
    except exceptions as e:
        logger.warning(f"⚡ Primary failed ({type(e).__name__}), using fallback")
        return await fallback(*args, **kwargs)
