"""Sapphire portfolio integrations: read-only connectors to external brokers."""

__all__: list[str] = []

try:
    from .robinhood import RobinhoodReader
    __all__ += ["RobinhoodReader"]
except ImportError:
    pass
