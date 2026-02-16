# Core Module __init__.py
"""
Sapphire V2 Core Module
Clean, modular architecture for autonomous trading.
"""
from .orchestrator import TradingOrchestrator
from .trading_loop import TradingLoop

__all__ = ["TradingOrchestrator", "TradingLoop"]
