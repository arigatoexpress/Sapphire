"""Standalone health check functions for self-healing system."""

import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)


async def check_database_health() -> bool:
    """Standalone database health check function."""
    try:
        from .storage import get_storage

        storage = await get_storage()
        if storage and storage.is_ready():
            # Try a simple SQL query that doesn't depend on existing tables
            async with storage._session_factory() as session:
                await session.execute(text("SELECT 1"))
            return True
        return False
    except Exception as e:
        logger.debug(f"Database health check failed: {e}")
        return False


async def check_redis_health() -> bool:
    """Standalone Redis health check function."""
    try:
        from .cache import get_cache

        cache = await get_cache()
        if cache and cache.is_connected():
            # Try a simple set/get operation
            test_key = "health_check_test"
            await cache.set(test_key, "test", ttl=10)
            result = await cache.get(test_key)
            return result == "test"
        return False
    except Exception as e:
        logger.debug(f"Redis health check failed: {e}")
        return False


async def check_platform_health(service, platform: str) -> dict:
    """
    V2.3: Independent platform health check for autonomous traders.

    Each platform trader needs to verify:
    1. Platform API connectivity
    2. Authentication/credentials valid
    3. Circuit breaker status
    4. Recent execution latency

    Returns dict with health status and metrics.
    """
    health = {
        "platform": platform,
        "healthy": False,
        "latency_ms": 0,
        "circuit_breaker": "unknown",
        "last_trade": None,
        "error": None
    }

    try:
        # Check circuit breaker status
        if hasattr(service, 'platform_router') and service.platform_router:
            from .platform_router import PlatformType
            platform_enum = PlatformType(platform.lower())
            breaker = service.platform_router.circuit_breakers.get(platform_enum)
            if breaker:
                health["circuit_breaker"] = breaker.state.value
                if breaker.state.value == "open":
                    health["error"] = "Circuit breaker OPEN - platform unavailable"
                    return health

        # Platform-specific connectivity checks
        import time
        start = time.time()

        if platform.lower() == "drift" and hasattr(service, 'drift_client'):
            # Quick Drift health check - get account info
            if service.drift_client:
                positions = await service.drift_client.get_positions()
                health["healthy"] = True
                health["last_trade"] = len(positions) if positions else 0

        elif platform.lower() == "hyperliquid" and hasattr(service, 'hyperliquid_client'):
            # Quick Hyperliquid health check
            if service.hyperliquid_client:
                # Try to get user state
                user_state = await service.hyperliquid_client.get_user_state()
                health["healthy"] = True if user_state else False

        elif platform.lower() == "aster" and hasattr(service, '_exchange_client'):
            # Quick Aster health check - get server time
            if service._exchange_client:
                server_time = await service._exchange_client.get_server_time()
                health["healthy"] = True if server_time else False

        elif platform.lower() == "symphony":
            # Symphony health check - verify agent manager
            if hasattr(service, 'symphony_manager') and service.symphony_manager:
                health["healthy"] = True

        elif platform.lower() == "lighter":
            # Lighter health check - verify client initialized
            if hasattr(service, 'lighter_client') and service.lighter_client:
                health["healthy"] = True

        health["latency_ms"] = int((time.time() - start) * 1000)

    except Exception as e:
        logger.warning(f"Platform health check failed for {platform}: {e}")
        health["error"] = str(e)
        health["healthy"] = False

    return health


async def check_all_platforms_health(service) -> dict:
    """
    V2.3: Check health of all independent platform traders.
    Returns comprehensive health status for autonomous trading system.
    """
    platforms = ["drift", "hyperliquid", "aster", "symphony", "lighter"]
    results = {}

    for platform in platforms:
        results[platform] = await check_platform_health(service, platform)

    # Calculate overall system health
    healthy_count = sum(1 for p in results.values() if p["healthy"])
    total_count = len(platforms)

    return {
        "platforms": results,
        "healthy_platforms": healthy_count,
        "total_platforms": total_count,
        "system_health": healthy_count / total_count if total_count > 0 else 0,
        "autonomous_trading_ready": healthy_count >= 1  # At least 1 platform working
    }
