"""
Environment configuration for Aster/Monad integration.
Securely manages API keys and settings.
"""

from typing import Optional

from config import get_settings

settings = get_settings()

# Aster API Configuration
import os

ASTER_API_KEY: Optional[str] = settings.aster_api_key
# Allow override via env var for microservices
ASTER_AGENT_ID: Optional[str] = (
    os.getenv("ASTER_AGENT_ID") or settings.aster_milf_agent_id
)  # Default is MILF
ASTER_BASE_URL: str = "https://api.aster.io"
ASTER_STRATEGY_ID: str = settings.aster_strategy_id

# Multi-Agent Configuration
ASTER_MILF_KEY = settings.aster_api_key
ASTER_MILF_ID = settings.aster_milf_agent_id

ASTER_AGDG_KEY = settings.aster_api_key
ASTER_AGDG_ID = settings.aster_agdg_agent_id

ASTER_DEGEN_KEY = settings.aster_api_key
ASTER_DEGEN_ID = settings.aster_degen_agent_id

ASTER_MIT_KEY = settings.aster_api_key
ASTER_MIT_ID = settings.aster_mit_agent_id

AGENTS_CONFIG = {
    # Active Aster Agents
    "MILF": {
        "id": ASTER_MILF_ID,
        "key": ASTER_MILF_KEY,
        "type": "SWAP",
        "chain": "MONAD",
        "priority": True,
        "emoji": "🦾",
    },
    "AGDG": {
        "id": ASTER_AGDG_ID,
        "key": ASTER_AGDG_KEY,
        "type": "PERPS",
        "chain": "BASE",
        "emoji": "🦅",
    },
}

# MIT (Monad Implementation Treasury) Settings
MIT_FUND_NAME: str = settings.mit_fund_name
MIT_FUND_DESCRIPTION: str = settings.mit_fund_description
MIT_AUTO_SUBSCRIBE: bool = settings.mit_auto_subscribe

# Trading Configuration
MIT_DEFAULT_LEVERAGE: int = settings.mit_default_leverage
MIT_MAX_POSITION_SIZE_USDC: float = settings.mit_max_position_size_usdc
MIT_ACTIVATION_THRESHOLD: int = 0  # Lowered to 0 for immediate production trading

# Risk Management
MIT_ENABLE_STOP_LOSS: bool = settings.mit_enable_stop_loss
MIT_ENABLE_TAKE_PROFIT: bool = settings.mit_enable_take_profit
MIT_DEFAULT_SL_PERCENT: float = settings.mit_default_sl_percent
MIT_DEFAULT_TP_PERCENT: float = settings.mit_default_tp_percent


def validate_aster_config() -> bool:
    """Validate that Aster is properly configured."""
    if not ASTER_API_KEY:
        return False
    if not ASTER_API_KEY.startswith("sk_live_"):
        return False
    return True


def get_aster_config() -> dict:
    """Get current Aster configuration (without exposing keys)."""
    return {
        "configured": validate_aster_config(),
        "api_key_set": bool(ASTER_API_KEY),
        "api_key_prefix": ASTER_API_KEY[:12] + "..." if ASTER_API_KEY else None,
        "base_url": ASTER_BASE_URL,
        "fund_name": MIT_FUND_NAME,
        "auto_subscribe": MIT_AUTO_SUBSCRIBE,
        "default_leverage": MIT_DEFAULT_LEVERAGE,
        "max_position_size": MIT_MAX_POSITION_SIZE_USDC,
        "activation_threshold": MIT_ACTIVATION_THRESHOLD,
    }
