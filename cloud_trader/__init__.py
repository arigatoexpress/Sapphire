"""Lean Cloud Trader core package."""

from .config import Settings, get_settings
from .optimization.bandit import EpsilonGreedyBandit
from .optimization.trailing import TrailingConfig, optimise_trailing_stop
# from .service import TradingService  # Removed to prevent heavy load

__all__ = [
    "Settings",
    "get_settings",
    # "TradingService",
    "EpsilonGreedyBandit",
    "TrailingConfig",
    "optimise_trailing_stop",
]
