"""Pure cross-asset rolling correlation primitives.

The module intentionally stays stdlib-only. Inputs are plain Python series
objects and outputs are dataclasses that can be serialized directly for the
dashboard, daemon, and plugin tool.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from itertools import combinations
from typing import Any

MAX_ASSETS_HARD = 24
MAX_WINDOW_DAYS = 365
MIN_OBSERVATIONS_PER_WINDOW = 30

DEFAULT_WINDOWS: dict[str, int] = {
    "24h": 24,
    "7d": 24 * 7,
    "30d": 24 * 30,
}
DEFAULT_METHODS: tuple[str, ...] = ("pearson", "spearman", "kendall")


@dataclass(frozen=True)
class CorrelationCell:
    """Correlation values for one pair in one rolling window."""

    pair: tuple[str, str]
    window: str
    sample_count: int
    pearson: float | None
    spearman: float | None
    kendall: float | None


@dataclass(frozen=True)
class MethodMatrix:
    """Square correlation matrix for a single method/window."""

    method: str
    window: str
    observations: int
    min_observations: int
    assets: list[str]
    matrix: list[list[float | None]]
    sample_counts: list[list[int]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BreakdownEvent:
    """A statistically unusual correlation move for an asset pair."""

    pair: tuple[str, str]
    timestamp: str
    method: str
    window: str
    current: float
    baseline_mean: float
    baseline_stdev: float
    z_score: float
    severity: str
    direction: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CorrelationMatrix:
    """Multi-window, multi-method correlation result."""

    generated_at: str
    assets: list[str]
    windows: dict[str, dict[str, MethodMatrix]]
    pair_cells: list[CorrelationCell]
    breakdown_events: list[BreakdownEvent]

    def matrix_for(self, *, window: str = "7d", method: str = "pearson") -> MethodMatrix:
        """Return a specific method/window matrix with a clear error on miss."""
        try:
            return self.windows[window][method]
        except KeyError as exc:
            raise KeyError(f"matrix not available for window={window!r} method={method!r}") from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "assets": list(self.assets),
            "windows": {
                window: {method: matrix.to_dict() for method, matrix in methods.items()}
                for window, methods in self.windows.items()
            },
            "pair_cells": [cell_to_dict(cell) for cell in self.pair_cells],
            "breakdown_events": [event.to_dict() for event in self.breakdown_events],
        }


def cell_to_dict(cell: CorrelationCell) -> dict[str, Any]:
    return asdict(cell)


def _now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).replace(microsecond=0).isoformat()


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    rounded = round(float(value), digits)
    return 0.0 if rounded == -0.0 else rounded


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _point_timestamp(point: Any, fallback_index: int) -> str:
    raw: Any = None
    if isinstance(point, Mapping):
        raw = (
            point.get("timestamp")
            or point.get("timestamp_iso")
            or point.get("date")
            or point.get("time")
            or point.get("t")
        )
    else:
        raw = getattr(point, "timestamp", None) or getattr(point, "timestamp_iso", None)
    if isinstance(raw, datetime):
        return raw.astimezone(UTC).replace(microsecond=0).isoformat()
    if raw is not None:
        return str(raw)
    return f"{fallback_index:012d}"


def _point_close(point: Any) -> float | None:
    if _is_number(point):
        return float(point)
    if isinstance(point, Mapping):
        for key in ("close", "c", "price", "value"):
            if key in point and _is_number(point[key]):
                return float(point[key])
        return None
    for attr in ("close", "price", "value"):
        value = getattr(point, attr, None)
        if _is_number(value):
            return float(value)
    return None


def coerce_close_series(raw: Any) -> dict[str, float]:
    """Normalize common OHLCV/close shapes into ``timestamp -> close``."""
    out: dict[str, float] = {}
    if raw is None:
        return out
    if isinstance(raw, Mapping):
        if "close" in raw and _point_close(raw) is not None:
            return {_point_timestamp(raw, 0): float(_point_close(raw) or 0.0)}
        for idx, (key, value) in enumerate(raw.items()):
            if _is_number(value):
                out[str(key)] = float(value)
            else:
                close = _point_close(value)
                if close is not None:
                    out[_point_timestamp(value, idx) if isinstance(value, Mapping) else str(key)] = close
        return dict(sorted(out.items()))
    if isinstance(raw, Iterable) and not isinstance(raw, str | bytes):
        for idx, point in enumerate(raw):
            close = _point_close(point)
            if close is not None:
                out[_point_timestamp(point, idx)] = close
    return dict(sorted(out.items()))


def align_pair(
    left: Mapping[str, float],
    right: Mapping[str, float],
) -> tuple[list[str], list[float], list[float]]:
    """Return shared timestamps and value vectors sorted by timestamp."""
    shared = sorted(set(left) & set(right))
    return shared, [left[t] for t in shared], [right[t] for t in shared]


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Compute Pearson correlation without numpy/pandas."""
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return max(-1.0, min(1.0, num / (den_x * den_y)))


def _ranks(values: Sequence[float]) -> list[float]:
    indexed = sorted((value, idx) for idx, value in enumerate(values))
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][0] == indexed[i][0]:
            j += 1
        avg_rank = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[indexed[k][1]] = avg_rank
        i = j + 1
    return ranks


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Compute Spearman rank correlation with average ranks for ties."""
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    return pearson(_ranks(xs), _ranks(ys))


def kendall(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Compute Kendall tau-b with tie handling."""
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    concordant = 0
    discordant = 0
    ties_x = 0
    ties_y = 0
    for i in range(len(xs) - 1):
        for j in range(i + 1, len(xs)):
            dx = _cmp(xs[i], xs[j])
            dy = _cmp(ys[i], ys[j])
            if dx == 0 and dy == 0:
                continue
            if dx == 0:
                ties_x += 1
            elif dy == 0:
                ties_y += 1
            elif dx == dy:
                concordant += 1
            else:
                discordant += 1
    denominator = math.sqrt((concordant + discordant + ties_x) * (concordant + discordant + ties_y))
    if denominator == 0:
        return None
    return max(-1.0, min(1.0, (concordant - discordant) / denominator))


def _cmp(left: float, right: float) -> int:
    if left < right:
        return -1
    if left > right:
        return 1
    return 0


def correlation_for_method(method: str, xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if method == "pearson":
        return pearson(xs, ys)
    if method == "spearman":
        return spearman(xs, ys)
    if method == "kendall":
        return kendall(xs, ys)
    raise ValueError(f"unsupported correlation method: {method}")


def normalize_windows(windows: Mapping[str, int] | Sequence[int] | None) -> dict[str, int]:
    if windows is None:
        return dict(DEFAULT_WINDOWS)
    if isinstance(windows, Mapping):
        out = {str(label): int(size) for label, size in windows.items()}
    else:
        out = {f"{int(size)}obs": int(size) for size in windows}
    for label, size in out.items():
        if size < 2:
            raise ValueError(f"window {label!r} must be at least 2 observations")
        max_observations = MAX_WINDOW_DAYS * 24
        if size > max_observations:
            raise ValueError(f"window {label!r} exceeds MAX_WINDOW_DAYS={MAX_WINDOW_DAYS}")
    return out


def build_correlation_matrix(
    series_by_asset: Mapping[str, Any],
    *,
    windows: Mapping[str, int] | Sequence[int] | None = None,
    methods: Sequence[str] = DEFAULT_METHODS,
    min_observations: int = MIN_OBSERVATIONS_PER_WINDOW,
    breakdown_window: int = 24 * 7,
    baseline_window: int = 24 * 90,
    breakdown_z_threshold: float = 2.0,
    now: datetime | None = None,
) -> CorrelationMatrix:
    """Compute rolling correlation matrices and breakdown events.

    ``windows`` are expressed as observations so the same logic works for
    hourly or daily fixtures. The default labels assume hourly bars.
    """
    assets = [asset.strip().upper() for asset in series_by_asset if str(asset).strip()]
    assets = sorted(dict.fromkeys(assets))
    if len(assets) > MAX_ASSETS_HARD:
        raise ValueError(f"asset count {len(assets)} exceeds MAX_ASSETS_HARD={MAX_ASSETS_HARD}")
    normalized = {asset: coerce_close_series(series_by_asset[asset]) for asset in assets}
    window_map = normalize_windows(windows)
    method_names = tuple(method.lower().strip() for method in methods)
    for method in method_names:
        correlation_for_method(method, [1.0, 2.0], [1.0, 2.0])

    matrices: dict[str, dict[str, MethodMatrix]] = {}
    cells: list[CorrelationCell] = []
    for label, size in window_map.items():
        min_required = max(2, min(int(min_observations), int(size)))
        method_values: dict[str, list[list[float | None]]] = {
            method: [[None for _ in assets] for _ in assets] for method in method_names
        }
        sample_counts = [[0 for _ in assets] for _ in assets]
        for i, asset in enumerate(assets):
            for method in method_names:
                method_values[method][i][i] = 1.0
            sample_counts[i][i] = len(normalized[asset])
        for i, j in combinations(range(len(assets)), 2):
            _, xs_all, ys_all = align_pair(normalized[assets[i]], normalized[assets[j]])
            xs = xs_all[-size:]
            ys = ys_all[-size:]
            sample_count = len(xs)
            sample_counts[i][j] = sample_counts[j][i] = sample_count
            values: dict[str, float | None] = {}
            if sample_count >= min_required:
                for method in method_names:
                    values[method] = _round(correlation_for_method(method, xs, ys))
                    method_values[method][i][j] = method_values[method][j][i] = values[method]
            else:
                for method in method_names:
                    values[method] = None
            cells.append(
                CorrelationCell(
                    pair=(assets[i], assets[j]),
                    window=label,
                    sample_count=sample_count,
                    pearson=values.get("pearson"),
                    spearman=values.get("spearman"),
                    kendall=values.get("kendall"),
                )
            )
        matrices[label] = {
            method: MethodMatrix(
                method=method,
                window=label,
                observations=size,
                min_observations=min_required,
                assets=list(assets),
                matrix=method_values[method],
                sample_counts=[list(row) for row in sample_counts],
            )
            for method in method_names
        }

    events = detect_breakdown_events(
        normalized,
        window=breakdown_window,
        baseline_window=baseline_window,
        z_threshold=breakdown_z_threshold,
        min_baseline_observations=max(3, min(20, baseline_window)),
    )
    return CorrelationMatrix(
        generated_at=_now_iso(now),
        assets=assets,
        windows=matrices,
        pair_cells=cells,
        breakdown_events=events,
    )


def detect_breakdown_events(
    series_by_asset: Mapping[str, Mapping[str, float]],
    *,
    window: int,
    baseline_window: int,
    z_threshold: float = 2.0,
    min_baseline_observations: int = 20,
) -> list[BreakdownEvent]:
    """Find pair correlations that have moved unusually versus baseline."""
    events: list[BreakdownEvent] = []
    assets = sorted(series_by_asset)
    for left, right in combinations(assets, 2):
        timestamps, xs, ys = align_pair(series_by_asset[left], series_by_asset[right])
        if len(xs) < window + min_baseline_observations:
            continue
        rolling: list[float] = []
        rolling_timestamps: list[str] = []
        for idx in range(window, len(xs) + 1):
            value = pearson(xs[idx - window : idx], ys[idx - window : idx])
            if value is not None:
                rolling.append(value)
                rolling_timestamps.append(timestamps[idx - 1])
        if len(rolling) < min_baseline_observations + 1:
            continue
        current = rolling[-1]
        baseline = rolling[max(0, len(rolling) - baseline_window - 1) : -1]
        if len(baseline) < min_baseline_observations:
            continue
        mean = sum(baseline) / len(baseline)
        stdev = math.sqrt(sum((value - mean) ** 2 for value in baseline) / len(baseline))
        if stdev == 0:
            continue
        z_score = (current - mean) / stdev
        if abs(z_score) <= z_threshold:
            continue
        direction = "correlation_spike" if z_score > 0 else "correlation_breakdown"
        severity = _severity(abs(z_score))
        events.append(
            BreakdownEvent(
                pair=(left, right),
                timestamp=rolling_timestamps[-1],
                method="pearson",
                window=f"{window}obs",
                current=_round(current) or 0.0,
                baseline_mean=_round(mean) or 0.0,
                baseline_stdev=_round(stdev) or 0.0,
                z_score=_round(z_score) or 0.0,
                severity=severity,
                direction=direction,
                note=(
                    f"{left}/{right} {direction.replace('_', ' ')}: "
                    f"{current:+.2f} vs {mean:+.2f} baseline ({z_score:+.1f} sigma)"
                ),
            )
        )
    return sorted(events, key=lambda event: abs(event.z_score), reverse=True)


def _severity(abs_z: float) -> str:
    if abs_z >= 4.0:
        return "severe"
    if abs_z >= 3.0:
        return "high"
    return "moderate"


__all__ = [
    "BreakdownEvent",
    "CorrelationCell",
    "CorrelationMatrix",
    "DEFAULT_METHODS",
    "DEFAULT_WINDOWS",
    "MAX_ASSETS_HARD",
    "MAX_WINDOW_DAYS",
    "MIN_OBSERVATIONS_PER_WINDOW",
    "MethodMatrix",
    "align_pair",
    "build_correlation_matrix",
    "coerce_close_series",
    "correlation_for_method",
    "detect_breakdown_events",
    "kendall",
    "normalize_windows",
    "pearson",
    "spearman",
]
