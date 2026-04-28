"""Cross-asset correlation and regime intelligence."""

from lib.cross_asset.correlation_matrix import (
    BreakdownEvent,
    CorrelationCell,
    CorrelationMatrix,
    MethodMatrix,
    build_correlation_matrix,
    kendall,
    pearson,
    spearman,
)
from lib.cross_asset.lead_lag import LeadLagResult, analyze_lead_lag, lead_lag_for_pair
from lib.cross_asset.regime_detector import REGIME_LABELS, RegimeLabel, detect_regime
from lib.cross_asset.sources import (
    DEFAULT_ASSET_MAP,
    OHLCVPoint,
    build_default_adapters,
    fetch_universe,
    to_close_series,
)

__all__ = [
    "BreakdownEvent",
    "CorrelationCell",
    "CorrelationMatrix",
    "DEFAULT_ASSET_MAP",
    "LeadLagResult",
    "MethodMatrix",
    "OHLCVPoint",
    "REGIME_LABELS",
    "RegimeLabel",
    "build_correlation_matrix",
    "build_default_adapters",
    "detect_regime",
    "fetch_universe",
    "analyze_lead_lag",
    "kendall",
    "lead_lag_for_pair",
    "pearson",
    "spearman",
    "to_close_series",
]
