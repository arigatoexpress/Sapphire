#!/usr/bin/env python3
"""Summarize rolling PnL windows from timeframe matrix backtest OHLC data."""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
from typing import Dict, List

import pandas as pd
from run_smart_money_timeframe_matrix import run_smart_money_backtest


def _asof_equity(eq: pd.Series, ts: pd.Timestamp) -> float:
    if eq.empty:
        return float('nan')
    ts = pd.Timestamp(ts)
    if eq.index.tz is not None and ts.tzinfo is None:
        ts = ts.tz_localize(eq.index.tz)
    if eq.index.tz is None and ts.tzinfo is not None:
        ts = ts.tz_convert(None)
    try:
        v = eq.asof(ts)
        if pd.isna(v):
            return float(eq.iloc[0])
        return float(v)
    except Exception:
        # fallback to first value if lookup fails
        return float(eq.iloc[0])


def _window_return(eq: pd.Series, start_ts: pd.Timestamp) -> float:
    if eq.empty:
        return float('nan')
    end_v = float(eq.iloc[-1])
    start_v = _asof_equity(eq, start_ts)
    if start_v == 0 or pd.isna(start_v):
        return float('nan')
    return (end_v / start_v - 1.0) * 100.0


def analyze_folder(folder: Path, swing_size: int, fee_per_side_pct: float) -> pd.DataFrame:
    data_dir = folder / 'data'
    files = sorted(data_dir.glob('*_*.csv'))
    rows: List[Dict[str, object]] = []

    for f in files:
        stem = f.stem
        parts = stem.split('_')
        if len(parts) != 2:
            continue
        symbol, timeframe = parts
        if timeframe not in {'1m', '15m', '1h', '4h', '1d'}:
            continue

        df = pd.read_csv(f, index_col=0, parse_dates=True)
        if df.empty:
            continue
        cols = {c.lower(): c for c in df.columns}
        needed = ['open', 'high', 'low', 'close', 'volume']
        if not all(k in cols for k in needed):
            continue
        df = df[[cols['open'], cols['high'], cols['low'], cols['close'], cols['volume']]].copy()
        df.columns = needed
        df = df.sort_index()

        bt, eq = run_smart_money_backtest(
            df,
            swing_size=swing_size,
            fee_per_side_pct=fee_per_side_pct,
        )

        end_ts = pd.Timestamp(eq.index[-1])
        ytd_start = pd.Timestamp(year=end_ts.year, month=1, day=1, tz=end_ts.tz if hasattr(end_ts, 'tz') else None)

        row = {
            'symbol': symbol,
            'timeframe': timeframe,
            'bars': bt.bars,
            'trades': bt.trades,
            'total_return_pct': bt.total_return_pct,
            'max_drawdown_pct': bt.max_drawdown_pct,
            'win_rate_pct': bt.win_rate_pct,
            'pnl_7d_pct': round(_window_return(eq, end_ts - pd.Timedelta(days=7)), 2),
            'pnl_30d_pct': round(_window_return(eq, end_ts - pd.Timedelta(days=30)), 2),
            'pnl_90d_pct': round(_window_return(eq, end_ts - pd.Timedelta(days=90)), 2),
            'pnl_180d_pct': round(_window_return(eq, end_ts - pd.Timedelta(days=180)), 2),
            'pnl_365d_pct': round(_window_return(eq, end_ts - pd.Timedelta(days=365)), 2),
            'pnl_ytd_pct': round(_window_return(eq, ytd_start), 2),
            'pnl_since_start_pct': round(float(bt.total_return_pct), 2),
        }
        rows.append(row)

        eq_out = data_dir / f'equity_{symbol}_{timeframe}.csv'
        eq.to_frame('equity').to_csv(eq_out)

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    tf_order = {'1m': 0, '15m': 1, '1h': 2, '4h': 3, '1d': 4}
    out['_tf_order'] = out['timeframe'].map(tf_order).fillna(99)
    out = out.sort_values(['symbol', '_tf_order']).drop(columns=['_tf_order'])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('folder', help='timeframe_matrix output folder path')
    ap.add_argument('--swing-size', type=int, default=25)
    ap.add_argument('--fee-per-side-pct', type=float, default=0.04)
    args = ap.parse_args()

    folder = Path(args.folder)
    if not folder.exists():
        raise SystemExit(f'Folder not found: {folder}')

    df = analyze_folder(folder, args.swing_size, args.fee_per_side_pct)
    if df.empty:
        raise SystemExit('No valid timeframe data found.')

    csv_path = folder / 'pnl_windows.csv'
    md_path = folder / 'pnl_windows.md'
    df.to_csv(csv_path, index=False)

    # best timeframe per symbol by total return
    best_rows = []
    for sym, sdf in df.groupby('symbol'):
        best = sdf.sort_values('total_return_pct', ascending=False).iloc[0]
        best_rows.append(best)
    best_df = pd.DataFrame(best_rows)

    lines = [
        '# PnL Window Summary',
        '',
        f"Generated: {dt.datetime.utcnow().isoformat()}Z",
        '',
        '## Full Matrix',
        '',
        df.to_markdown(index=False),
        '',
        '## Best Timeframe Per Symbol',
        '',
        best_df.to_markdown(index=False),
        '',
    ]
    md_path.write_text('\n'.join(lines), encoding='utf-8')

    print(df.to_string(index=False))
    print(f"\nWrote: {csv_path}")
    print(f"Wrote: {md_path}")


if __name__ == '__main__':
    main()
