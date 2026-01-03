"""
Environment configuration for Symphony/Monad integration.
Securely manages API keys and settings.
"""

from typing import Optional
from .config import get_settings

settings = get_settings()

# Symphony API Configuration
SYMPHONY_API_KEY: Optional[str] = settings.symphony_api_key
SYMPHONY_AGENT_ID: Optional[str] = settings.symphony_milf_agent_id  # Default is MILF
SYMPHONY_BASE_URL: str = "https://api.symphony.io"
SYMPHONY_STRATEGY_ID: str = settings.symphony_strategy_id

# Multi-Agent Configuration
SYMPHONY_MILF_KEY = settings.symphony_api_key
SYMPHONY_MILF_ID = settings.symphony_milf_agent_id

SYMPHONY_AGDG_KEY = settings.symphony_api_key
SYMPHONY_AGDG_ID = settings.symphony_agdg_agent_id

SYMPHONY_DEGEN_KEY = settings.symphony_api_key
SYMPHONY_DEGEN_ID = settings.symphony_degen_agent_id

SYMPHONY_MIT_KEY = settings.symphony_api_key
SYMPHONY_MIT_ID = settings.symphony_mit_agent_id

AGENTS_CONFIG = {
    "MILF": {"id": SYMPHONY_MILF_ID, "key": SYMPHONY_MILF_KEY, "type": "SWAP", "chain": "MONAD"},
    "AGDG": {"id": SYMPHONY_AGDG_ID, "key": SYMPHONY_AGDG_KEY, "type": "PERPS", "chain": "BASE"},
    "DEGEN": {"id": SYMPHONY_DEGEN_ID, "key": SYMPHONY_DEGEN_KEY, "type": "PERPS", "chain": "BASE"},
    "MIT": {"id": SYMPHONY_MIT_ID, "key": SYMPHONY_MIT_KEY, "type": "PERPS", "chain": "BASE"},
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
