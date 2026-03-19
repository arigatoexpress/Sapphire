#!/usr/bin/env python3
"""
Smart Money Breakout timeframe matrix backtest.

Runs the strategy across multiple symbols and timeframes using Binance Vision
historical klines (monthly futures UM files), then writes visual analysis.

Default scope:
- Symbols: BTC, ETH, SOL
- Timeframes: 1m, 15m, 1h, 4h, 1d
- Start date: 2024-01-01
- End date: last full UTC month (monthly data completeness)

Outputs:
  output/backtests/timeframe_matrix_<YYYY-MM-DD_HHMMSS>/
    - data/<SYMBOL>_<TF>.csv
    - timeframe_backtest_results.csv
    - charts/return_heatmap.png
    - charts/winrate_heatmap.png
    - charts/drawdown_heatmap.png
    - charts/equity_<TF>.png
    - report.md
    - summary.json
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
    "1min": "1m",
    "1m": "1m",
    "15min": "15m",
    "15m": "15m",
    "1hour": "1h",
    "1h": "1h",
    "4hour": "4h",
    "4h": "4h",
    "daily": "1d",
    "1d": "1d",
    "day": "1d",
}


@dataclass
class BacktestResult:
    symbol: str
    timeframe: str
    bars: int
    trades: int
    win_rate_pct: float
    total_return_pct: float
    max_drawdown_pct: float
    avg_trade_return_pct: float
    profit_factor: float


def _normalize_timeframes(raw: str) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in raw.split(","):
        k = item.strip().lower().replace(" ", "")
        tf = TF_CANONICAL.get(k)
        if not tf or tf in seen:
            continue
        seen.add(tf)
        out.append(tf)
    return out or ["1m", "15m", "1h", "4h", "1d"]


def _normalize_symbols(raw: str) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in raw.split(","):
        s = item.strip().upper()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out or ["BTC", "ETH", "SOL"]


def _month_iter(start_date: dt.date, end_date_exclusive: dt.date):
    # Yields first day of each month where month_start < end_date_exclusive
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
            # Binance Vision monthly files are generally headered CSVs.
            # We keep a fallback path for unexpected header-less files.
            try:
                df = pd.read_csv(fh, header=0)
            except Exception:
                fh.seek(0)
                df = pd.read_csv(fh, header=None)
    if df.empty:
        return df

    # Normalize column names for either headered or header-less files.
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


def download_binance_vision_klines(
    symbol: str,
    timeframe: str,
    start_date: dt.date,
    end_date_exclusive: dt.date,
    timeout: int = 40,
) -> pd.DataFrame:
    symbol_pair = f"{symbol}USDT"
    frames: List[pd.DataFrame] = []

    sess = requests.Session()
    for month_start in _month_iter(start_date, end_date_exclusive):
        ym = f"{month_start.year:04d}-{month_start.month:02d}"
        url = f"{BINANCE_VISION_BASE}/{symbol_pair}/{timeframe}/{symbol_pair}-{timeframe}-{ym}.zip"
        try:
            r = sess.get(url, timeout=timeout)
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


def _pivot_flags(high: np.ndarray, low: np.ndarray, swing: int) -> Tuple[np.ndarray, np.ndarray]:
    # Pine-like pivot with symmetric window = 2*swing + 1 and delayed confirmation.
    window = (2 * swing) + 1
    hs = pd.Series(high)
    ls = pd.Series(low)

    roll_max = hs.rolling(window=window, center=True, min_periods=window).max().to_numpy()
    roll_min = ls.rolling(window=window, center=True, min_periods=window).min().to_numpy()

    piv_hi = np.isfinite(roll_max) & (high >= roll_max)
    piv_lo = np.isfinite(roll_min) & (low <= roll_min)
    return piv_hi, piv_lo


def run_smart_money_backtest(
    df: pd.DataFrame,
    swing_size: int = 25,
    rr: float = 1.0,
    fee_per_side_pct: float = 0.04,
) -> Tuple[BacktestResult, pd.Series]:
    close = df["close"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    idx = df.index

    piv_hi, piv_lo = _pivot_flags(high, low, swing_size)

    prev_high = np.nan
    prev_low = np.nan
    prev_high_idx = -1
    prev_low_idx = -1
    high_active = False
    low_active = False

    pos = 0
    entry = 0.0
    tp = np.nan
    sl = np.nan

    trade_returns: List[float] = []
    equity = [1.0]
    equity_index = [idx[0]]

    for i in range(len(df)):
        pivot_center = i - swing_size
        if pivot_center >= 0:
            if piv_hi[pivot_center]:
                prev_high = float(high[pivot_center])
                prev_high_idx = pivot_center
                high_active = True
            if piv_lo[pivot_center]:
                prev_low = float(low[pivot_center])
                prev_low_idx = pivot_center
                low_active = True

        high_broken = bool(high_active and not np.isnan(prev_high) and close[i] > prev_high)
        low_broken = bool(low_active and not np.isnan(prev_low) and close[i] < prev_low)
        if high_broken:
            high_active = False
        if low_broken:
            low_active = False

        # Exit checks first
        if pos != 0:
            hit_tp = (high[i] >= tp) if pos > 0 else (low[i] <= tp)
            hit_sl = (low[i] <= sl) if pos > 0 else (high[i] >= sl)
            if hit_tp or hit_sl:
                if hit_tp and hit_sl:
                    exit_px = sl  # conservative
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

        # New structure breakout => enter/reverse
        if high_broken or low_broken:
            if high_broken and prev_high_idx >= 0:
                length = max(1, i - prev_high_idx)
                w_lo = low[max(0, i - length + 1) : i + 1]
                w_hi = high[max(0, i - length + 1) : i + 1]
                dist = (float(np.max(w_hi)) - float(np.min(w_lo))) / 3.0
                new_pos = 1
                new_tp = float(prev_high + dist)
                new_sl = float(prev_high - (dist / rr))
            elif low_broken and prev_low_idx >= 0:
                length = max(1, i - prev_low_idx)
                w_lo = low[max(0, i - length + 1) : i + 1]
                w_hi = high[max(0, i - length + 1) : i + 1]
                dist = (float(np.max(w_hi)) - float(np.min(w_lo))) / 3.0
                new_pos = -1
                new_tp = float(prev_low - dist)
                new_sl = float(prev_low + (dist / rr))
            else:
                continue

            # Reverse existing opposite position at close
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

    # Force close at last close
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

    win_rate = float((len(wins) / len(tr)) * 100.0)
    total_ret = float((np.prod(1.0 + tr) - 1.0) * 100.0)
    avg_trade = float(np.mean(tr) * 100.0)
    profit_factor = float(np.sum(wins) / abs(np.sum(losses))) if len(losses) else math.inf

    eq = pd.Series(equity, index=pd.to_datetime(equity_index), name="equity").sort_index()
    rolling_peak = eq.cummax()
    dd = (eq / rolling_peak) - 1.0
    max_dd = float(dd.min() * 100.0) if not dd.empty else 0.0

    result = BacktestResult(
        symbol="",
        timeframe="",
        bars=len(df),
        trades=len(tr),
        win_rate_pct=round(win_rate, 2),
        total_return_pct=round(total_ret, 2),
        max_drawdown_pct=round(max_dd, 2),
        avg_trade_return_pct=round(avg_trade, 3),
        profit_factor=round(float(profit_factor), 3) if np.isfinite(profit_factor) else float("inf"),
    )
    return result, eq


def _plot_heatmap(df: pd.DataFrame, value_col: str, title: str, out_path: Path, cmap: str = "RdYlGn") -> None:
    if df.empty:
        return
    pivot = df.pivot(index="timeframe", columns="symbol", values=value_col)
    # enforce order
    tf_order = ["1m", "15m", "1h", "4h", "1d"]
    pivot = pivot.reindex([t for t in tf_order if t in pivot.index])

    fig, ax = plt.subplots(figsize=(8, 4.8))
    data = pivot.to_numpy(dtype=float)
    im = ax.imshow(data, aspect="auto", cmap=cmap)
    ax.set_xticks(np.arange(len(pivot.columns)))
    ax.set_yticks(np.arange(len(pivot.index)))
    ax.set_xticklabels(pivot.columns)
    ax.set_yticklabels(pivot.index)
    ax.set_title(title)

    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            v = data[i, j]
            if np.isnan(v):
                txt = "--"
            else:
                txt = f"{v:.2f}"
            ax.text(j, i, txt, ha="center", va="center", color="black", fontsize=8)

    cbar = fig.colorbar(im, ax=ax)
    cbar.ax.set_ylabel(value_col, rotation=90)
    plt.tight_layout()
    plt.savefig(out_path, dpi=160)
    plt.close(fig)


def _plot_equity_by_timeframe(equities: Dict[Tuple[str, str], pd.Series], out_dir: Path) -> None:
    if not equities:
        return
    chart_dir = out_dir / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)

    for tf in ["1m", "15m", "1h", "4h", "1d"]:
        tf_series = {sym: eq for (sym, t), eq in equities.items() if t == tf and not eq.empty}
        if not tf_series:
            continue
        plt.figure(figsize=(12, 6))
        for sym, eq in sorted(tf_series.items()):
            plt.plot(eq.index, eq.values, label=sym, linewidth=1.4)
        plt.title(f"Smart Money Breakout Equity Curves ({tf})")
        plt.xlabel("Date")
        plt.ylabel("Equity (Initial = 1.0)")
        plt.grid(alpha=0.2)
        plt.legend()
        plt.tight_layout()
        plt.savefig(chart_dir / f"equity_{tf}.png", dpi=160)
        plt.close()


def write_report(
    out_dir: Path,
    start_date: str,
    end_date_exclusive: str,
    symbols: List[str],
    timeframes: List[str],
    results_df: pd.DataFrame,
) -> None:
    report_path = out_dir / "report.md"
    now = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    lines = [
        "# Smart Money Breakout Timeframe Matrix Test",
        "",
        f"- Generated: `{now}`",
        f"- Symbols: `{', '.join(symbols)}`",
        f"- Timeframes: `{', '.join(timeframes)}`",
        f"- Data range: `{start_date}` to `{end_date_exclusive}` (end exclusive)",
        "- Data source: Binance Vision Futures UM monthly klines (offline historical files).",
        "",
        "## Results Table",
        "",
    ]

    if results_df.empty:
        lines += ["_No results generated._", ""]
    else:
        lines += [results_df.to_markdown(index=False), ""]

        lines += ["## Best Timeframe Per Symbol", ""]
        best_rows = []
        for sym in symbols:
            sdf = results_df[results_df["symbol"] == sym]
            if sdf.empty:
                continue
            best = sdf.sort_values("total_return_pct", ascending=False).iloc[0]
            best_rows.append({
                "symbol": sym,
                "best_timeframe": best["timeframe"],
                "total_return_pct": float(best["total_return_pct"]),
                "win_rate_pct": float(best["win_rate_pct"]),
                "max_drawdown_pct": float(best["max_drawdown_pct"]),
                "trades": int(best["trades"]),
            })
        if best_rows:
            lines += [pd.DataFrame(best_rows).to_markdown(index=False), ""]

    lines += [
        "## Visuals",
        "",
        "- `charts/return_heatmap.png`",
        "- `charts/winrate_heatmap.png`",
        "- `charts/drawdown_heatmap.png`",
        "- `charts/equity_1m.png`",
        "- `charts/equity_15m.png`",
        "- `charts/equity_1h.png`",
        "- `charts/equity_4h.png`",
        "- `charts/equity_1d.png`",
        "",
    ]

    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="BTC,ETH,SOL")
    parser.add_argument("--timeframes", default="1m,15m,1h,4h,1d")
    parser.add_argument("--start-date", default="2024-01-01")
    parser.add_argument("--swing-size", type=int, default=25)
    parser.add_argument("--fee-per-side-pct", type=float, default=0.04)
    parser.add_argument("--out-root", default="output/backtests")
    args = parser.parse_args()

    symbols = _normalize_symbols(args.symbols)
    timeframes = _normalize_timeframes(args.timeframes)

    start_date = dt.date.fromisoformat(args.start_date)
    today = dt.datetime.utcnow().date()
    end_date_exclusive = dt.date(today.year, today.month, 1)  # last full month boundary
    if end_date_exclusive <= start_date:
        raise SystemExit("No full-month data window for requested start date")

    stamp = dt.datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
    out_dir = Path(args.out_root) / f"timeframe_matrix_{stamp}"
    data_dir = out_dir / "data"
    chart_dir = out_dir / "charts"
    data_dir.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, object]] = []
    equities: Dict[Tuple[str, str], pd.Series] = {}

    for sym in symbols:
        for tf in timeframes:
            print(f"[fetch] {sym} {tf} ...", flush=True)
            df = download_binance_vision_klines(
                symbol=sym,
                timeframe=tf,
                start_date=start_date,
                end_date_exclusive=end_date_exclusive,
            )
            if df.empty:
                print(f"[skip] {sym} {tf}: no data", flush=True)
                continue

            # persist raw data for auditability
            df.to_csv(data_dir / f"{sym}_{tf}.csv")

            if len(df) < (args.swing_size * 3):
                print(f"[skip] {sym} {tf}: not enough bars ({len(df)})", flush=True)
                continue

            bt, eq = run_smart_money_backtest(
                df,
                swing_size=args.swing_size,
                fee_per_side_pct=args.fee_per_side_pct,
            )
            bt.symbol = sym
            bt.timeframe = tf
            equities[(sym, tf)] = eq
            rows.append(
                {
                    "symbol": bt.symbol,
                    "timeframe": bt.timeframe,
                    "bars": bt.bars,
                    "trades": bt.trades,
                    "win_rate_pct": bt.win_rate_pct,
                    "total_return_pct": bt.total_return_pct,
                    "max_drawdown_pct": bt.max_drawdown_pct,
                    "avg_trade_return_pct": bt.avg_trade_return_pct,
                    "profit_factor": bt.profit_factor,
                }
            )
            print(
                f"[done] {sym} {tf}: bars={bt.bars} trades={bt.trades} ret={bt.total_return_pct:.2f}% win={bt.win_rate_pct:.2f}%",
                flush=True,
            )

    results_df = pd.DataFrame(rows)
    if not results_df.empty:
        tf_order = {"1m": 0, "15m": 1, "1h": 2, "4h": 3, "1d": 4}
        results_df["_tf_order"] = results_df["timeframe"].map(tf_order).fillna(99)
        results_df = results_df.sort_values(["symbol", "_tf_order"]).drop(columns=["_tf_order"])

    results_path = out_dir / "timeframe_backtest_results.csv"
    results_df.to_csv(results_path, index=False)

    # Charts
    _plot_heatmap(
        results_df,
        value_col="total_return_pct",
        title="Smart Money Breakout Total Return (%)",
        out_path=chart_dir / "return_heatmap.png",
        cmap="RdYlGn",
    )
    _plot_heatmap(
        results_df,
        value_col="win_rate_pct",
        title="Smart Money Breakout Win Rate (%)",
        out_path=chart_dir / "winrate_heatmap.png",
        cmap="YlGn",
    )
    _plot_heatmap(
        results_df,
        value_col="max_drawdown_pct",
        title="Smart Money Breakout Max Drawdown (%)",
        out_path=chart_dir / "drawdown_heatmap.png",
        cmap="YlOrRd_r",
    )
    _plot_equity_by_timeframe(equities, out_dir)

    write_report(
        out_dir=out_dir,
        start_date=start_date.isoformat(),
        end_date_exclusive=end_date_exclusive.isoformat(),
        symbols=symbols,
        timeframes=timeframes,
        results_df=results_df,
    )

    summary = {
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "symbols": symbols,
        "timeframes": timeframes,
        "start_date": start_date.isoformat(),
        "end_date_exclusive": end_date_exclusive.isoformat(),
        "results_rows": int(len(results_df)),
        "output_dir": str(out_dir.resolve()),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
