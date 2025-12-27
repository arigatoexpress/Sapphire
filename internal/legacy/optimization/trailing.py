"""Optuna helper for tuning trailing stop parameters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class TrailingConfig:
    stop_buffer: float
    trail_step: float


def optimise_trailing_stop(
    evaluate: Callable[[TrailingConfig], float],
    *,
    n_trials: int = 30,
    seed: int = 42,
) -> TrailingConfig:
    try:
        import optuna
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Install optuna to run the trailing stop tuner") from exc

    def objective(trial: "optuna.trial.Trial") -> float:
        cfg = TrailingConfig(
            stop_buffer=trial.suggest_float("stop_buffer", 0.002, 0.03),
            trail_step=trial.suggest_float("trail_step", 0.0005, 0.01),
        )
        return evaluate(cfg)

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.QMCSampler(seed=seed),
    )
    study.optimize(objective, n_trials=n_trials)
    best = study.best_params
    return TrailingConfig(stop_buffer=best["stop_buffer"], trail_step=best["trail_step"])


__all__ = ["optimise_trailing_stop", "TrailingConfig"]
