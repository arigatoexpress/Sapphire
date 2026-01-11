"""
Sapphire V2 API Routers
Refactored API layer - domain-specific routers.
"""

from .agents import router as agents_router
from .analytics import router as analytics_router
from .portfolio import router as portfolio_router
from .trading import router as trading_router

__all__ = ["trading_router", "agents_router", "portfolio_router", "analytics_router"]
