"""Rolling Sortino helpers for the live-capital ramp.

The functions here are pure. They accept return series from tests, paper
evidence, or operator-curated live ledgers and return explicit small-sample
reasons instead of quietly inventing a ratio.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class SortinoResult:
    """A paste-safe Sortino computation result."""

    value: float | None
    periods: int
    target_return: float = 0.0
    downside_deviation: float | None = None
    mean_return: float | None = None
    reason: str = "ok"
    skipped: int = 0

    @property
    def ok(self) -> bool:
        return self.value is not None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.value is not None and math.isinf(self.value):
            data["value"] = "inf"
        return data


def _clean_returns(returns: Iterable[float | int | str | None]) -> tuple[list[float], int]:
    clean: list[float] = []
    skipped = 0
    for raw in returns:
        try:
            value = float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            skipped += 1
            continue
        if math.isnan(value):
            skipped += 1
            continue
        clean.append(value)
    return clean, skipped


def sortino_ratio(
    returns: Iterable[float | int | str | None],
    *,
    target_return: float = 0.0,
    minimum_periods: int = 14,
    annualization_factor: float | None = None,
) -> SortinoResult:
    """Compute a Sortino ratio with explicit small-sample handling.

    Args:
        returns: Per-period returns as decimals, e.g. ``0.01`` for 1%.
        target_return: Minimum acceptable return per period.
        minimum_periods: Required clean observations. The ramp uses 14.
        annualization_factor: Optional multiplier applied as ``sqrt(factor)``.

    Returns:
        :class:`SortinoResult`. ``value`` is ``None`` when the input is not
        fit for a gate decision. All-positive returns yield ``inf`` when the
        mean return is above target because downside deviation is zero.
    """

    clean, skipped = _clean_returns(returns)
    n = len(clean)
    if n < minimum_periods:
        return SortinoResult(
            value=None,
            periods=n,
            target_return=target_return,
            reason=f"insufficient_periods:{n}/{minimum_periods}",
            skipped=skipped,
        )

    excess = [r - target_return for r in clean]
    mean_excess = sum(excess) / n
    downside_squares = [min(0.0, r - target_return) ** 2 for r in clean]
    downside_deviation = math.sqrt(sum(downside_squares) / n)
    mean_return = sum(clean) / n

    if downside_deviation == 0:
        if mean_excess > 0:
            return SortinoResult(
                value=math.inf,
                periods=n,
                target_return=target_return,
                downside_deviation=0.0,
                mean_return=mean_return,
                reason="no_downside_positive_mean",
                skipped=skipped,
            )
        return SortinoResult(
            value=None,
            periods=n,
            target_return=target_return,
            downside_deviation=0.0,
            mean_return=mean_return,
            reason="no_downside_no_positive_excess",
            skipped=skipped,
        )

    value = mean_excess / downside_deviation
    if annualization_factor is not None:
        value *= math.sqrt(float(annualization_factor))
    return SortinoResult(
        value=value,
        periods=n,
        target_return=target_return,
        downside_deviation=downside_deviation,
        mean_return=mean_return,
        reason="ok",
        skipped=skipped,
    )


def last_n_sortino(
    returns: Iterable[float | int | str | None],
    *,
    window: int = 14,
    target_return: float = 0.0,
) -> SortinoResult:
    """Compute Sortino over the last ``window`` clean returns."""

    clean, skipped = _clean_returns(returns)
    tail = clean[-window:]
    result = sortino_ratio(tail, target_return=target_return, minimum_periods=window)
    return SortinoResult(
        value=result.value,
        periods=result.periods,
        target_return=result.target_return,
        downside_deviation=result.downside_deviation,
        mean_return=result.mean_return,
        reason=result.reason,
        skipped=result.skipped + skipped,
    )
