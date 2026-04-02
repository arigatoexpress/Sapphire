#!/usr/bin/env python3
"""
Official top-crypto data pull + Smart Money Breakout backtest report.

Outputs:
  output/backtests/official_test_<YYYY-MM-DD>/
    - data/top_symbols.csv
    - data/<SYMBOL>_daily.csv
    - charts/*.png
    - backtest_results.csv
    - report.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import yfinance as yf

COINGECKO_MARKETS = "https://api.coingecko.com/api/v3/coins/markets"
STABLE_OR_DERIVATIVE = {
    "USDT",
    "USDC",
    "DAI",
    "USDE",
    "FDUSD",
    "BUSD",
    "TUSD",
    "USDS",
    "WSTETH",
    "STETH",
    "WBTC",
    "WETH",
}
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{2,10}$")


@dataclass
class BacktestResult:
    symbol: str
    bars: int
    trades: int
    win_rate_pct: float
    total_return_pct: float
    max_drawdown_pct: float
    avg_trade_return_pct: float
    profit_factor: float


def fetch_top_crypto_symbols(top_n: int) -> pd.DataFrame:
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 50,
        "page": 1,
        "sparkline": "false",
    }
    resp = requests.get(COINGECKO_MARKETS, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    rows = []
    for row in data:
        sym = str(row.get("symbol", "")).upper().strip()
        if not sym or sym in STABLE_OR_DERIVATIVE:
            continue
        if not SYMBOL_PATTERN.match(sym):
            continue
        rows.append(
            {
                "id": row.get("id"),
                "symbol": sym,
                "name": row.get("name"),
                "market_cap": float(row.get("market_cap") or 0.0),
                "rank": int(row.get("market_cap_rank") or 99999),
            }
        )
    df = pd.DataFrame(rows).sort_values(["rank", "market_cap"], ascending=[True, False])
    return df.head(top_n).reset_index(drop=True)


def download_ohlcv(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    ticker = f"{symbol}-USD"
    df = yf.download(
        tickers=ticker,
        start=start_date,
        end=end_date,
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    if df is None or df.empty:
        return pd.DataFrame()
    # yfinance can return multi-index columns depending on version
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    needed = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        return pd.DataFrame()
    out = df[needed].copy()
    out.columns = [c.lower() for c in out.columns]
    out.index = pd.to_datetime(out.index).tz_localize(None)
    out = out.dropna()
    return out


def _is_pivot_high(high: np.ndarray, center: int, swing: int) -> bool:
    left = center - swing
    right = center + swing
    if left < 0 or right >= len(high):
        return False
    window = high[left : right + 1]
    return bool(high[center] >= np.max(window))


def _is_pivot_low(low: np.ndarray, center: int, swing: int) -> bool:
    left = center - swing
    right = center + swing
    if left < 0 or right >= len(low):
        return False
    window = low[left : right + 1]
    return bool(low[center] <= np.min(window))


def run_smart_money_backtest(
    df: pd.DataFrame,
    swing_size: int = 25,
    rr: float = 1.0,
    fee_per_side_pct: float = 0.04,
) -> Tuple[BacktestResult, pd.Series]:
    """
    Simplified port of the Smart Money Breakout mechanics:
    - BOS on close break of active pivot
    - TP/SL derived from breakout structure distance
    - single active position at a time
    """
    close = df["close"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    idx = df.index

    prev_high = np.nan
    prev_low = np.nan
    prev_high_idx = -1
    prev_low_idx = -1
    high_active = False
    low_active = False

    pos = 0  # 1 long, -1 short, 0 flat
    entry = 0.0
    tp = np.nan
    sl = np.nan
    trade_returns: List[float] = []
    equity = [1.0]
    equity_index = [idx[0]]

    for i in range(len(df)):
        # pivot confirmation arrives with swing delay
        pivot_center = i - swing_size
        if pivot_center >= swing_size:
            if _is_pivot_high(high, pivot_center, swing_size):
                piv_hi = float(high[pivot_center])
                prev_high = piv_hi
                prev_high_idx = pivot_center
                high_active = True
            if _is_pivot_low(low, pivot_center, swing_size):
                piv_lo = float(low[pivot_center])
                prev_low = piv_lo
                prev_low_idx = pivot_center
                low_active = True

        high_broken = bool(high_active and not np.isnan(prev_high) and close[i] > prev_high)
        low_broken = bool(low_active and not np.isnan(prev_low) and close[i] < prev_low)
        if high_broken:
            high_active = False
        if low_broken:
            low_active = False

        # manage open trade exits first (bar-extreme execution)
        if pos != 0:
            hit_tp = (high[i] >= tp) if pos > 0 else (low[i] <= tp)
            hit_sl = (low[i] <= sl) if pos > 0 else (high[i] >= sl)
            if hit_tp or hit_sl:
                # conservative: if both touched same bar, assume SL first
                if hit_tp and hit_sl:
                    exit_px = sl
                elif hit_tp:
                    exit_px = tp
                else:
                    exit_px = sl

                gross = (exit_px - entry) / entry if pos > 0 else (entry - exit_px) / entry
                net = gross - (2 * fee_per_side_pct / 100.0)
                trade_returns.append(net)
                equity.append(equity[-1] * (1.0 + net))
                equity_index.append(idx[i])
                pos = 0
                entry = 0.0
                tp = np.nan
                sl = np.nan

        # new structure breakout -> enter/reverse
        if high_broken or low_broken:
            if high_broken and prev_high_idx >= 0:
                length = max(1, i - prev_high_idx)
                lo = float(np.min(low[max(0, i - length + 1) : i + 1]))
                hi = float(np.max(high[max(0, i - length + 1) : i + 1]))
                dist = (hi - lo) / 3.0
                new_pos = 1
                new_tp = float(prev_high + dist)
                new_sl = float(prev_high - (dist / rr))
            elif low_broken and prev_low_idx >= 0:
                length = max(1, i - prev_low_idx)
                lo = float(np.min(low[max(0, i - length + 1) : i + 1]))
                hi = float(np.max(high[max(0, i - length + 1) : i + 1]))
                dist = (hi - lo) / 3.0
                new_pos = -1
                new_tp = float(prev_low - dist)
                new_sl = float(prev_low + (dist / rr))
            else:
                continue

            # close opposite position at market close before reversing
            if pos != 0 and pos != new_pos and entry > 0:
                gross = (close[i] - entry) / entry if pos > 0 else (entry - close[i]) / entry
                net = gross - (2 * fee_per_side_pct / 100.0)
                trade_returns.append(net)
                equity.append(equity[-1] * (1.0 + net))
                equity_index.append(idx[i])
                pos = 0
                entry = 0.0

            if pos == 0:
                pos = new_pos
                entry = float(close[i])
                tp = new_tp
                sl = new_sl

    # close open trade at final close
    if pos != 0 and entry > 0:
        final_close = float(close[-1])
        gross = (final_close - entry) / entry if pos > 0 else (entry - final_close) / entry
        net = gross - (2 * fee_per_side_pct / 100.0)
        trade_returns.append(net)
        equity.append(equity[-1] * (1.0 + net))
        equity_index.append(idx[-1])

    if not trade_returns:
        trade_returns = [0.0]

    tr = np.array(trade_returns, dtype=float)
    wins = tr[tr > 0]
    losses = tr[tr < 0]
    win_rate = float((len(wins) / len(tr)) * 100.0) if len(tr) else 0.0
    total_ret = float((np.prod(1.0 + tr) - 1.0) * 100.0)
    avg_trade = float(np.mean(tr) * 100.0)
    profit_factor = float(np.sum(wins) / abs(np.sum(losses))) if len(losses) else math.inf

    eq = pd.Series(equity, index=pd.to_datetime(equity_index), name="equity").sort_index()
    rolling_peak = eq.cummax()
    dd = (eq / rolling_peak) - 1.0
    max_dd = float(dd.min() * 100.0) if not dd.empty else 0.0

    result = BacktestResult(
        symbol="",
        bars=len(df),
        trades=len(tr),
        win_rate_pct=round(win_rate, 2),
        total_return_pct=round(total_ret, 2),
        max_drawdown_pct=round(max_dd, 2),
        avg_trade_return_pct=round(avg_trade, 3),
        profit_factor=round(float(profit_factor), 3) if np.isfinite(profit_factor) else float("inf"),
    )
    return result, eq


def make_visuals(
    out_dir: Path,
    price_frames: Dict[str, pd.DataFrame],
    equities: Dict[str, pd.Series],
    results_df: pd.DataFrame,
) -> None:
    chart_dir = out_dir / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)

    # 1) Normalized price performance
    perf = pd.DataFrame(
        {
            sym: (df["close"] / df["close"].iloc[0]) * 100.0
            for sym, df in price_frames.items()
            if not df.empty
        }
    ).dropna(how="all")
    if not perf.empty:
        plt.figure(figsize=(13, 7))
        for col in perf.columns:
            plt.plot(perf.index, perf[col], label=col, linewidth=1.6)
        plt.title("Top Crypto Normalized Performance (Base = 100)")
        plt.ylabel("Index (Base 100)")
        plt.xlabel("Date")
        plt.legend(ncol=4, fontsize=9)
        plt.grid(alpha=0.2)
        plt.tight_layout()
        plt.savefig(chart_dir / "normalized_performance.png", dpi=150)
        plt.close()

    # 2) Strategy equity curves
    if equities:
        eq_df = pd.DataFrame({k: v for k, v in equities.items()}).dropna(how="all")
        plt.figure(figsize=(13, 7))
        for col in eq_df.columns:
            plt.plot(eq_df.index, eq_df[col], label=col, linewidth=1.6)
        plt.title("Smart Money Breakout Backtest Equity Curves")
        plt.ylabel("Equity (Initial = 1.0)")
        plt.xlabel("Date")
        plt.legend(ncol=4, fontsize=9)
        plt.grid(alpha=0.2)
        plt.tight_layout()
        plt.savefig(chart_dir / "strategy_equity_curves.png", dpi=150)
        plt.close()

    # 3) Risk/return summary bars
    if not results_df.empty:
        plot_df = results_df.sort_values("total_return_pct", ascending=False)
        fig, ax1 = plt.subplots(figsize=(13, 7))
        x = np.arange(len(plot_df))
        ax1.bar(x - 0.2, plot_df["total_return_pct"], width=0.4, label="Total Return %")
        ax1.bar(x + 0.2, plot_df["max_drawdown_pct"], width=0.4, label="Max Drawdown %")
        ax1.set_xticks(x)
        ax1.set_xticklabels(plot_df["symbol"], rotation=45, ha="right")
        ax1.set_ylabel("Percent")
        ax1.set_title("Backtest Return vs Drawdown")
        ax1.axhline(0, color="black", linewidth=0.8)
        ax1.legend()
        ax1.grid(alpha=0.2, axis="y")
        plt.tight_layout()
        plt.savefig(chart_dir / "return_drawdown_summary.png", dpi=150)
        plt.close()


def write_report(
    out_dir: Path,
    start_date: str,
    symbols_df: pd.DataFrame,
    results_df: pd.DataFrame,
) -> None:
    report = out_dir / "report.md"
    generated_at = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    top_line = ""
    if not results_df.empty:
        best = results_df.sort_values("total_return_pct", ascending=False).iloc[0]
        top_line = (
            f"- Best total return: **{best['symbol']}** "
            f"({best['total_return_pct']:.2f}%, win-rate {best['win_rate_pct']:.2f}%)."
        )

    lines = [
        "# Official Backtest: Top Crypto Smart Money Breakout",
        "",
        f"- Generated: `{generated_at}`",
        f"- Data start: `{start_date}`",
        "- Data source ranking: CoinGecko market-cap top list (spot majors, stable/wrapped filtered).",
        "- OHLCV source: Yahoo Finance daily candles (`*-USD`).",
        "- Strategy test harness: Smart Money Breakout (BOS pivots, TP/SL distance model, single position per symbol).",
        "",
        "## Universe",
        "",
        symbols_df.to_markdown(index=False) if not symbols_df.empty else "_No symbols resolved._",
        "",
        "## Backtest Summary",
        "",
        results_df.to_markdown(index=False) if not results_df.empty else "_No results generated._",
        "",
        "## Key Findings",
        "",
        top_line if top_line else "- No valid strategy results were produced.",
        "- Risk check: use drawdown and profit-factor together; return alone is not sufficient.",
        "- Next iteration: move to 1h or 4h candles + exchange-native fills for closer live fidelity.",
        "",
        "## Charts",
        "",
        "1. `charts/normalized_performance.png`",
        "2. `charts/strategy_equity_curves.png`",
        "3. `charts/return_drawdown_summary.png`",
        "",
    ]
    report.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default="2024-01-01")
    parser.add_argument("--top-n", type=int, default=8)
    parser.add_argument("--out-root", default="output/backtests")
    parser.add_argument("--swing-size", type=int, default=25)
    args = parser.parse_args()

    today = dt.date.today().isoformat()
    out_dir = Path(args.out_root) / f"official_test_{today}"
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    top_symbols_df = fetch_top_crypto_symbols(args.top_n)
    top_symbols_df.to_csv(data_dir / "top_symbols.csv", index=False)

    price_frames: Dict[str, pd.DataFrame] = {}
    equity_curves: Dict[str, pd.Series] = {}
    rows: List[Dict[str, object]] = []
    end_date = (dt.date.today() + dt.timedelta(days=1)).isoformat()

    for _, row in top_symbols_df.iterrows():
        sym = str(row["symbol"]).upper().strip()
        try:
            df = download_ohlcv(sym, start_date=args.start_date, end_date=end_date)
        except Exception:
            continue
        if df.empty or len(df) < (args.swing_size * 3):
            continue

        df.to_csv(data_dir / f"{sym}_daily.csv")
        price_frames[sym] = df
        bt, eq = run_smart_money_backtest(df, swing_size=args.swing_size)
        bt.symbol = sym
        equity_curves[sym] = eq
        rows.append(
            {
                "symbol": bt.symbol,
                "bars": bt.bars,
                "trades": bt.trades,
                "win_rate_pct": bt.win_rate_pct,
                "total_return_pct": bt.total_return_pct,
                "max_drawdown_pct": bt.max_drawdown_pct,
                "avg_trade_return_pct": bt.avg_trade_return_pct,
                "profit_factor": bt.profit_factor,
            }
        )

    results_df = pd.DataFrame(rows).sort_values("total_return_pct", ascending=False)
    results_df.to_csv(out_dir / "backtest_results.csv", index=False)
    make_visuals(out_dir, price_frames, equity_curves, results_df)
    write_report(out_dir, args.start_date, top_symbols_df, results_df)

    summary = {
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "start_date": args.start_date,
        "top_n_requested": args.top_n,
        "symbols_tested": int(len(results_df)),
        "output_dir": str(out_dir.resolve()),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
