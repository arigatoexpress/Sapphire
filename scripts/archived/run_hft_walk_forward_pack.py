#!/usr/bin/env python3
"""
Safer HFT walk-forward pack for deployment gating.

Workflow:
1) Download data for symbols/timeframes.
2) Optimize parameters on validation window.
3) Re-run selected params on train and test windows.
4) Enforce strict validation risk gates.
5) Produce a single-symbol shortlist (one symbol per strategy/timeframe).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import pandas as pd

from run_hft_indicator_suite import (
    backtest_chartprime_tbt,
    backtest_luxalgo_msb_ob,
    download_klines,
)


@dataclass(frozen=True)
class ParamSet:
    leverage: float
    risk_frac: float
    cooldown_bars: int


def _normalize_symbols(raw: str) -> List[str]:
    out, seen = [], set()
    for tok in raw.split(","):
        s = tok.strip().upper()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out or ["BTC", "ETH", "SOL"]


def _normalize_timeframes(raw: str) -> List[str]:
    aliases = {"60m": "1h", "1H": "1h", "1h": "1h", "15m": "15m"}
    out, seen = [], set()
    for tok in raw.split(","):
        k = tok.strip()
        tf = aliases.get(k, aliases.get(k.lower(), k.lower()))
        if tf not in {"15m", "1h"}:
            continue
        if tf in seen:
            continue
        seen.add(tf)
        out.append(tf)
    return out or ["15m", "1h"]


def _parse_float_list(raw: str, default: List[float]) -> List[float]:
    vals = []
    for tok in raw.split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            vals.append(float(tok))
        except ValueError:
            pass
    return vals or default


def _parse_int_list(raw: str, default: List[int]) -> List[int]:
    vals = []
    for tok in raw.split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            vals.append(int(tok))
        except ValueError:
            pass
    return vals or default


def _score(metrics: Dict[str, float]) -> float:
    # Higher better. Penalize drawdown heavily.
    return (
        float(metrics.get("total_return_pct", 0.0))
        + (3.0 * float(metrics.get("sharpe", 0.0)))
        + (0.05 * float(metrics.get("win_rate_pct", 0.0)))
        + (0.6 * float(metrics.get("max_drawdown_pct", 0.0)))  # dd is negative
    )


def _passes_validation_gate(metrics: Dict[str, float], min_return_pct: float, max_drawdown_pct: float) -> bool:
    return (
        float(metrics.get("total_return_pct", -9999.0)) >= min_return_pct
        and float(metrics.get("max_drawdown_pct", -9999.0)) >= max_drawdown_pct
        and float(metrics.get("liquidation_count", 0)) == 0
    )


def _run_strategy(
    strategy: str,
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    p: ParamSet,
    fee_pct: float,
) -> Tuple[Dict[str, object], pd.Series]:
    if strategy == "luxalgo_msb_ob":
        return backtest_luxalgo_msb_ob(
            df=df,
            symbol=symbol,
            timeframe=timeframe,
            leverage=p.leverage,
            risk_frac=p.risk_frac,
            fee_pct=fee_pct,
        )
    if strategy == "chartprime_tbt":
        return backtest_chartprime_tbt(
            df=df,
            symbol=symbol,
            timeframe=timeframe,
            leverage=p.leverage,
            risk_frac=p.risk_frac,
            fee_pct=fee_pct,
            cooldown_bars=p.cooldown_bars,
        )
    raise ValueError(f"Unknown strategy: {strategy}")


def _plot_shortlist_curves(out_dir: Path, curve_rows: List[Tuple[str, str, str, pd.Series]]) -> None:
    cdir = out_dir / "charts"
    cdir.mkdir(parents=True, exist_ok=True)
    for strategy, symbol, timeframe, eq in curve_rows:
        plt.figure(figsize=(10.5, 4.8))
        plt.plot(eq.index, eq.values, linewidth=1.2)
        plt.title(f"Walk-Forward Test Equity — {strategy} {symbol} {timeframe}")
        plt.grid(alpha=0.2)
        plt.tight_layout()
        plt.savefig(cdir / f"wf_test_equity_{strategy}_{symbol}_{timeframe}.png", dpi=160)
        plt.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="BTC,ETH,SOL")
    ap.add_argument("--timeframes", default="15m,1h")
    ap.add_argument("--train-start", default="2024-01-01")
    ap.add_argument("--validate-start", default="2025-01-01")
    ap.add_argument("--test-start", default="2026-01-01")
    ap.add_argument("--end-date", default="")
    ap.add_argument("--leverages", default="1,2,3")
    ap.add_argument("--risk-fracs", default="0.0025,0.005,0.01")
    ap.add_argument("--cooldowns", default="2,4,8")
    ap.add_argument("--fee-pct", type=float, default=0.0005)  # 0.05%
    ap.add_argument("--min-val-return-pct", type=float, default=0.0)
    ap.add_argument("--max-val-drawdown-pct", type=float, default=-25.0)
    ap.add_argument("--out-root", default="output/backtests")
    args = ap.parse_args()

    symbols = _normalize_symbols(args.symbols)
    timeframes = _normalize_timeframes(args.timeframes)
    train_start = dt.date.fromisoformat(args.train_start)
    validate_start = dt.date.fromisoformat(args.validate_start)
    test_start = dt.date.fromisoformat(args.test_start)
    if args.end_date:
        end_date_exclusive = dt.date.fromisoformat(args.end_date)
    else:
        today = dt.datetime.utcnow().date()
        end_date_exclusive = dt.date(today.year, today.month, 1)

    leverages = _parse_float_list(args.leverages, [1.0, 2.0, 3.0])
    risk_fracs = _parse_float_list(args.risk_fracs, [0.0025, 0.005, 0.01])
    cooldowns = _parse_int_list(args.cooldowns, [2, 4, 8])

    stamp = dt.datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
    out_dir = Path(args.out_root) / f"hft_walk_forward_{stamp}"
    (out_dir / "data").mkdir(parents=True, exist_ok=True)
    (out_dir / "charts").mkdir(parents=True, exist_ok=True)

    strategies = ["luxalgo_msb_ob", "chartprime_tbt"]
    all_rows: List[Dict[str, object]] = []
    shortlist_rows: List[Dict[str, object]] = []
    shortlist_curves: List[Tuple[str, str, str, pd.Series]] = []

    for symbol in symbols:
        for tf in timeframes:
            print(f"[fetch] {symbol} {tf}", flush=True)
            df = download_klines(symbol, tf, train_start, end_date_exclusive)
            if df.empty or len(df) < 1000:
                print(f"[skip] {symbol} {tf}: insufficient data", flush=True)
                continue

            df.to_csv(out_dir / "data" / f"{symbol}_{tf}.csv")
            train_df = df[(df.index >= pd.Timestamp(train_start, tz="UTC")) & (df.index < pd.Timestamp(validate_start, tz="UTC"))]
            val_df = df[(df.index >= pd.Timestamp(validate_start, tz="UTC")) & (df.index < pd.Timestamp(test_start, tz="UTC"))]
            test_df = df[(df.index >= pd.Timestamp(test_start, tz="UTC")) & (df.index < pd.Timestamp(end_date_exclusive, tz="UTC"))]

            if len(train_df) < 500 or len(val_df) < 300 or len(test_df) < 150:
                print(f"[skip] {symbol} {tf}: not enough bars in one of train/val/test", flush=True)
                continue

            for strat in strategies:
                best_param = None
                best_val_score = -1e18
                best_val_metrics: Dict[str, object] | None = None
                best_val_pass = False

                for lev in leverages:
                    for rf in risk_fracs:
                        cds = cooldowns if strat == "chartprime_tbt" else [2]
                        for cd in cds:
                            p = ParamSet(leverage=lev, risk_frac=rf, cooldown_bars=cd)
                            val_m, _ = _run_strategy(strat, val_df, symbol, tf, p, args.fee_pct)
                            val_sc = _score(val_m)
                            val_pass = _passes_validation_gate(
                                val_m,
                                min_return_pct=args.min_val_return_pct,
                                max_drawdown_pct=args.max_val_drawdown_pct,
                            )

                            if val_pass and not best_val_pass:
                                best_param, best_val_score, best_val_metrics, best_val_pass = p, val_sc, val_m, True
                            elif val_pass and best_val_pass and val_sc > best_val_score:
                                best_param, best_val_score, best_val_metrics = p, val_sc, val_m
                            elif not best_val_pass and val_sc > best_val_score:
                                best_param, best_val_score, best_val_metrics = p, val_sc, val_m

                if best_param is None or best_val_metrics is None:
                    continue

                train_m, _ = _run_strategy(strat, train_df, symbol, tf, best_param, args.fee_pct)
                test_m, test_eq = _run_strategy(strat, test_df, symbol, tf, best_param, args.fee_pct)

                row = {
                    "strategy": strat,
                    "symbol": symbol,
                    "timeframe": tf,
                    "selected_leverage": best_param.leverage,
                    "selected_risk_frac": best_param.risk_frac,
                    "selected_cooldown_bars": best_param.cooldown_bars,
                    "val_gate_passed": bool(best_val_pass),
                    "train_return_pct": train_m.get("total_return_pct", 0.0),
                    "train_drawdown_pct": train_m.get("max_drawdown_pct", 0.0),
                    "train_sharpe": train_m.get("sharpe", 0.0),
                    "val_return_pct": best_val_metrics.get("total_return_pct", 0.0),
                    "val_drawdown_pct": best_val_metrics.get("max_drawdown_pct", 0.0),
                    "val_sharpe": best_val_metrics.get("sharpe", 0.0),
                    "val_liquidations": best_val_metrics.get("liquidation_count", 0),
                    "test_return_pct": test_m.get("total_return_pct", 0.0),
                    "test_drawdown_pct": test_m.get("max_drawdown_pct", 0.0),
                    "test_sharpe": test_m.get("sharpe", 0.0),
                    "test_liquidations": test_m.get("liquidation_count", 0),
                    "test_trades": test_m.get("trades", 0),
                    "test_pnl_7d_pct": test_m.get("pnl_7d_pct", 0.0),
                    "test_pnl_30d_pct": test_m.get("pnl_30d_pct", 0.0),
                    "test_pnl_90d_pct": test_m.get("pnl_90d_pct", 0.0),
                    "selection_score": round(best_val_score, 4),
                }
                all_rows.append(row)
                print(
                    f"[wf] {strat} {symbol} {tf}: val={row['val_return_pct']:.2f}% "
                    f"test={row['test_return_pct']:.2f}% pass={row['val_gate_passed']}",
                    flush=True,
                )

                shortlist_curves.append((strat, symbol, tf, test_eq))

    all_df = pd.DataFrame(all_rows)
    if all_df.empty:
        raise SystemExit("No walk-forward rows produced.")

    # Enforce single-symbol cap in shortlist: one symbol per strategy+timeframe.
    for (strat, tf), g in all_df.groupby(["strategy", "timeframe"]):
        gated = g[g["val_gate_passed"] == True].copy()
        pick_pool = gated if not gated.empty else g.copy()
        pick = pick_pool.sort_values(
            by=["test_return_pct", "test_sharpe", "test_drawdown_pct"],
            ascending=[False, False, False],
        ).head(1)
        shortlist_rows.extend(pick.to_dict("records"))

    shortlist_df = pd.DataFrame(shortlist_rows)
    if not shortlist_df.empty:
        # Keep only selected curves in shortlist
        wanted = {(r["strategy"], r["symbol"], r["timeframe"]) for r in shortlist_rows}
        shortlist_curves = [r for r in shortlist_curves if (r[0], r[1], r[2]) in wanted]
        _plot_shortlist_curves(out_dir, shortlist_curves)

    all_df.to_csv(out_dir / "walk_forward_all.csv", index=False)
    shortlist_df.to_csv(out_dir / "walk_forward_shortlist.csv", index=False)

    report_lines = [
        "# HFT Walk-Forward Safety Pack",
        "",
        f"- Generated: `{dt.datetime.utcnow().replace(microsecond=0).isoformat()}Z`",
        f"- Symbols: `{','.join(symbols)}`",
        f"- Timeframes: `{','.join(timeframes)}`",
        f"- Train: `{train_start}` -> `{validate_start}`",
        f"- Validate: `{validate_start}` -> `{test_start}`",
        f"- Test: `{test_start}` -> `{end_date_exclusive}` (end exclusive)",
        f"- Validation gate: `return >= {args.min_val_return_pct}%`, `drawdown >= {args.max_val_drawdown_pct}%`, `liquidations == 0`",
        "",
        "## Full Walk-Forward Results",
        "",
        all_df.to_markdown(index=False),
        "",
        "## Single-Symbol Shortlist (one symbol per strategy/timeframe)",
        "",
        shortlist_df.to_markdown(index=False) if not shortlist_df.empty else "_No shortlist rows_",
        "",
    ]
    (out_dir / "report.md").write_text("\n".join(report_lines), encoding="utf-8")

    summary = {
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "symbols": symbols,
        "timeframes": timeframes,
        "train_start": train_start.isoformat(),
        "validate_start": validate_start.isoformat(),
        "test_start": test_start.isoformat(),
        "end_date_exclusive": end_date_exclusive.isoformat(),
        "rows": int(len(all_df)),
        "shortlist_rows": int(len(shortlist_df)),
        "output_dir": str(out_dir.resolve()),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

