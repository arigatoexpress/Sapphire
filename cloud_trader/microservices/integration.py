"""Integration module to add microservices event publishing to TradingService.

This module monkey-patches TradingService methods to publish events to PubSub
for cross-service aggregation, without modifying the core trading logic.
"""

import asyncio
import functools
import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from .events import ServiceEventPublisher, ServiceEventType
from .identity import get_service_identity, validate_service_scope

if TYPE_CHECKING:
    from ..trading_service import TradingService

logger = logging.getLogger(__name__)


def add_microservices_support(trading_service: "TradingService") -> None:
    """Add microservices event publishing to a TradingService instance.

    This function:
    1. Initializes the event publisher
    2. Patches key methods to publish events
    3. Starts heartbeat loop
    4. Validates service scope

    Args:
        trading_service: TradingService instance to augment
    """
    # Get service identity
    identity = get_service_identity()
    logger.info(f"🆔 Initializing microservices support for: {identity}")

    # Initialize event publisher
    project_id = trading_service._settings.gcp_project_id
    enable_pubsub = trading_service._settings.enable_pubsub

    if not project_id:
        logger.warning("⚠️ GCP_PROJECT_ID not set, microservices events disabled")
        enable_pubsub = False

    publisher = ServiceEventPublisher(
        project_id=project_id or "sapphire-default",
        enable_pubsub=enable_pubsub,
    )

    # Store publisher on service
    trading_service._event_publisher = publisher
    trading_service._service_identity = identity

    logger.info(
        f"✅ Event publisher initialized (PubSub: {'ENABLED' if enable_pubsub else 'DISABLED'})"
    )

    # Patch methods to publish events
    _patch_balance_updates(trading_service, publisher)
    _patch_trade_execution(trading_service, publisher)
    _patch_position_updates(trading_service, publisher)

    # Start heartbeat loop
    asyncio.create_task(_heartbeat_loop(trading_service, publisher))

    logger.info(f"✅ Microservices support active for {identity}")


def _patch_balance_updates(
    trading_service: "TradingService", publisher: ServiceEventPublisher
):
    """Patch balance update methods to publish events."""
    original_update_balance = trading_service._update_account_balance

    @functools.wraps(original_update_balance)
    async def patched_update_balance(*args, **kwargs):
        # Call original
        result = await original_update_balance(*args, **kwargs)

        # Publish event
        try:
            identity = get_service_identity()
            platform = identity.service_type.value

            await publisher.publish_balance_update(
                platform=platform,
                balance=trading_service._account_balance,
                equity=getattr(trading_service._portfolio, "equity", None),
                available_margin=None,  # Could extract from exchange client
            )
        except Exception as e:
            logger.error(f"❌ Failed to publish balance update: {e}")

        return result

    # Replace method
    trading_service._update_account_balance = patched_update_balance
    logger.debug("✅ Patched: _update_account_balance")


def _patch_trade_execution(
    trading_service: "TradingService", publisher: ServiceEventPublisher
):
    """Patch trade execution to publish events."""
    original_execute_trade = trading_service._execute_trade_order

    @functools.wraps(original_execute_trade)
    async def patched_execute_trade(
        agent, symbol, side, quantity_float, thesis, is_closing=False, *args, **kwargs
    ):
        # Call original
        result = await original_execute_trade(
            agent, symbol, side, quantity_float, thesis, is_closing, *args, **kwargs
        )

        # Publish event (after successful execution)
        try:
            # Get price from recent trades or market data
            price = 0.0
            if hasattr(trading_service, "_recent_trades") and trading_service._recent_trades:
                # Find most recent trade for this symbol
                for trade in reversed(trading_service._recent_trades):
                    if trade.get("symbol") == symbol:
                        price = trade.get("price", 0.0)
                        break

            await publisher.publish_trade_executed(
                symbol=symbol,
                side=side,
                size=quantity_float,
                price=price,
                realized_pnl=None,  # Could extract from trade result
            )
        except Exception as e:
            logger.error(f"❌ Failed to publish trade execution: {e}")

        return result

    # Replace method
    trading_service._execute_trade_order = patched_execute_trade
    logger.debug("✅ Patched: _execute_trade_order")


def _patch_position_updates(
    trading_service: "TradingService", publisher: ServiceEventPublisher
):
    """Patch position updates to publish events."""
    original_sync_positions = trading_service._sync_positions_from_exchange

    @functools.wraps(original_sync_positions)
    async def patched_sync_positions(*args, **kwargs):
        # Call original
        result = await original_sync_positions(*args, **kwargs)

        # Publish events for all positions
        try:
            positions = trading_service._open_positions or {}

            for symbol, position in positions.items():
                await publisher.publish_position_update(
                    symbol=symbol,
                    size=position.get("quantity", 0.0),
                    entry_price=position.get("entry_price", 0.0),
                    unrealized_pnl=position.get("unrealized_pnl", 0.0),
                    leverage=position.get("leverage", 1.0),
                )
        except Exception as e:
            logger.error(f"❌ Failed to publish position updates: {e}")

        return result

    # Replace method
    trading_service._sync_positions_from_exchange = patched_sync_positions
    logger.debug("✅ Patched: _sync_positions_from_exchange")


async def _heartbeat_loop(
    trading_service: "TradingService", publisher: ServiceEventPublisher
):
    """Background task to publish periodic heartbeats."""
    logger.info("💓 Starting microservices heartbeat loop")

    start_time = asyncio.get_event_loop().time()

    while not trading_service._stop_event.is_set():
        try:
            # Collect stats
            stats = {
                "start_time": start_time,
                "balance": trading_service._account_balance,
                "positions": len(trading_service._open_positions or {}),
                "pending_orders": len(trading_service._pending_orders or {}),
            }

            # Publish heartbeat
            await publisher.publish_heartbeat(stats=stats)

        except Exception as e:
            logger.error(f"❌ Heartbeat error: {e}")

        # Wait 30 seconds
        await asyncio.sleep(30)

    logger.info("💓 Heartbeat loop stopped")


def validate_trading_scope(platform: str) -> None:
    """Validate that the current service should trade on the given platform.

    This is a safety check to prevent services from trading on wrong platforms.

    Args:
        platform: Platform name (e.g., "hyperliquid", "lighter", "drift")

    Raises:
        RuntimeError: If the service should not trade on this platform
    """
    validate_service_scope(platform)


def get_service_stats() -> Dict[str, Any]:
    """Get service identity and stats for debugging."""
    identity = get_service_identity()

    return {
        "service_name": identity.service_name,
        "service_type": identity.service_type.value,
        "region": identity.region,
        "is_trading_service": identity.is_trading_service,
        "is_web_service": identity.is_web_service,
        "emoji": identity.emoji,
    }
