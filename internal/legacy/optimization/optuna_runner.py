"""Utility for running Optuna-based trailing stop tuning on historical data."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .trailing import TrailingConfig, optimise_trailing_stop


def evaluate_from_csv(path: Path, config: TrailingConfig) -> float:
    df = pd.read_csv(path)
    pnl = 0.0
    for _, row in df.iterrows():
        reward = row.get("pnl", 0.0)
        pnl += reward - config.stop_buffer * abs(reward)
    return pnl


def main() -> None:
    parser = argparse.ArgumentParser(description="Tune trailing stop parameters via Optuna")
    parser.add_argument("--csv", type=Path, required=True, help="CSV with backtest PnL column")
    parser.add_argument("--trials", type=int, default=30)
    args = parser.parse_args()

    def evaluate(config: TrailingConfig) -> float:
        return evaluate_from_csv(args.csv, config)

    best = optimise_trailing_stop(evaluate, n_trials=args.trials)
    print(f"Best trailing config: stop_buffer={best.stop_buffer:.4f}, step={best.trail_step:.4f}")


if __name__ == "__main__":  # pragma: no cover - CLI helper
    main()
