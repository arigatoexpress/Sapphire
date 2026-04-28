"""Sapphire Pine generation service.

Wraps :mod:`lib.pine_generation` with the disk-side concerns: pulling top-N
backtest configs from `data/backtests/strategies/best_per_symbol_*.json`,
generating Pine source, persisting under `pine/generated/<date>/`.
"""

from __future__ import annotations
