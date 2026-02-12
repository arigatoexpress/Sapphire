"""
Shared Utilities for Sapphire Trading Platform

Common utility functions used across all bot services.
"""

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def get_service_name() -> str:
    """Get the current service name from environment."""
    return os.getenv("SERVICE_NAME", os.getenv("K_SERVICE", "unknown"))


def get_revision() -> str:
    """Get the current Cloud Run revision."""
    return os.getenv("K_REVISION", "local")


def get_timestamp_us() -> int:
    """Get current timestamp in microseconds."""
    return int(time.time() * 1_000_000)


def utc_now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)


def format_price(price: float, decimals: int = 2) -> str:
    """Format a price with proper decimals."""
    return f"${price:,.{decimals}f}"


def format_percent(value: float, decimals: int = 2) -> str:
    """Format a percentage."""
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.{decimals}f}%"


def format_quantity(qty: float, decimals: int = 4) -> str:
    """Format a quantity."""
    return f"{qty:.{decimals}f}"


def calculate_pnl_percent(entry_price: float, current_price: float, is_long: bool) -> float:
    """Calculate P&L percentage for a position."""
    if entry_price <= 0:
        return 0.0
    if is_long:
        return ((current_price - entry_price) / entry_price) * 100
    else:
        return ((entry_price - current_price) / entry_price) * 100


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divide two numbers, returning default if denominator is zero."""
    if denominator == 0:
        return default
    return numerator / denominator


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value between min and max."""
    return max(min_val, min(max_val, value))


class ServiceConfig:
    """
    Centralized configuration for a bot service.
    Reads from environment variables with sensible defaults.
    """

    def __init__(self, platform: str):
        self.platform = platform
        self.service_name = get_service_name()
        self.revision = get_revision()

        # GCP Configuration
        self.project_id = os.getenv("GCP_PROJECT_ID", "sapphire-479610")

        # Trading Configuration
        self.trading_enabled = os.getenv("TRADING_ENABLED", "true").lower() == "true"
        self.max_position_size = float(
            os.getenv("MAX_POSITION_SIZE", "20")
        )  # Reduced for low collateral
        self.max_positions = int(os.getenv("MAX_POSITIONS", "5"))

        # Loop Configuration
        self.loop_interval_ms = int(os.getenv("LOOP_INTERVAL_MS", "1000"))
        self.signal_timeout_ms = int(os.getenv("SIGNAL_TIMEOUT_MS", "5000"))

        # Logging
        self.log_level = os.getenv("LOG_LEVEL", "INFO")

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "platform": self.platform,
            "service_name": self.service_name,
            "revision": self.revision,
            "trading_enabled": self.trading_enabled,
            "max_position_size": self.max_position_size,
            "max_positions": self.max_positions,
            "loop_interval_ms": self.loop_interval_ms,
        }


def setup_logging(level: str = "INFO"):
    """Configure logging for a service."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Reduce noise from some libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
