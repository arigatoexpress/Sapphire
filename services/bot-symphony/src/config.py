"""
Minimal configuration for Aster bot microservice.
Loads settings from environment variables.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Settings:
    """Aster configuration settings loaded from environment."""

    # Aster API
    aster_api_key: Optional[str] = None
    aster_milf_agent_id: Optional[str] = None
    aster_agdg_agent_id: Optional[str] = None
    aster_degen_agent_id: Optional[str] = None
    aster_mit_agent_id: Optional[str] = None
    aster_strategy_id: str = "default"

    # MIT Fund Settings
    mit_fund_name: str = "Sapphire MIT Fund"
    mit_fund_description: str = "Sapphire AI-powered trading fund on Monad"
    mit_auto_subscribe: bool = True

    # Trading Configuration
    mit_default_leverage: int = 2
    mit_max_position_size_usdc: float = 100.0

    # Risk Management
    mit_enable_stop_loss: bool = True
    mit_enable_take_profit: bool = True
    mit_default_sl_percent: float = 5.0
    mit_default_tp_percent: float = 10.0


def get_settings() -> Settings:
    """Load settings from environment variables."""
    return Settings(
        aster_api_key=os.getenv("ASTER_API_KEY"),
        aster_milf_agent_id=os.getenv("ASTER_MILF_AGENT_ID"),
        aster_agdg_agent_id=os.getenv("ASTER_AGDG_AGENT_ID"),
        aster_degen_agent_id=os.getenv("ASTER_DEGEN_AGENT_ID"),
        aster_mit_agent_id=os.getenv("ASTER_MIT_AGENT_ID"),
        aster_strategy_id=os.getenv("ASTER_STRATEGY_ID", "default"),
        mit_fund_name=os.getenv("MIT_FUND_NAME", "Sapphire MIT Fund"),
        mit_fund_description=os.getenv(
            "MIT_FUND_DESCRIPTION", "Sapphire AI-powered trading fund on Monad"
        ),
        mit_auto_subscribe=os.getenv("MIT_AUTO_SUBSCRIBE", "true").lower() == "true",
        mit_default_leverage=int(os.getenv("MIT_DEFAULT_LEVERAGE", "2")),
        mit_max_position_size_usdc=float(os.getenv("MIT_MAX_POSITION_SIZE_USDC", "100.0")),
        mit_enable_stop_loss=os.getenv("MIT_ENABLE_STOP_LOSS", "true").lower() == "true",
        mit_enable_take_profit=os.getenv("MIT_ENABLE_TAKE_PROFIT", "true").lower() == "true",
        mit_default_sl_percent=float(os.getenv("MIT_DEFAULT_SL_PERCENT", "5.0")),
        mit_default_tp_percent=float(os.getenv("MIT_DEFAULT_TP_PERCENT", "10.0")),
    )
