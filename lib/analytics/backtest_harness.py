"""CPCV-grounded backtest harness for the bearish-asymmetry Section 4.5 gate.

The bearish-direction asymmetry design doc (``docs/research/bearish-direction-asymmetry-2026-04-26.md``)
gates Layers A and B (chain factors in ``predict.py``, real ``short`` emission across
strategies) behind a CPCV-validated backtest with a deflated-Sharpe floor and a max-drawdown
ceiling. This module is that gate.

It is deliberately small. It composes existing primitives:

- ``lib.analytics.cpcv.cpcv_splits`` — purged + embargoed combinatorial splits.
- ``lib.analytics.strategies.BacktestEngine`` — drives ``Strategy`` instances through
  ``run_backtest`` and projects metrics onto a dashboard-shaped ``SimpleNamespace``.
- ``lib.analytics.deflated_sharpe.deflated_sharpe_ratio`` — Bailey & López de Prado 2014
  multiple-testing deflation.
- ``lib.analytics.backtest_engine.Bar`` — the OHLCV row dataclass shared across the stack.

What it does not do:

- It does not fetch live OHLCV from yfinance. The bearish-asymmetry doc requires the
  exact 2025-04-01 → 2026-04-25 window, which is not deterministic against ``yfinance``
  in a CI sandbox. Instead, it reads CSV under
  ``data/backtests/<symbol>/<timeframe>/*.csv`` if present, otherwise it returns a
  ``HarnessResult`` with ``acceptance.passes_section_4_5 == False`` and
  ``reasons=["no historical data: <symbol>"]``. The data gap is documented in §4.5.
- It does not modify the trading critical path (``strategies.py``, ``risk_engine.py``,
  ``run_strategies.py``, ``backtest_engine.py``). Layers A and B remain deferred until
  this harness can be fed real OHLCV.

CSV format (one file per symbol/timeframe, header-required):

    ts,open,high,low,close,volume
    2025-04-01T00:00:00+00:00,82500.1,84001.4,82200.0,83710.5,12345.6
    ...

ts must be ISO-8601 (timezone-aware preferred); the harness coerces to UTC.

CLI contract (matches ``scripts/ops/compare_*_artifacts.py``):

    python3 -m lib.analytics.backtest_harness \
        --strategy lib.analytics.strategies:RegimeAwareRSI \
        --start 2025-04-01 --end 2026-04-25 \
        --symbols BTC-USD,ETH-USD,SOL-USD

Exit codes: 0 = PASS, 10 = WARN (data gap or insufficient evidence), 20 = FAIL
(acceptance gate failed with adequate data).
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import logging
import math
import statistics
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lib.analytics.strategies import Strategy

log = logging.getLogger(__name__)

# Allow ``python3 -m lib.analytics.backtest_harness`` from the repo root without
# editable install. Mirrors the trick used by run_strategies.py.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Re-import after sys.path fix so the public exports point at the canonical paths.
from lib.analytics.backtest_engine import Bar  # noqa: E402
from lib.analytics.cpcv import cpcv_splits  # noqa: E402
from lib.analytics.deflated_sharpe import deflated_sharpe_ratio  # noqa: E402

# ── Exit codes (mirror compare_backtest_artifacts.py) ────────────────────────
EXIT_PASS = 0
EXIT_WARN = 10
EXIT_FAIL = 20

# ── Acceptance gates (Section 4.5 — conservative defaults) ───────────────────
MIN_TRADES = 30
MIN_SORTINO = 0.5
MIN_DSR = 0.0
MAX_DRAWDOWN_PCT = 35.0


# ── Public dataclasses ───────────────────────────────────────────────────────


@dataclass
class HarnessConfig:
    """Configuration for ``run_harness``.

    Defaults mirror the §4.5 reference window. ``cpcv_n_groups``/``cpcv_test_size``
    feed straight through to ``lib.analytics.cpcv.cpcv_splits``. ``cpcv_embargo`` is
    expressed as a fraction of total bars (matches ``embargo_pct`` in cpcv.py).
    """

    start_date: str = "2025-04-01"
    end_date: str = "2026-04-25"
    symbols: tuple[str, ...] = ("BTC-USD", "ETH-USD", "SOL-USD")
    cpcv_n_groups: int = 6
    cpcv_test_size: int = 2
    cpcv_embargo: float = 0.02
    bankroll: float = 10_000.0
    fee_bps: float = 5.0


@dataclass
class HarnessResult:
    """Aggregated CPCV outcome with explicit acceptance trace.

    All numeric fields are summary statistics across all (symbol × CPCV-fold) cells,
    not per-symbol. Per-fold detail is kept lightweight to keep this dataclass
    serializable and reviewable in a CI log.
    """

    cpcv_folds: int = 0
    total_trades: int = 0
    mean_pnl_pct: float = 0.0
    mean_sortino: float = 0.0
    deflated_sharpe: float = 0.0
    max_drawdown_pct: float = 0.0
    acceptance: dict[str, Any] = field(
        default_factory=lambda: {
            "passes_section_4_5": False,
            "reasons": [],
        }
    )


# ── Data loading ─────────────────────────────────────────────────────────────


def _data_root() -> Path:
    """Where ``data/backtests/<symbol>/<timeframe>/*.csv`` lives. Override in tests
    via the ``SAPPHIRE_BACKTEST_DATA_ROOT`` env var."""
    import os

    override = os.environ.get("SAPPHIRE_BACKTEST_DATA_ROOT")
    if override:
        return Path(override)
    return _ROOT / "data" / "backtests"


def _load_symbol_bars(
    symbol: str,
    start_date: str,
    end_date: str,
    timeframe: str = "1d",
    data_root: Path | None = None,
) -> list[Bar]:
    """Load OHLCV bars for ``symbol`` from the on-disk CSV cache.

    Returns ``[]`` if the directory or file is missing, or if no rows fall inside
    [start_date, end_date]. The harness treats an empty list as a data gap and
    fails-warn.
    """
    root = data_root or _data_root()
    sym_dir = root / symbol / timeframe
    if not sym_dir.exists():
        return []

    csvs = sorted(sym_dir.glob("*.csv"))
    if not csvs:
        return []

    start = _parse_iso(start_date)
    end = _parse_iso(end_date)
    bars: list[Bar] = []

    for path in csvs:
        try:
            with path.open(newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    ts = _parse_iso(row.get("ts") or row.get("date") or "")
                    if ts is None or start is None or end is None:
                        continue
                    if ts < start or ts > end:
                        continue
                    try:
                        bars.append(
                            Bar(
                                ts=ts,
                                open=float(row["open"]),
                                high=float(row["high"]),
                                low=float(row["low"]),
                                close=float(row["close"]),
                                volume=float(row.get("volume", 0.0) or 0.0),
                            )
                        )
                    except (KeyError, ValueError) as e:
                        log.debug("skipping malformed row in %s: %s", path, e)
                        continue
        except OSError as e:
            log.warning("failed to read %s: %s", path, e)
            continue

    bars.sort(key=lambda b: b.ts)
    return bars


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        # Bare YYYY-MM-DD or full ISO-8601
        if len(value) == 10:
            dt = datetime.fromisoformat(value).replace(tzinfo=UTC)
        else:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return None


# ── Per-fold metric helpers ──────────────────────────────────────────────────


def _fold_metrics(
    bars_subset: list[Bar], strategy: Strategy, symbol: str, bankroll: float, fee_bps: float
) -> dict[str, float]:
    """Run one strategy instance on one fold's bars via ``BacktestEngine``.

    Returns a flat dict with the four numbers we aggregate: sortino, total_pnl_pct,
    max_drawdown_pct, and the trade count. The engine itself is unmodified — we
    just feed it a subset of bars, which is exactly what the old CPCV path did.
    """
    from lib.analytics.strategies import BacktestEngine

    if len(bars_subset) < 20:
        return {
            "sortino": 0.0,
            "pnl_pct": 0.0,
            "max_dd_pct": 0.0,
            "trades": 0.0,
            "sharpe": 0.0,
        }

    engine = BacktestEngine(bankroll=bankroll, fee_bps=fee_bps)
    report = engine.run(bars_subset, strategy, symbol, aux_data={})
    # report is a SimpleNamespace from BacktestEngine — fractions for win_rate/return/dd.
    return {
        "sortino": float(getattr(report, "sortino", 0.0) or 0.0),
        "pnl_pct": float(getattr(report, "total_return_pct", 0.0) or 0.0) * 100.0,
        "max_dd_pct": float(getattr(report, "max_drawdown_pct", 0.0) or 0.0) * 100.0,
        "trades": float(getattr(report, "total_trades", 0) or 0),
        "sharpe": float(getattr(report, "sharpe", 0.0) or 0.0),
    }


# ── Public API ───────────────────────────────────────────────────────────────


def run_harness(
    strategy_factory: Callable[[], Strategy],
    config: HarnessConfig,
    *,
    data_root: Path | None = None,
) -> HarnessResult:
    """Run a CPCV backtest harness for one strategy across ``config.symbols``.

    The factory is called once per (symbol × CPCV split). This guarantees the
    strategy gets a fresh, side-effect-free instance per fold — required for any
    strategy that holds state (rolling buffers, regime caches) between bars.

    Args:
        strategy_factory: Zero-arg callable returning a fresh ``Strategy`` each call.
        config: ``HarnessConfig`` with date window, CPCV params, bankroll, fees.
        data_root: Override ``data/backtests/`` for testing.

    Returns:
        ``HarnessResult`` with aggregate metrics and the §4.5 acceptance trace.
    """
    bars_by_symbol: dict[str, list[Bar]] = {}
    for sym in config.symbols:
        bars = _load_symbol_bars(
            sym,
            config.start_date,
            config.end_date,
            data_root=data_root,
        )
        if bars:
            bars_by_symbol[sym] = bars

    if not bars_by_symbol:
        return HarnessResult(
            acceptance={
                "passes_section_4_5": False,
                "reasons": ["no historical data"],
            },
        )

    # Per-fold accumulators — every (symbol × split) cell contributes one row.
    sortinos: list[float] = []
    pnls_pct: list[float] = []
    max_dds: list[float] = []
    sharpes: list[float] = []
    total_trades = 0
    total_folds = 0
    fold_count_per_symbol: dict[str, int] = {}

    for sym, bars in bars_by_symbol.items():
        n_bars = len(bars)
        # cpcv_splits raises if n_samples < n_groups — gracefully skip thin symbols.
        if n_bars < config.cpcv_n_groups:
            log.warning("symbol %s has only %d bars, skipping CPCV", sym, n_bars)
            continue

        try:
            splits = list(
                cpcv_splits(
                    n_samples=n_bars,
                    n_groups=config.cpcv_n_groups,
                    n_test_groups=config.cpcv_test_size,
                    # purge_pct kept conservative; only embargo is configurable here.
                    purge_pct=0.01,
                    embargo_pct=config.cpcv_embargo,
                )
            )
        except ValueError as e:
            log.warning("cpcv_splits rejected %s: %s", sym, e)
            continue

        for _train_idx, test_idx in splits:
            if not test_idx:
                continue
            test_bars = [bars[i] for i in test_idx]
            strat = strategy_factory()  # fresh instance per fold
            m = _fold_metrics(
                test_bars,
                strat,
                sym,
                config.bankroll,
                config.fee_bps,
            )
            sortinos.append(m["sortino"])
            pnls_pct.append(m["pnl_pct"])
            max_dds.append(m["max_dd_pct"])
            sharpes.append(m["sharpe"])
            total_trades += int(m["trades"])
            total_folds += 1
            fold_count_per_symbol[sym] = fold_count_per_symbol.get(sym, 0) + 1

    if total_folds == 0:
        return HarnessResult(
            acceptance={
                "passes_section_4_5": False,
                "reasons": ["no folds produced — symbols too short for CPCV grouping"],
            },
        )

    mean_sortino = statistics.fmean(sortinos) if sortinos else 0.0
    mean_pnl_pct = statistics.fmean(pnls_pct) if pnls_pct else 0.0
    # Worst-case drawdown across all folds — the §4.5 ceiling is on the worst, not the mean.
    worst_dd = max(max_dds) if max_dds else 0.0

    # DSR consumes the per-fold Sharpe distribution as the trial set, with the
    # selected Sharpe = mean(folds). This matches Bailey & López de Prado's
    # framing of "we picked a strategy across many trials". Reuses the existing
    # implementation rather than reinventing.
    if sharpes:
        try:
            dsr_input = [s for s in sharpes if math.isfinite(s)]
            if not dsr_input:
                dsr_input = [0.0]
            dsr_result = deflated_sharpe_ratio(
                sharpe_list=dsr_input,
                selected_sharpe=statistics.fmean(dsr_input),
                n_obs=max(1, total_folds),
            )
            dsr_value = float(dsr_result.deflated_sharpe)
            if not math.isfinite(dsr_value):
                dsr_value = 0.0
        except (ValueError, ZeroDivisionError) as e:
            log.warning("DSR computation failed: %s", e)
            dsr_value = 0.0
    else:
        dsr_value = 0.0

    acceptance = _evaluate_acceptance(
        total_trades=total_trades,
        mean_sortino=mean_sortino,
        deflated_sharpe=dsr_value,
        max_drawdown_pct=worst_dd,
    )

    return HarnessResult(
        cpcv_folds=total_folds,
        total_trades=total_trades,
        mean_pnl_pct=round(mean_pnl_pct, 4),
        mean_sortino=round(mean_sortino, 4),
        deflated_sharpe=round(dsr_value, 4),
        max_drawdown_pct=round(worst_dd, 4),
        acceptance=acceptance,
    )


def _evaluate_acceptance(
    *,
    total_trades: int,
    mean_sortino: float,
    deflated_sharpe: float,
    max_drawdown_pct: float,
) -> dict[str, Any]:
    """Apply the §4.5 conservative acceptance gates, recording every failure."""
    reasons: list[str] = []

    if total_trades < MIN_TRADES:
        reasons.append(f"total_trades={total_trades} < {MIN_TRADES} (insufficient evidence)")
    if mean_sortino < MIN_SORTINO:
        reasons.append(f"mean_sortino={mean_sortino:.3f} < {MIN_SORTINO}")
    if deflated_sharpe < MIN_DSR:
        reasons.append(
            f"deflated_sharpe={deflated_sharpe:.3f} < {MIN_DSR} "
            f"(strategy likely overfit relative to selection bias)"
        )
    if max_drawdown_pct > MAX_DRAWDOWN_PCT:
        reasons.append(
            f"max_drawdown_pct={max_drawdown_pct:.2f} > {MAX_DRAWDOWN_PCT} (catastrophic drawdown)"
        )

    return {"passes_section_4_5": not reasons, "reasons": reasons}


# ── Strategy factory resolution (CLI helper) ─────────────────────────────────


def _resolve_strategy_factory(spec: str) -> Callable[[], Strategy]:
    """Parse ``module:class`` and return a zero-arg factory.

    Example: ``lib.analytics.strategies:RegimeAwareRSI`` → ``lambda: RegimeAwareRSI()``.
    """
    if ":" not in spec:
        raise ValueError(f"--strategy must be 'module:class', got {spec!r}")
    module_path, cls_name = spec.split(":", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, cls_name, None)
    if cls is None:
        raise ValueError(f"class {cls_name!r} not found in {module_path!r}")

    def _factory() -> Strategy:
        return cls()  # type: ignore[no-any-return]

    return _factory


# ── CLI ──────────────────────────────────────────────────────────────────────


def cli(argv: list[str] | None = None) -> int:
    """Argparse front-end. Prints JSON to stdout. Returns exit code 0/10/20."""
    parser = argparse.ArgumentParser(
        prog="lib.analytics.backtest_harness",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--strategy",
        required=True,
        help="module:class spec, e.g. lib.analytics.strategies:RegimeAwareRSI",
    )
    parser.add_argument("--start", default="2025-04-01")
    parser.add_argument("--end", default="2026-04-25")
    parser.add_argument(
        "--symbols",
        default="BTC-USD,ETH-USD,SOL-USD",
        help="Comma-separated tickers (default: BTC,ETH,SOL — matches §4.5 universe)",
    )
    parser.add_argument(
        "--config-json",
        type=Path,
        default=None,
        help="Optional JSON file overriding any HarnessConfig field",
    )
    args = parser.parse_args(argv)

    # Build base config from args, then apply optional JSON override.
    symbols = tuple(s.strip() for s in args.symbols.split(",") if s.strip())
    cfg_kwargs: dict[str, Any] = {
        "start_date": args.start,
        "end_date": args.end,
        "symbols": symbols,
    }
    if args.config_json is not None:
        try:
            override = json.loads(args.config_json.read_text(encoding="utf-8"))
            if not isinstance(override, dict):
                raise ValueError("--config-json must be a JSON object")
            for key, value in override.items():
                if key == "symbols" and isinstance(value, list):
                    value = tuple(value)
                cfg_kwargs[key] = value
        except (OSError, ValueError) as e:
            print(f"config-json error: {e}", file=sys.stderr)
            return EXIT_WARN

    try:
        config = HarnessConfig(**cfg_kwargs)
    except TypeError as e:
        print(f"invalid config: {e}", file=sys.stderr)
        return EXIT_WARN

    try:
        factory = _resolve_strategy_factory(args.strategy)
    except (ValueError, ImportError) as e:
        print(f"strategy resolution failed: {e}", file=sys.stderr)
        return EXIT_WARN

    result = run_harness(factory, config)

    # Emit JSON to stdout — caller consumes this exactly like the compare_*_artifacts scripts.
    print(json.dumps(asdict(result), indent=2, default=str))

    if result.acceptance.get("passes_section_4_5"):
        return EXIT_PASS

    reasons = result.acceptance.get("reasons", [])
    # Data-gap conditions are WARN, not FAIL — there's not enough info to judge.
    data_gap_markers = ("no historical data", "no folds produced")
    if any(marker in r for marker in data_gap_markers for r in reasons):
        return EXIT_WARN
    return EXIT_FAIL


__all__ = [
    "EXIT_FAIL",
    "EXIT_PASS",
    "EXIT_WARN",
    "HarnessConfig",
    "HarnessResult",
    "MAX_DRAWDOWN_PCT",
    "MIN_DSR",
    "MIN_SORTINO",
    "MIN_TRADES",
    "cli",
    "run_harness",
]


if __name__ == "__main__":
    sys.exit(cli())
