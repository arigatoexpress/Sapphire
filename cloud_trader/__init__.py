"""Lean Cloud Trader core package.

Keep imports lightweight so unit tests can import individual modules without
pulling in the full runtime dependency graph.
"""

from .config import Settings, get_settings

__all__ = ["Settings", "get_settings", "TradingService"]


def __getattr__(name: str):
    if name == "TradingService":
        # Lazy import avoids failing module import for tests that don't need the
        # heavyweight trading runtime and its optional legacy config modules.
        from .trading_service import TradingService

        return TradingService
    raise AttributeError(name)
