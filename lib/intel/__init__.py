"""Market intelligence: stablecoins, econ calendar, political signals, liquidation, order flow."""

__all__ = [
    "MarketIntelligence",
    "MarketIntelSnapshot",
    "collect",
    "load_latest_snapshot",
]


def __getattr__(name: str):
    if name in __all__:
        from lib.intel import market_intelligence

        return getattr(market_intelligence, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
