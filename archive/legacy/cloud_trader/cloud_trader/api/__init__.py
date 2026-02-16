# API Module __init__.py
"""
Sapphire V2 API Layer
Clean, domain-specific routers.
"""
from .routers import agents_router, analytics_router, portfolio_router, trading_router

__all__ = ["trading_router", "agents_router", "portfolio_router", "analytics_router"]
