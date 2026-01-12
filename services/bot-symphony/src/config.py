"""
Minimal configuration for Symphony bot microservice.
Loads settings from environment variables.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Settings:
    """Symphony configuration settings loaded from environment."""

    # Symphony API
    symphony_api_key: Optional[str] = None
    symphony_milf_agent_id: Optional[str] = None
    symphony_agdg_agent_id: Optional[str] = None
    symphony_degen_agent_id: Optional[str] = None
    symphony_mit_agent_id: Optional[str] = None
    symphony_strategy_id: str = "default"

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
        symphony_api_key=os.getenv("SYMPHONY_API_KEY"),
        symphony_milf_agent_id=os.getenv("SYMPHONY_MILF_AGENT_ID"),
        symphony_agdg_agent_id=os.getenv("SYMPHONY_AGDG_AGENT_ID"),
        symphony_degen_agent_id=os.getenv("SYMPHONY_DEGEN_AGENT_ID"),
        symphony_mit_agent_id=os.getenv("SYMPHONY_MIT_AGENT_ID"),
        symphony_strategy_id=os.getenv("SYMPHONY_STRATEGY_ID", "default"),
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
