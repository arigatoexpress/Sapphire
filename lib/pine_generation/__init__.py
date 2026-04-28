"""Sapphire Pine v5 strategy generation pipeline.

This package translates the 7 Python strategies in :mod:`lib.analytics.strategies`
into deployable Pine Script v5 source for TradingView.

Public surface:
    - :class:`PineSpec` — input bundle: strategy class name + parameters + symbol.
    - :func:`generate_pine` — pure (PineSpec) -> str translator.
    - :func:`validate_pine` — pure (str) -> PineValidationResult lint.
    - :data:`SUPPORTED_STRATEGIES` — list of strategy class names this lane supports.

The package never executes Pine, never pushes to TradingView, and never imports
from `lib/portfolio/`, `lib/trading/`, or any live-capital module. The plugin
tool wraps an env-gated push step (`SAPPHIRE_PINE_TV_PUSH_LIVE=1`).
"""

from __future__ import annotations

from .translator import (
    SUPPORTED_STRATEGIES,
    PineParams,
    PineSpec,
    available_strategies,
    generate_pine,
    spec_from_backtest_row,
)
from .validator import (
    PineValidationResult,
    validate_pine,
)

__all__ = [
    "SUPPORTED_STRATEGIES",
    "PineParams",
    "PineSpec",
    "PineValidationResult",
    "available_strategies",
    "generate_pine",
    "spec_from_backtest_row",
    "validate_pine",
]

__version__ = "0.1.0"
