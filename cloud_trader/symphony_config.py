"""
Environment configuration for Symphony/Monad integration.
Securely manages API keys and settings.
"""

import os
from typing import Optional

# Symphony API Configuration
SYMPHONY_API_KEY: Optional[str] = os.getenv("SYMPHONY_API_KEY")
SYMPHONY_BASE_URL: str = os.getenv("SYMPHONY_BASE_URL", "https://api.symphony.io")

# MIT (Monad Implementation Treasury) Settings
MIT_FUND_NAME: str = os.getenv("MIT_FUND_NAME", "Sapphire MIT Agent")
MIT_FUND_DESCRIPTION: str = os.getenv(
    "MIT_FUND_DESCRIPTION",
    "Autonomous AI trading agent powered by Sapphire intelligence on Monad blockchain",
)
MIT_AUTO_SUBSCRIBE: bool = os.getenv("MIT_AUTO_SUBSCRIBE", "true").lower() == "true"

# Trading Configuration
MIT_DEFAULT_LEVERAGE: int = int(os.getenv("MIT_DEFAULT_LEVERAGE", "3"))
MIT_MAX_POSITION_SIZE_USDC: float = float(os.getenv("MIT_MAX_POSITION_SIZE_USDC", "100"))
MIT_ACTIVATION_THRESHOLD: int = 5  # Trades required for activation

# Risk Management
MIT_ENABLE_STOP_LOSS: bool = os.getenv("MIT_ENABLE_STOP_LOSS", "true").lower() == "true"
MIT_ENABLE_TAKE_PROFIT: bool = os.getenv("MIT_ENABLE_TAKE_PROFIT", "true").lower() == "true"
MIT_DEFAULT_SL_PERCENT: float = float(os.getenv("MIT_DEFAULT_SL_PERCENT", "0.03"))  # 3%
MIT_DEFAULT_TP_PERCENT: float = float(os.getenv("MIT_DEFAULT_TP_PERCENT", "0.08"))  # 8%


def validate_symphony_config() -> bool:
    """Validate that Symphony is properly configured."""
    if not SYMPHONY_API_KEY:
        return False
    if not SYMPHONY_API_KEY.startswith("sk_live_"):
        return False
    return True


def get_symphony_config() -> dict:
    """Get current Symphony configuration (without exposing keys)."""
    return {
        "configured": validate_symphony_config(),
        "api_key_set": bool(SYMPHONY_API_KEY),
        "api_key_prefix": SYMPHONY_API_KEY[:12] + "..." if SYMPHONY_API_KEY else None,
        "base_url": SYMPHONY_BASE_URL,
        "fund_name": MIT_FUND_NAME,
        "auto_subscribe": MIT_AUTO_SUBSCRIBE,
        "default_leverage": MIT_DEFAULT_LEVERAGE,
        "max_position_size": MIT_MAX_POSITION_SIZE_USDC,
        "activation_threshold": MIT_ACTIVATION_THRESHOLD,
    }
