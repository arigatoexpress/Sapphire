"""Walk-forward backtest builder service.

Pure orchestration around lib.analytics.walkforward (no live data, no I/O
except writing JSON artifacts to data/backtests/walkforward/<date>/).
"""

VERSION = "0.1.0"
