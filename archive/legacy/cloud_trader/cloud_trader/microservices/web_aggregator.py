"""Web aggregator service for sapphire-web.

This module initializes the state aggregator for the web service,
which subscribes to events from all trading microservices and
maintains a unified view for the dashboard.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

from .events import ServiceStateAggregator

if TYPE_CHECKING:
    from ..trading_service import TradingService

logger = logging.getLogger(__name__)

# Global aggregator instance
_aggregator: Optional[ServiceStateAggregator] = None


async def initialize_web_aggregator(trading_service: "TradingService") -> ServiceStateAggregator:
    """Initialize the web aggregator for sapphire-web service.

    This should only be called when SERVE_FRONTEND=true.

    Args:
        trading_service: TradingService instance

    Returns:
        ServiceStateAggregator instance
    """
    global _aggregator

    if _aggregator is not None:
        logger.warning("⚠️ Web aggregator already initialized")
        return _aggregator

    project_id = trading_service._settings.gcp_project_id

    if not project_id:
        logger.error("❌ Cannot initialize web aggregator: GCP_PROJECT_ID not set")
        raise ValueError("GCP_PROJECT_ID required for web aggregator")

    logger.info("🌐 Initializing Web Aggregator for sapphire-web...")

    _aggregator = ServiceStateAggregator(
        project_id=project_id,
        subscription_name="sapphire-web-events",
        topic_name="sapphire-service-events",
        enable_firestore=True,  # Enable persistence
    )

    # Start subscribing to events
    await _aggregator.start()

    logger.info("✅ Web Aggregator initialized and subscribed to service events")

    # Store aggregator on trading service for API access
    trading_service._state_aggregator = _aggregator

    return _aggregator


def get_web_aggregator() -> Optional[ServiceStateAggregator]:
    """Get the global web aggregator instance.

    Returns:
        ServiceStateAggregator or None if not initialized
    """
    return _aggregator


async def shutdown_web_aggregator():
    """Shutdown the web aggregator."""
    global _aggregator

    if _aggregator:
        logger.info("🛑 Shutting down web aggregator...")
        await _aggregator.close()
        _aggregator = None
