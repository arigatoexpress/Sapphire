"""
Retry mechanism with exponential backoff for resilient operations.
"""

import asyncio
import logging
import random
import time
from functools import wraps
from typing import Any, Callable, Optional, Type, Union

logger = logging.getLogger(__name__)

class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
        jitter: bool = True,
        retry_exceptions: tuple = (Exception,),
        retry_condition: Optional[Callable[[Exception], bool]] = None
    ):
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter
        self.retry_exceptions = retry_exceptions
        self.retry_condition = retry_condition

def calculate_delay(attempt: int, config: RetryConfig) -> float:
    """Calculate delay for the current attempt using exponential backoff."""
    delay = config.initial_delay * (config.backoff_factor ** (attempt - 1))
    delay = min(delay, config.max_delay)

    if config.jitter:
        # Add random jitter to prevent thundering herd
        delay = delay * (0.5 + random.random() * 0.5)

    return delay

def should_retry(exception: Exception, config: RetryConfig) -> bool:
    """Determine if an exception should trigger a retry."""
    # Check if exception type matches
    if not isinstance(exception, config.retry_exceptions):
        return False

    # Check custom retry condition
    if config.retry_condition and not config.retry_condition(exception):
        return False

    return True

async def retry_async(
    func: Callable,
    *args,
    config: RetryConfig = None,
    **kwargs
) -> Any:
    """Execute an async function with retry logic."""
    if config is None:
        config = RetryConfig()

    last_exception = None

    for attempt in range(1, config.max_attempts + 1):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                # Run sync function in thread pool
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, func, *args, **kwargs)

        except Exception as e:
            last_exception = e

            if attempt == config.max_attempts:
                logger.error(f"All {config.max_attempts} attempts failed for {func.__name__}")
                raise last_exception

            if not should_retry(e, config):
                logger.debug(f"Exception {type(e).__name__} not retryable for {func.__name__}")
                raise last_exception

            delay = calculate_delay(attempt, config)
            logger.warning(
                f"Attempt {attempt}/{config.max_attempts} failed for {func.__name__}: {e}. "
                f"Retrying in {delay:.2f}s"
            )
            await asyncio.sleep(delay)

    # This should never be reached, but just in case
    raise last_exception

def retry(config: Optional[RetryConfig] = None):
    """Decorator for adding retry logic to functions."""
    def decorator(func: Callable) -> Callable:
        retry_config = config or RetryConfig()

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await retry_async(func, *args, config=retry_config, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For sync functions, create an async wrapper
            async def async_func():
                return func(*args, **kwargs)

            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(retry_async(async_func, config=retry_config))
            finally:
                loop.close()

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator

# Pre-configured retry configurations for common scenarios
API_RETRY_CONFIG = RetryConfig(
    max_attempts=5,
    initial_delay=1.0,
    max_delay=30.0,
    backoff_factor=2.0,
    retry_exceptions=(Exception,),
    retry_condition=lambda e: not isinstance(e, (ValueError, TypeError))  # Don't retry validation errors
)

DATABASE_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    initial_delay=0.5,
    max_delay=10.0,
    backoff_factor=2.0,
    retry_exceptions=(Exception,)
)

REDIS_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    initial_delay=0.1,
    max_delay=5.0,
    backoff_factor=1.5,
    retry_exceptions=(Exception,)
)

EXTERNAL_API_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    initial_delay=2.0,
    max_delay=60.0,
    backoff_factor=2.0,
    retry_exceptions=(Exception,)
)

# Convenience decorators
def retry_api(func: Callable) -> Callable:
    """Decorator for API calls with retry logic."""
    return retry(API_RETRY_CONFIG)(func)

def retry_database(func: Callable) -> Callable:
    """Decorator for database operations with retry logic."""
    return retry(DATABASE_RETRY_CONFIG)(func)

def retry_redis(func: Callable) -> Callable:
    """Decorator for Redis operations with retry logic."""
    return retry(REDIS_RETRY_CONFIG)(func)

def retry_external_api(func: Callable) -> Callable:
    """Decorator for external API calls with retry logic."""
    return retry(EXTERNAL_API_RETRY_CONFIG)(func)
