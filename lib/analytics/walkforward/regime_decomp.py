"""Regime decomposition of walk-forward returns.

Given a ``WalkforwardResult`` (or any equivalent (returns, timestamps) sequence)
plus a set of regime labels keyed by date, this module:

1. Joins per-bar test returns to a regime label using a forward-fill semantics
   on the ISO date string (the regime feed is sparse — typically one row per
   day from ``data/cross_asset/<date>/regimes.jsonl``).
2. Groups returns into per-regime buckets and computes per-regime metrics:
   total / mean return, volatility, downside deviation, win rate, max drawdown,
   Sharpe, Sortino, n_observations.
3. Reports the empirical regime distribution and the relative concentration of
   PnL by regime.

The module is pure and consumes only on-disk JSONL artifacts plus the in-memory
``WalkforwardResult`` (or a synthetic ``(returns, timestamps)`` pair). It never
recomputes regimes itself — that is ``lib.cross_asset.regime_detector``'s job.

Default regime feed path: ``data/cross_asset/<YYYY-MM-DD>/regimes.jsonl``. The
loader walks ``data/cross_asset`` from newest to oldest until it finds a
``regimes.jsonl`` and ingests every line. Each line is expected to carry at
least a ``timestamp`` (or ``date``) field and a ``label`` field.
"""

from __future__ import annotations

import json
import logging
import math
import statistics
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGIME_DIR = ROOT / "data" / "cross_asset"


__all__ = [
    "RegimeDecompResult",
    "RegimeReturnsBucket",
    "attach_regime_labels",
    "decompose_by_regime",
    "load_regime_labels",
]


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass
class RegimeReturnsBucket:
    """All test returns observed under a single regime label."""

    label: str
    n_observations: int
    total_return: float
    mean_return: float
    median_return: float
    volatility: float  # population stdev (we treat the bucket as the population)
    downside_volatility: float
    win_rate: float
    max_drawdown: float  # equity-curve max DD computed from the in-bucket equity chain
    sharpe: float
    sortino: float
    pnl_share: float  # share of total absolute PnL across all buckets

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RegimeDecompResult:
    """Full decomposition of a walk-forward returns stream by regime label."""

    strategy_cls: str
    symbol: str
    n_observations: int
    n_labelled: int
    n_unlabelled: int
    join_semantics: str  # "forward_fill" | "exact_match" | "nearest_prior"
    label_source: str
    buckets: list[RegimeReturnsBucket] = field(default_factory=list)
    distribution: dict[str, float] = field(default_factory=dict)  # label → fraction
    overall_mean_return: float = 0.0
    overall_volatility: float = 0.0
    dominant_regime: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_cls": self.strategy_cls,
            "symbol": self.symbol,
            "n_observations": self.n_observations,
            "n_labelled": self.n_labelled,
            "n_unlabelled": self.n_unlabelled,
            "join_semantics": self.join_semantics,
            "label_source": self.label_source,
            "buckets": [b.to_dict() for b in self.buckets],
            "distribution": dict(self.distribution),
            "overall_mean_return": self.overall_mean_return,
            "overall_volatility": self.overall_volatility,
            "dominant_regime": self.dominant_regime,
        }


# ---------------------------------------------------------------------------
# Regime label loader
# ---------------------------------------------------------------------------


def _normalise_date(raw: str) -> str:
    """Return ISO date string (YYYY-MM-DD) from any common timestamp shape."""
    if not raw:
        return ""
    raw = str(raw)
    # Strip trailing tz / time portion. Accept: '2026-04-29', '2026-04-29T...',
    # '2026-04-29 12:00:00+00:00', etc.
    # We always take the first 10 chars after stripping leading whitespace.
    raw = raw.strip()
    if len(raw) >= 10:
        candidate = raw[:10]
        try:
            datetime.strptime(candidate, "%Y-%m-%d")
            return candidate
        except ValueError:
            pass
    # Fallback: try fromisoformat for any prefix
    try:
        return datetime.fromisoformat(raw.split("Z")[0].replace(" ", "T")).date().isoformat()
    except (ValueError, TypeError):
        return ""


def load_regime_labels(
    source: Path | str | None = None,
    *,
    regime_dir: Path = DEFAULT_REGIME_DIR,
) -> dict[str, str]:
    """Load regime labels keyed by ISO date.

    If ``source`` is a file path, ingest that file directly. If it is a
    directory, glob ``*/regimes.jsonl`` underneath. If it is None, walk
    ``regime_dir`` from newest YYYY-MM-DD subdirectory backwards and stop at
    the first one carrying a ``regimes.jsonl``.

    Each JSONL line is expected to carry ``timestamp`` (or ``date``) + ``label``.
    Lines with missing fields are skipped silently. Latest label wins on
    duplicate dates (reflecting real cross-asset/run.py append semantics).
    """
    paths: list[Path] = []
    if source is not None:
        p = Path(source)
        if p.is_file():
            paths = [p]
        elif p.is_dir():
            paths = sorted(p.glob("*/regimes.jsonl"))
    else:
        if regime_dir.is_dir():
            for child in sorted(regime_dir.iterdir(), reverse=True):
                if child.is_dir() and (child / "regimes.jsonl").is_file():
                    paths = [child / "regimes.jsonl"]
                    break

    out: dict[str, str] = {}
    for path in paths:
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = obj.get("timestamp") or obj.get("date") or obj.get("ts")
                label = obj.get("label") or obj.get("regime") or obj.get("name")
                if not ts or not label:
                    continue
                key = _normalise_date(str(ts))
                if not key:
                    continue
                out[key] = str(label)
        except OSError as exc:  # pragma: no cover — defensive only
            log.warning("regime feed unreadable at %s: %s", path, exc)

    return out


# ---------------------------------------------------------------------------
# Join semantics
# ---------------------------------------------------------------------------


def attach_regime_labels(
    timestamps: list[str],
    labels: Mapping[str, str],
    *,
    semantics: str = "forward_fill",
    default_label: str = "regime_uncertain",
) -> list[str]:
    """Attach a regime label to each timestamp.

    Args:
        timestamps:    Per-observation ISO date strings (may have duplicates,
                       may be unsorted).
        labels:        Mapping of ISO date → regime label.
        semantics:     ``forward_fill`` (default) — for any date not present,
                       inherit the most recent prior labelled date. Equivalent
                       to "the regime classification active when the bar
                       closed". Other modes:
                          ``exact_match`` — only use a label when the exact
                          date is present in ``labels``; otherwise return
                          ``default_label``.
                          ``nearest_prior`` — alias for ``forward_fill`` but
                          still falls back to the next future label if no
                          prior label exists. Useful for sparse early data.
        default_label: Fallback when no label can be resolved.

    Returns:
        A list of regime labels aligned 1:1 with ``timestamps``.
    """
    if semantics not in {"forward_fill", "exact_match", "nearest_prior"}:
        raise ValueError(
            f"semantics must be forward_fill | exact_match | nearest_prior (got {semantics!r})"
        )

    if not labels:
        return [default_label] * len(timestamps)

    sorted_label_dates = sorted(labels.keys())

    out: list[str] = []
    for ts in timestamps:
        date = _normalise_date(ts)
        if not date:
            out.append(default_label)
            continue

        if semantics == "exact_match":
            out.append(labels.get(date, default_label))
            continue

        # forward_fill / nearest_prior
        # Find the latest label_date <= date; if absent, optionally fall through
        # to the earliest future date for nearest_prior.
        candidate: str | None = None
        for ld in reversed(sorted_label_dates):
            if ld <= date:
                candidate = labels[ld]
                break
        if candidate is None and semantics == "nearest_prior":
            for ld in sorted_label_dates:
                if ld >= date:
                    candidate = labels[ld]
                    break
        out.append(candidate or default_label)

    return out


# ---------------------------------------------------------------------------
# Decomposition
# ---------------------------------------------------------------------------


def _bucket_metrics(label: str, returns: list[float]) -> RegimeReturnsBucket:
    """Compute per-regime metrics from a list of bar returns."""
    n = len(returns)
    if n == 0:
        return RegimeReturnsBucket(
            label=label,
            n_observations=0,
            total_return=0.0,
            mean_return=0.0,
            median_return=0.0,
            volatility=0.0,
            downside_volatility=0.0,
            win_rate=0.0,
            max_drawdown=0.0,
            sharpe=0.0,
            sortino=0.0,
            pnl_share=0.0,
        )

    total = sum(returns)
    mean = statistics.fmean(returns)
    median = statistics.median(returns)
    vol = statistics.pstdev(returns) if n > 1 else 0.0
    downside = [r for r in returns if r < 0]
    if downside:
        dd_vol = math.sqrt(sum(r * r for r in downside) / n)
    else:
        dd_vol = 0.0
    wins = [r for r in returns if r > 0]
    wr = (len(wins) / n) if n else 0.0

    # Equity curve walk for max DD
    eq = [1.0]
    for r in returns:
        eq.append(eq[-1] * (1.0 + r))
    peak = eq[0]
    max_dd = 0.0
    for v in eq:
        peak = max(peak, v)
        if peak > 0:
            max_dd = max(max_dd, (peak - v) / peak)

    sharpe = (mean / vol) * math.sqrt(252) if vol > 0 else 0.0
    sortino = (mean / dd_vol) * math.sqrt(252) if dd_vol > 0 else 0.0

    return RegimeReturnsBucket(
        label=label,
        n_observations=n,
        total_return=round(total, 6),
        mean_return=round(mean, 6),
        median_return=round(median, 6),
        volatility=round(vol, 6),
        downside_volatility=round(dd_vol, 6),
        win_rate=round(wr, 4),
        max_drawdown=round(max_dd, 6),
        sharpe=round(sharpe, 4),
        sortino=round(sortino, 4),
        pnl_share=0.0,  # filled in after bucket totals are known
    )


def decompose_by_regime(
    returns: list[float] | Iterable[float],
    timestamps: list[str] | Iterable[str],
    labels: Mapping[str, str] | None = None,
    *,
    strategy_cls: str = "Strategy",
    symbol: str = "?",
    semantics: str = "forward_fill",
    default_label: str = "regime_uncertain",
    label_source: str = "data/cross_asset/<latest>/regimes.jsonl",
) -> RegimeDecompResult:
    """Group returns by regime label and compute per-regime metrics.

    Both ``returns`` and ``timestamps`` are positional; they must be the same
    length. ``labels`` is a date→label mapping (typically from
    ``load_regime_labels``). Pass ``labels=None`` to load the default feed.
    """
    rets = list(returns)
    tss = list(timestamps)
    if len(rets) != len(tss):
        raise ValueError(
            f"returns and timestamps must be the same length ({len(rets)} vs {len(tss)})"
        )

    if labels is None:
        labels = load_regime_labels()

    aligned_labels = attach_regime_labels(
        tss,
        labels,
        semantics=semantics,
        default_label=default_label,
    )

    buckets: dict[str, list[float]] = {}
    for r, lab in zip(rets, aligned_labels, strict=True):
        buckets.setdefault(lab, []).append(r)

    # Build metrics
    bucket_results = [_bucket_metrics(lab, vals) for lab, vals in sorted(buckets.items())]
    total_abs_pnl = sum(abs(b.total_return) for b in bucket_results) or 1.0
    for b in bucket_results:
        b.pnl_share = round(abs(b.total_return) / total_abs_pnl, 4)

    n = len(rets)
    distribution = {b.label: round(b.n_observations / n, 4) if n else 0.0 for b in bucket_results}
    dominant = max(bucket_results, key=lambda b: b.n_observations).label if bucket_results else ""
    overall_mean = round(statistics.fmean(rets), 6) if rets else 0.0
    overall_vol = round(statistics.pstdev(rets), 6) if len(rets) > 1 else 0.0

    n_labelled = sum(1 for lab in aligned_labels if lab != default_label)
    n_unlabelled = len(aligned_labels) - n_labelled

    return RegimeDecompResult(
        strategy_cls=strategy_cls,
        symbol=symbol,
        n_observations=n,
        n_labelled=n_labelled,
        n_unlabelled=n_unlabelled,
        join_semantics=semantics,
        label_source=label_source,
        buckets=bucket_results,
        distribution=distribution,
        overall_mean_return=overall_mean,
        overall_volatility=overall_vol,
        dominant_regime=dominant,
    )


# ---------------------------------------------------------------------------
# Convenience: decompose a WalkforwardResult directly
# ---------------------------------------------------------------------------


def decompose_walkforward_result(
    wf_result: Any,
    labels: Mapping[str, str] | None = None,
    *,
    semantics: str = "forward_fill",
    default_label: str = "regime_uncertain",
    label_source: str = "data/cross_asset/<latest>/regimes.jsonl",
) -> RegimeDecompResult:
    """Apply ``decompose_by_regime`` to a ``WalkforwardResult`` instance."""
    return decompose_by_regime(
        list(getattr(wf_result, "concatenated_test_returns", []) or []),
        list(getattr(wf_result, "concatenated_test_timestamps", []) or []),
        labels=labels,
        strategy_cls=str(getattr(wf_result, "strategy_cls", "Strategy")),
        symbol=str(getattr(wf_result, "symbol", "?")),
        semantics=semantics,
        default_label=default_label,
        label_source=label_source,
    )


__all__.append("decompose_walkforward_result")
