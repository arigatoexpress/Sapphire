#!/usr/bin/env python3
"""
HFT Indicator Strategy Suite Backtester

Strategies:
1) LuxAlgo Market Structure Break + OB probability (ported logic)
2) ChartPrime Trendline Breakouts With Targets (ported logic)

Runs on Binance Vision futures klines for HFT timeframes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import math
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests

BINANCE_VISION_BASE = "https://data.binance.vision/data/futures/um/monthly/klines"
KLINE_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_asset_volume",
    "number_of_trades",
    "taker_buy_base_asset_volume",
    "taker_buy_quote_asset_volume",
    "ignore",
]

TF_CANONICAL = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "60m": "1h",
}


def _normalize_symbols(raw: str) -> List[str]:
    out, seen = [], set()
    for tok in raw.split(','):
        s = tok.strip().upper()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out or ["BTC", "ETH", "SOL"]


def _normalize_timeframes(raw: str) -> List[str]:
    out, seen = [], set()
    for tok in raw.split(','):
        k = tok.strip().lower().replace(' ', '')
        tf = TF_CANONICAL.get(k)
        if not tf or tf in seen:
            continue
        seen.add(tf)
        out.append(tf)
    return out or ["1m", "5m", "15m"]


def _month_iter(start_date: dt.date, end_date_exclusive: dt.date):
    cur = dt.date(start_date.year, start_date.month, 1)
    end_month = dt.date(end_date_exclusive.year, end_date_exclusive.month, 1)
    while cur < end_month:
        yield cur
        if cur.month == 12:
            cur = dt.date(cur.year + 1, 1, 1)
        else:
            cur = dt.date(cur.year, cur.month + 1, 1)


def _parse_zip_csv(blob: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = zf.namelist()
        if not names:
            return pd.DataFrame()
        with zf.open(names[0]) as fh:
            df = pd.read_csv(fh, header=0)

    if df.empty:
        return df
    if "open_time" not in df.columns:
        df.columns = KLINE_COLUMNS[: len(df.columns)]

    needed = ["open_time", "open", "high", "low", "close", "volume"]
    if any(c not in df.columns for c in needed):
        return pd.DataFrame()

    out = df[needed].copy()
    out["open_time"] = pd.to_numeric(out["open_time"], errors="coerce")
    for col in ["open", "high", "low", "close", "volume"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["open_time"] = pd.to_datetime(out["open_time"], unit="ms", utc=True, errors="coerce")
    out = out.dropna().sort_values("open_time")
    out = out.set_index("open_time")
    return out


def download_klines(symbol: str, timeframe: str, start_date: dt.date, end_date_exclusive: dt.date) -> pd.DataFrame:
    pair = f"{symbol}USDT"
    sess = requests.Session()
    frames: List[pd.DataFrame] = []

    for m in _month_iter(start_date, end_date_exclusive):
        ym = f"{m.year:04d}-{m.month:02d}"
        url = f"{BINANCE_VISION_BASE}/{pair}/{timeframe}/{pair}-{timeframe}-{ym}.zip"
        try:
            r = sess.get(url, timeout=40)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            part = _parse_zip_csv(r.content)
            if not part.empty:
                frames.append(part)
        except Exception:
            continue

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames).sort_index()
    start_ts = pd.Timestamp(start_date, tz="UTC")
    end_ts = pd.Timestamp(end_date_exclusive, tz="UTC")
    df = df[(df.index >= start_ts) & (df.index < end_ts)]
    df = df[~df.index.duplicated(keep="first")]
    return df


def _pivot_flags(high: np.ndarray, low: np.ndarray, left: int, right: int) -> Tuple[np.ndarray, np.ndarray]:
    n = len(high)
    piv_hi = np.zeros(n, dtype=bool)
    piv_lo = np.zeros(n, dtype=bool)
    win = left + right + 1

    hs = pd.Series(high)
    ls = pd.Series(low)
    roll_max = hs.rolling(window=win, min_periods=win).max().to_numpy()
    roll_min = ls.rolling(window=win, min_periods=win).min().to_numpy()

    for i in range(win - 1, n):
        c = i - right
        if c - left < 0:
            continue
        if high[c] >= roll_max[i]:
            piv_hi[c] = True
        if low[c] <= roll_min[i]:
            piv_lo[c] = True
    return piv_hi, piv_lo


def _build_metrics(strategy: str, symbol: str, timeframe: str, eq: pd.Series, trade_pnls: List[float], liquidations: int) -> Dict[str, object]:
    if eq.empty:
        return {}

    trades = len(trade_pnls)
    tr = np.array(trade_pnls if trade_pnls else [0.0], dtype=float)
    wins = tr[tr > 0]
    losses = tr[tr < 0]

    win_rate = (len(wins) / max(1, trades)) * 100.0
    total_return_pct = (float(eq.iloc[-1]) - 1.0) * 100.0

    peak = eq.cummax()
    dd = (eq / peak) - 1.0
    max_dd_pct = float(dd.min() * 100.0) if not dd.empty else 0.0

    rets = eq.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    if len(rets) > 2 and float(rets.std()) > 0:
        annual = {"1m": 525600, "3m": 175200, "5m": 105120, "15m": 35040, "1h": 8760}.get(timeframe, 525600)
        sharpe = float((rets.mean() / rets.std()) * np.sqrt(annual))
    else:
        sharpe = 0.0

    pf = float(wins.sum() / abs(losses.sum())) if len(losses) else float("inf")

    end_ts = pd.Timestamp(eq.index[-1])
    def wret(days: int) -> float:
        s = end_ts - pd.Timedelta(days=days)
        sv = float(eq.asof(s)) if not pd.isna(eq.asof(s)) else float(eq.iloc[0])
        ev = float(eq.iloc[-1])
        return ((ev / sv) - 1.0) * 100.0 if sv > 0 else float("nan")

    if getattr(end_ts, "tzinfo", None) is not None:
        ytd_start = pd.Timestamp(year=end_ts.year, month=1, day=1, tz=end_ts.tz)
    else:
        ytd_start = pd.Timestamp(year=end_ts.year, month=1, day=1)
    ytd_start_val = float(eq.asof(ytd_start)) if not pd.isna(eq.asof(ytd_start)) else float(eq.iloc[0])
    ytd = ((float(eq.iloc[-1]) / ytd_start_val) - 1.0) * 100.0 if ytd_start_val > 0 else float("nan")

    return {
        "strategy": strategy,
        "symbol": symbol,
        "timeframe": timeframe,
        "bars": int(len(eq)),
        "trades": int(trades),
        "win_rate_pct": round(float(win_rate), 2),
        "total_return_pct": round(float(total_return_pct), 2),
        "max_drawdown_pct": round(float(max_dd_pct), 2),
        "sharpe": round(float(sharpe), 3),
        "profit_factor": round(float(pf), 3) if np.isfinite(pf) else float("inf"),
        "liquidation_count": int(liquidations),
        "pnl_7d_pct": round(float(wret(7)), 2),
        "pnl_30d_pct": round(float(wret(30)), 2),
        "pnl_90d_pct": round(float(wret(90)), 2),
        "pnl_180d_pct": round(float(wret(180)), 2),
        "pnl_ytd_pct": round(float(ytd), 2),
    }


def _apply_trade(equity: float, risk_frac: float, leverage: float, move: float, fee_pct: float) -> Tuple[float, float]:
    # move is raw price return (e.g., +0.002)
    pnl_frac = (risk_frac * leverage * move) - (2.0 * risk_frac * leverage * fee_pct)
    equity = max(1e-9, equity * (1.0 + pnl_frac))
    return equity, pnl_frac


def backtest_luxalgo_msb_ob(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    pivot_len: int = 7,
    z_threshold: float = 0.5,
    leverage: float = 12.0,
    risk_frac: float = 0.08,
    fee_pct: float = 0.0002,
) -> Tuple[Dict[str, object], pd.Series]:
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    open_ = df["open"].to_numpy(dtype=float)
    idx = pd.to_datetime(df.index)

    price_change = np.diff(close, prepend=close[0])
    mom_avg = pd.Series(price_change).rolling(50, min_periods=10).mean().to_numpy()
    mom_std = pd.Series(price_change).rolling(50, min_periods=10).std(ddof=0).replace(0, np.nan).to_numpy()
    momentum_z = (price_change - mom_avg) / mom_std
    momentum_z = np.nan_to_num(momentum_z)

    piv_hi, piv_lo = _pivot_flags(high, low, left=pivot_len, right=pivot_len)

    last_ph = np.nan
    last_pl = np.nan

    pos = 0
    entry = 0.0
    tp = np.nan
    sl = np.nan

    equity = 1.0
    eq_vals = [equity]
    eq_idx = [idx[0]]
    trade_pnls: List[float] = []
    liquidations = 0

    for i in range(len(df)):
        if piv_hi[i]:
            last_ph = high[i]
        if piv_lo[i]:
            last_pl = low[i]

        # exit first
        if pos != 0:
            if pos > 0:
                hit_tp = high[i] >= tp
                hit_sl = low[i] <= sl
                if hit_tp or hit_sl:
                    exit_px = sl if hit_sl else tp
                    move = (exit_px - entry) / entry
                    equity, pnl = _apply_trade(equity, risk_frac, leverage, move, fee_pct)
                    trade_pnls.append(pnl)
                    pos = 0
            else:
                hit_tp = low[i] <= tp
                hit_sl = high[i] >= sl
                if hit_tp or hit_sl:
                    exit_px = sl if hit_sl else tp
                    move = (entry - exit_px) / entry
                    equity, pnl = _apply_trade(equity, risk_frac, leverage, move, fee_pct)
                    trade_pnls.append(pnl)
                    pos = 0

        is_bull = (not np.isnan(last_ph)) and (close[i] > last_ph) and (close[i - 1] <= last_ph if i > 0 else False) and (momentum_z[i] > z_threshold)
        is_bear = (not np.isnan(last_pl)) and (close[i] < last_pl) and (close[i - 1] >= last_pl if i > 0 else False) and (momentum_z[i] < -z_threshold)

        if pos == 0 and (is_bull or is_bear):
            # OB candle search (last opposite body candle in prior 10 bars)
            ob_idx = None
            max_lookback = min(10, i)
            for j in range(1, max_lookback + 1):
                if is_bull and close[i - j] < open_[i - j]:
                    ob_idx = i - j
                    break
                if is_bear and close[i - j] > open_[i - j]:
                    ob_idx = i - j
                    break

            if ob_idx is None:
                eq_vals.append(equity)
                eq_idx.append(idx[i])
                continue

            ob_top = high[ob_idx]
            ob_bot = low[ob_idx]
            ob_range = max(1e-9, ob_top - ob_bot)

            entry = close[i]
            if is_bull:
                pos = 1
                tp = entry + (ob_range * 1.2)
                sl = ob_bot - (ob_range * 0.25)
            else:
                pos = -1
                tp = entry - (ob_range * 1.2)
                sl = ob_top + (ob_range * 0.25)

            # liquidation guard
            if leverage > 0:
                if pos > 0 and low[i] <= entry * (1 - 0.90 / leverage):
                    equity = max(1e-9, equity * (1 - risk_frac * 0.95))
                    trade_pnls.append(-risk_frac * 0.95)
                    liquidations += 1
                    pos = 0
                elif pos < 0 and high[i] >= entry * (1 + 0.90 / leverage):
                    equity = max(1e-9, equity * (1 - risk_frac * 0.95))
                    trade_pnls.append(-risk_frac * 0.95)
                    liquidations += 1
                    pos = 0

        eq_vals.append(equity)
        eq_idx.append(idx[i])

    # close at last bar
    if pos != 0 and entry > 0:
        final_close = close[-1]
        move = (final_close - entry) / entry if pos > 0 else (entry - final_close) / entry
        equity, pnl = _apply_trade(equity, risk_frac, leverage, move, fee_pct)
        trade_pnls.append(pnl)

    eq = pd.Series(eq_vals, index=pd.to_datetime(eq_idx), name="equity").sort_index()
    eq = eq[~eq.index.duplicated(keep="last")]
    metrics = _build_metrics("luxalgo_msb_ob", symbol, timeframe, eq, trade_pnls, liquidations)
    return metrics, eq


def backtest_chartprime_tbt(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    period: int = 10,
    leverage: float = 12.0,
    risk_frac: float = 0.08,
    fee_pct: float = 0.0002,
    cooldown_bars: int = 2,
) -> Tuple[Dict[str, object], pd.Series]:
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    idx = pd.to_datetime(df.index)

    right = max(1, period // 2)
    left = period

    piv_hi, piv_lo = _pivot_flags(high, low, left=left, right=right)

    # ATR-based zband proxy with 20-bar lag and half scaling
    tr = pd.Series(np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1)))))
    tr.iloc[0] = high[0] - low[0]
    atr30 = tr.rolling(30, min_periods=10).mean().to_numpy()
    vol_adj = np.minimum(atr30 * 0.3, close * 0.003)
    zband = pd.Series(vol_adj).shift(20).bfill().fillna(0).to_numpy() / 2.0

    high_pivots: List[Tuple[int, float]] = []
    low_pivots: List[Tuple[int, float]] = []

    pos = 0
    entry = 0.0
    tp = np.nan
    sl = np.nan
    last_entry_bar = -10_000

    equity = 1.0
    eq_vals = [equity]
    eq_idx = [idx[0]]
    trade_pnls: List[float] = []
    liquidations = 0

    for i in range(len(df)):
        if piv_hi[i]:
            high_pivots.append((i, high[i]))
            if len(high_pivots) > 5:
                high_pivots.pop(0)
        if piv_lo[i]:
            low_pivots.append((i, low[i]))
            if len(low_pivots) > 5:
                low_pivots.pop(0)

        # manage exits
        if pos > 0:
            hit_tp = high[i] >= tp
            hit_sl = close[i] <= sl
            if hit_tp or hit_sl:
                exit_px = sl if hit_sl else tp
                move = (exit_px - entry) / entry
                equity, pnl = _apply_trade(equity, risk_frac, leverage, move, fee_pct)
                trade_pnls.append(pnl)
                pos = 0
        elif pos < 0:
            hit_tp = low[i] <= tp
            hit_sl = close[i] >= sl
            if hit_tp or hit_sl:
                exit_px = sl if hit_sl else tp
                move = (entry - exit_px) / entry
                equity, pnl = _apply_trade(equity, risk_frac, leverage, move, fee_pct)
                trade_pnls.append(pnl)
                pos = 0

        if pos == 0 and (i - last_entry_bar) >= cooldown_bars:
            long_signal = False
            short_signal = False

            if len(high_pivots) >= 2:
                (x1, y1), (x2, y2) = high_pivots[-2], high_pivots[-1]
                if x2 > x1:
                    slope = (y2 - y1) / (x2 - x1)
                    if slope < 0 and i > x2:
                        line_prev = y2 + slope * ((i - 1) - x2)
                        line_now = y2 + slope * (i - x2)
                        if close[i - 1] < line_prev and close[i] > line_now:
                            long_signal = True

            if len(low_pivots) >= 2:
                (x1, y1), (x2, y2) = low_pivots[-2], low_pivots[-1]
                if x2 > x1:
                    slope = (y2 - y1) / (x2 - x1)
                    if slope > 0 and i > x2:
                        line_prev = y2 + slope * ((i - 1) - x2)
                        line_now = y2 + slope * (i - x2)
                        if close[i - 1] > (line_prev - (zband[i] * 0.1)) and close[i] < (line_now - (zband[i] * 0.1)):
                            short_signal = True

            if long_signal or short_signal:
                entry = close[i]
                if long_signal:
                    pos = 1
                    tp = high[i] + (zband[i] * 20.0)
                    sl = low[i] - (zband[i] * 20.0)
                else:
                    pos = -1
                    tp = low[i] - (zband[i] * 20.0)
                    sl = high[i] + (zband[i] * 20.0)
                last_entry_bar = i

                if leverage > 0:
                    if pos > 0 and low[i] <= entry * (1 - 0.90 / leverage):
                        equity = max(1e-9, equity * (1 - risk_frac * 0.95))
                        trade_pnls.append(-risk_frac * 0.95)
                        liquidations += 1
                        pos = 0
                    elif pos < 0 and high[i] >= entry * (1 + 0.90 / leverage):
                        equity = max(1e-9, equity * (1 - risk_frac * 0.95))
                        trade_pnls.append(-risk_frac * 0.95)
                        liquidations += 1
                        pos = 0

        eq_vals.append(equity)
        eq_idx.append(idx[i])

    if pos != 0 and entry > 0:
        final_close = close[-1]
        move = (final_close - entry) / entry if pos > 0 else (entry - final_close) / entry
        equity, pnl = _apply_trade(equity, risk_frac, leverage, move, fee_pct)
        trade_pnls.append(pnl)

    eq = pd.Series(eq_vals, index=pd.to_datetime(eq_idx), name="equity").sort_index()
    eq = eq[~eq.index.duplicated(keep="last")]
    metrics = _build_metrics("chartprime_tbt", symbol, timeframe, eq, trade_pnls, liquidations)
    return metrics, eq


def _plot_equity(out_dir: Path, strategy: str, symbol: str, timeframe: str, eq: pd.Series) -> None:
    cdir = out_dir / "charts"
    cdir.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(11, 5))
    plt.plot(eq.index, eq.values, linewidth=1.25)
    plt.title(f"{strategy} — {symbol} {timeframe} Equity")
    plt.grid(alpha=0.2)
    plt.tight_layout()
    plt.savefig(cdir / f"equity_{strategy}_{symbol}_{timeframe}.png", dpi=150)
    plt.close()


def _plot_heatmap(out_dir: Path, results_df: pd.DataFrame, strategy: str):
    sdf = results_df[results_df["strategy"] == strategy]
    if sdf.empty:
        return
    pivot = sdf.pivot(index="timeframe", columns="symbol", values="total_return_pct")
    tf_order = ["1m", "3m", "5m", "15m", "1h"]
    pivot = pivot.reindex([t for t in tf_order if t in pivot.index])

    arr = pivot.to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    im = ax.imshow(arr, aspect="auto", cmap="RdYlGn")
    ax.set_xticks(np.arange(len(pivot.columns)))
    ax.set_yticks(np.arange(len(pivot.index)))
    ax.set_xticklabels(pivot.columns)
    ax.set_yticklabels(pivot.index)
    ax.set_title(f"{strategy} Return Heatmap (%)")

    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            v = arr[i, j]
            txt = "--" if np.isnan(v) else f"{v:.1f}"
            ax.text(j, i, txt, ha="center", va="center", color="black", fontsize=8)

    fig.colorbar(im, ax=ax)
    plt.tight_layout()
    plt.savefig(out_dir / "charts" / f"heatmap_{strategy}.png", dpi=160)
    plt.close(fig)


def _write_report(out_dir: Path, start_date: str, end_date_exclusive: str, results_df: pd.DataFrame):
    now = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    p = out_dir / "report.md"

    lines = [
        "# HFT Indicator Strategy Suite",
        "",
        f"- Generated: `{now}`",
        f"- Data range: `{start_date}` -> `{end_date_exclusive}` (end exclusive)",
        "- Strategies: `luxalgo_msb_ob`, `chartprime_tbt`",
        "",
        "## Results",
        "",
        results_df.to_markdown(index=False) if not results_df.empty else "_No results_",
        "",
    ]

    for strat in ["luxalgo_msb_ob", "chartprime_tbt"]:
        sdf = results_df[results_df["strategy"] == strat]
        if sdf.empty:
            continue
        lines += [f"## {strat} Best Rows", ""]
        best = sdf.sort_values("total_return_pct", ascending=False).head(5)
        lines += [best.to_markdown(index=False), ""]

    p.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="BTC,ETH,SOL")
    ap.add_argument("--timeframes", default="1m,5m,15m")
    ap.add_argument("--start-date", default="2024-01-01")
    ap.add_argument("--leverage", type=float, default=12.0)
    ap.add_argument("--risk-frac", type=float, default=0.08)
    ap.add_argument("--fee-pct", type=float, default=0.0002)
    ap.add_argument("--out-root", default="output/backtests")
    args = ap.parse_args()

    symbols = _normalize_symbols(args.symbols)
    timeframes = _normalize_timeframes(args.timeframes)
    start_date = dt.date.fromisoformat(args.start_date)
    today = dt.datetime.utcnow().date()
    end_date_exclusive = dt.date(today.year, today.month, 1)

    stamp = dt.datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
    out_dir = Path(args.out_root) / f"hft_indicator_suite_{stamp}"
    (out_dir / "data").mkdir(parents=True, exist_ok=True)
    (out_dir / "charts").mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, object]] = []

    for symbol in symbols:
        for tf in timeframes:
            print(f"[fetch] {symbol} {tf} ...", flush=True)
            df = download_klines(symbol, tf, start_date, end_date_exclusive)
            if df.empty:
                print(f"[skip] {symbol} {tf}: no data", flush=True)
                continue
            df.to_csv(out_dir / "data" / f"{symbol}_{tf}.csv")

            if len(df) < 500:
                print(f"[skip] {symbol} {tf}: too few bars", flush=True)
                continue

            lux_m, lux_eq = backtest_luxalgo_msb_ob(
                df, symbol, tf,
                leverage=args.leverage,
                risk_frac=args.risk_frac,
                fee_pct=args.fee_pct,
            )
            rows.append(lux_m)
            _plot_equity(out_dir, "luxalgo_msb_ob", symbol, tf, lux_eq)
            print(
                f"[lux] {symbol} {tf}: ret={lux_m['total_return_pct']:.2f}% dd={lux_m['max_drawdown_pct']:.2f}% trades={lux_m['trades']}",
                flush=True,
            )

            cp_m, cp_eq = backtest_chartprime_tbt(
                df, symbol, tf,
                leverage=args.leverage,
                risk_frac=args.risk_frac,
                fee_pct=args.fee_pct,
            )
            rows.append(cp_m)
            _plot_equity(out_dir, "chartprime_tbt", symbol, tf, cp_eq)
            print(
                f"[chartprime] {symbol} {tf}: ret={cp_m['total_return_pct']:.2f}% dd={cp_m['max_drawdown_pct']:.2f}% trades={cp_m['trades']}",
                flush=True,
            )

    results_df = pd.DataFrame(rows)
    if not results_df.empty:
        tf_order = {"1m": 0, "3m": 1, "5m": 2, "15m": 3}
        results_df["_tf_order"] = results_df["timeframe"].map(tf_order).fillna(99)
        results_df = results_df.sort_values(["strategy", "symbol", "_tf_order"]).drop(columns=["_tf_order"])

    results_path = out_dir / "indicator_suite_results.csv"
    results_df.to_csv(results_path, index=False)

    _plot_heatmap(out_dir, results_df, "luxalgo_msb_ob")
    _plot_heatmap(out_dir, results_df, "chartprime_tbt")
    _write_report(out_dir, start_date.isoformat(), end_date_exclusive.isoformat(), results_df)

    summary = {
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "symbols": symbols,
        "timeframes": timeframes,
        "start_date": start_date.isoformat(),
        "end_date_exclusive": end_date_exclusive.isoformat(),
        "rows": int(len(results_df)),
        "output_dir": str(out_dir.resolve()),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
