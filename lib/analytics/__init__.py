"""Sapphire analytics module: correlations, signal enhancement, portfolio risk."""

from .correlation import (
    CorrelationEngine,
    CorrelationMatrix,
    DecorrelationEvent,
)

__all__ = [
    "CorrelationMatrix",
    "CorrelationEngine",
    "DecorrelationEvent",
]

try:
    from .risk_engine import PortfolioMetrics, RiskEngine, kelly_size
    __all__ += ["PortfolioMetrics", "RiskEngine", "kelly_size"]
except ImportError:
    pass

try:
    from .signal_enhancer import EnhancedSignal, SignalEnhancer
    __all__ += ["EnhancedSignal", "SignalEnhancer"]
except ImportError:
    pass
