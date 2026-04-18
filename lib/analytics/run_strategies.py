"""Multi-strategy sweep runner.

Fetches 90d daily OHLCV for BTC-USD, ETH-USD, SOL-USD, SPY; runs all 5
Sapphire strategies across a 3×3×3 parameter grid; saves results to
data/backtests/strategies/ and prints a ranked comparison table.

Usage:
    python -m lib.analytics.run_strategies
    python -m lib.analytics.run_strategies --days 90 --bankroll 10000

Invoked automatically every Saturday at 22:00 by:
    com.sapphire.backtest-weekly LaunchAgent
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# Allow running as `python lib/analytics/run_strategies.py` directly
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.analytics.backtest import load_yfinance_ohlcv
from lib.analytics.strategies import (
    ALL_STRATEGIES,
    COMPOSITE_THRESHOLDS,
    BacktestEngine,
    SapphireComposite,
    StrategyParams,
    SweepResult,
    best_per_symbol,
    compare,
    format_table,
    save_results,
    sweep_params,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("run_strategies")

SYMBOLS = ["BTC-USD", "ETH-USD", "SOL-USD", "SPY"]
AUX_SYMBOLS = ["BTC-USD", "SPY"]  # loaded once and shared as aux across all symbols


def _load_all_bars(symbols: list[str], days: int) -> dict:
    """Fetch OHLCV for every symbol. Returns {symbol: [Bar, ...]}."""
    bars_map: dict = {}
    for sym in symbols:
        log.info("  fetching %s (%dd)...", sym, days)
        bars = load_yfinance_ohlcv(sym, days=days)
        bars_map[sym] = bars
        log.info("    → %d bars", len(bars))
    return bars_map


def _build_aux_map(
    symbols: list[str],
    bars_map: dict,
) -> dict[str, dict]:
    """For each symbol, build aux = {btc: [...], spy: [...]}.

    BTC bars are used for regime detection in every strategy.
    SPY bars are used for correlation in CorrBreakout + SapphireComposite.
    """
    btc_bars = bars_map.get("BTC-USD", [])
    spy_bars = bars_map.get("SPY", [])
    aux_map: dict[str, dict] = {}

    for sym in symbols:
        aux: dict = {}
        # Regime: use BTC for non-BTC symbols; BTC uses its own bars (passed via window)
        if sym != "BTC-USD" and btc_bars:
            aux["btc"] = btc_bars
        # Correlation: SPY available for all symbols
        if sym != "SPY" and spy_bars:
            aux["spy"] = spy_bars
        aux_map[sym] = aux

    return aux_map


def _print_strategy_summary(all_best: list[SweepResult]) -> None:
    """Print per-strategy aggregate stats across all symbols."""
    from collections import defaultdict
    by_cls: dict[str, list[SweepResult]] = defaultdict(list)
    for r in all_best:
        by_cls[r.strategy_cls].append(r)

    print("\n── Strategy edge summary (avg Sortino across symbols) ──")
    rows = []
    for cls_name, results in by_cls.items():
        sortinos = [r.sortino for r in results if r.sortino is not None]
        avg_srt = sum(sortinos) / len(sortinos) if sortinos else 0.0
        profitable = sum(1 for r in results if r.total_return_pct > 0)
        rows.append((avg_srt, cls_name, len(results), profitable))

    for avg_srt, cls_name, n, profitable in sorted(rows, reverse=True):
        bar = "█" * max(0, int(avg_srt * 4))
        print(f"  {cls_name:<30} avg Sortino: {avg_srt:>6.2f}  {bar}  ({profitable}/{n} symbols profitable)")


def run(days: int = 90, bankroll: float = 10_000.0) -> list[SweepResult]:
    t0 = time.time()
    print(f"\n{'═'*70}")
    print(f"  Sapphire Strategy Sweep — {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Symbols: {SYMBOLS}   Days: {days}   Bankroll: ${bankroll:,.0f}")
    print(f"{'═'*70}\n")

    # ── 1. Fetch data ────────────────────────────────────────────────────────
    print("── Loading OHLCV ──")
    # We need all target symbols PLUS any aux symbols not already in SYMBOLS
    fetch_syms = list(dict.fromkeys(SYMBOLS + [s for s in AUX_SYMBOLS if s not in SYMBOLS]))
    bars_map = _load_all_bars(fetch_syms, days)

    # Filter to symbols that actually loaded
    active_symbols = [s for s in SYMBOLS if len(bars_map.get(s, [])) >= 25]
    if not active_symbols:
        log.error("No symbols loaded — check yfinance connectivity")
        return []

    aux_map = _build_aux_map(active_symbols, bars_map)

    # ── 2. Sweep all strategies ──────────────────────────────────────────────
    all_results: list[SweepResult] = []
    total_strategies = len(ALL_STRATEGIES)
    grid_size = 3 * 3 * 3  # rsi_period × sl_pct × tp_pct

    # Composite has an extra threshold dimension — we sweep it separately
    non_composite = [s for s in ALL_STRATEGIES if s is not SapphireComposite]
    composite_extra_combos = grid_size * len(COMPOSITE_THRESHOLDS)
    total_backtests = grid_size * len(active_symbols) * len(non_composite) + composite_extra_combos * len(active_symbols)
    print(f"\n── Running sweeps ({total_backtests} total backtests across {total_strategies} strategies) ──")

    for i, strat_cls in enumerate(non_composite, 1):
        t1 = time.time()
        results = sweep_params(strat_cls, active_symbols, bars_map, aux_map, bankroll)
        all_results.extend(results)
        elapsed = time.time() - t1
        profitable = sum(1 for r in results if r.total_return_pct > 0)
        log.info("[%d/%d] %-30s  %3d backtests  %d profitable  %.1fs",
                 i, total_strategies, strat_cls.__name__, len(results), profitable, elapsed)

    # SapphireComposite: also sweep composite_threshold
    log.info("Sweeping SapphireComposite with threshold range %s...", COMPOSITE_THRESHOLDS)
    engine = BacktestEngine(bankroll=bankroll)
    import itertools as _it

    from lib.analytics.strategies import PARAM_GRID
    for thresh, *combo_vals in _it.product(COMPOSITE_THRESHOLDS, *PARAM_GRID.values()):
        keys = list(PARAM_GRID.keys())
        params = StrategyParams(
            composite_threshold=thresh,
            **dict(zip(keys, combo_vals, strict=False)),
        )
        strat = SapphireComposite(params)
        for sym in active_symbols:
            bars = bars_map.get(sym, [])
            if len(bars) < 25:
                continue
            report = engine.run(bars, strat, sym, aux_map.get(sym, {}))
            all_results.append(SweepResult(
                strategy_cls=SapphireComposite.__name__,
                strategy_name=strat.name,
                symbol=sym,
                rsi_period=params.rsi_period,
                sl_pct=params.sl_pct,
                tp_pct=params.tp_pct,
                sortino=report.sortino,
                sharpe=report.sharpe,
                total_return_pct=report.total_return_pct,
                win_rate=report.win_rate,
                profit_factor=report.profit_factor,
                max_drawdown_pct=report.max_drawdown_pct,
                calmar=report.calmar,
                total_trades=report.total_trades,
                report=report,
            ))
    composite_count = sum(1 for r in all_results if r.strategy_cls == "SapphireComposite")
    log.info("[5/5] %-30s  %3d backtests  %d profitable",
             "SapphireComposite", composite_count,
             sum(1 for r in all_results if r.strategy_cls == "SapphireComposite" and r.total_return_pct > 0))

    if not all_results:
        log.error("No results produced — all bar loads failed?")
        return []

    # ── 3. Save full sweep ───────────────────────────────────────────────────
    save_path = save_results(all_results)
    print(f"\nFull sweep ({len(all_results)} backtests) saved → {save_path.relative_to(_ROOT)}")

    # ── 4. Best params per (strategy, symbol) ───────────────────────────────
    best = compare(best_per_symbol(all_results))

    # Save best-only results as a separate leaner file
    ts_tag = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    best_path = save_path.parent / f"best_per_symbol_{ts_tag}.json"
    import json
    best_path.write_text(json.dumps({
        "computed_at": datetime.now(UTC).isoformat(),
        "note": "Best Sortino params per (strategy_cls, symbol)",
        "results": [r.to_dict(include_report=True) for r in best],
    }, indent=2))
    print(f"Best params ({len(best)} rows) saved → {best_path.relative_to(_ROOT)}")

    # ── 5. Comparison table ──────────────────────────────────────────────────
    print("\n")
    print(format_table(
        best,
        title="Sapphire Strategy Comparison — best params per (strategy × symbol)",
        top_n=len(best),
    ))

    _print_strategy_summary(best)

    total_time = time.time() - t0
    print(f"\n✓ Done in {total_time:.1f}s")
    return best


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Sapphire multi-strategy sweep runner")
    p.add_argument("--days",     type=int,   default=90,       help="Lookback window (default: 90)")
    p.add_argument("--bankroll", type=float, default=10_000.0, help="Starting capital (default: 10000)")
    args = p.parse_args()
    run(days=args.days, bankroll=args.bankroll)
