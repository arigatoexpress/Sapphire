"""Sapphire analytics: correlations, risk, backtesting, performance reporting."""

__all__: list[str] = []

try:
    from .correlation import CorrelationEngine, CorrelationMatrix, DecorrelationEvent
    __all__ += ["CorrelationEngine", "CorrelationMatrix", "DecorrelationEvent"]
except ImportError:
    pass

try:
    from .risk_engine import PortfolioMetrics, RiskEngine, kelly_size
    __all__ += ["PortfolioMetrics", "RiskEngine", "kelly_size"]
except ImportError:
    pass

try:
    from .backtest import BacktestConfig, Backtester, BacktestResult, Trade
    __all__ += ["BacktestConfig", "BacktestResult", "Backtester", "Trade"]
except ImportError:
    pass

try:
    from .performance import build_performance_report
    __all__ += ["build_performance_report"]
except ImportError:
    pass

try:
    from .signal_enhancer import EnhancedSignal, SignalEnhancer
    __all__ += ["EnhancedSignal", "SignalEnhancer"]
except ImportError:
    pass

try:
    from .cpcv import CPCVResult, CPCVSplitMetrics, cpcv_splits, run_cpcv_backtest
    __all__ += ["CPCVResult", "CPCVSplitMetrics", "cpcv_splits", "run_cpcv_backtest"]
except ImportError:
    pass

try:
    from .regime import GMMRegimeDetector, RegimePrediction, extract_features, get_detector
    __all__ += ["GMMRegimeDetector", "RegimePrediction", "extract_features", "get_detector"]
except ImportError:
    pass

try:
    from .vpin import (
        VPINCache,
        VPINReading,
        classify_vpin,
        compute_vpin,
        compute_vpin_from_bars,
        get_vpin_cache,
        vpin_reading,
    )
    __all__ += [
        "VPINCache", "VPINReading", "classify_vpin", "compute_vpin",
        "compute_vpin_from_bars", "get_vpin_cache", "vpin_reading",
    ]
except ImportError:
    pass
