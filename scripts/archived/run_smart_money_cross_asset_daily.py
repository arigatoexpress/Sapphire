#!/usr/bin/env python3
"""Cross-asset daily Smart Money Breakout backtest (crypto + gold/silver + others)."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf
from run_official_crypto_backtest import run_smart_money_backtest


def _normalize_tickers(raw: str) -> list[str]:
    out = []
    seen = set()
    for tok in raw.split(','):
        t = tok.strip().upper()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def download_daily(ticker: str, start: str, end: str) -> pd.DataFrame:
    df = yf.download(
        tickers=ticker,
        start=start,
        end=end,
        interval='1d',
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    needed = ['Open', 'High', 'Low', 'Close', 'Volume']
    if any(c not in df.columns for c in needed):
        return pd.DataFrame()
    out = df[needed].copy()
    out.columns = ['open', 'high', 'low', 'close', 'volume']
    out.index = pd.to_datetime(out.index).tz_localize(None)
    out = out.dropna().sort_index()
    return out


def make_charts(out_dir: Path, price_frames: dict[str, pd.DataFrame], equities: dict[str, pd.Series], results_df: pd.DataFrame) -> None:
    chart_dir = out_dir / 'charts'
    chart_dir.mkdir(parents=True, exist_ok=True)

    perf = pd.DataFrame({
        sym: (df['close'] / df['close'].iloc[0]) * 100.0
        for sym, df in price_frames.items() if not df.empty
    }).dropna(how='all')
    if not perf.empty:
        plt.figure(figsize=(13, 7))
        for col in perf.columns:
            plt.plot(perf.index, perf[col], label=col, linewidth=1.5)
        plt.title('Cross-Asset Normalized Price Performance (Base=100)')
        plt.grid(alpha=0.2)
        plt.legend(ncol=4, fontsize=9)
        plt.tight_layout()
        plt.savefig(chart_dir / 'normalized_performance.png', dpi=160)
        plt.close()

    if equities:
        eq_df = pd.DataFrame({k: v for k, v in equities.items()}).dropna(how='all')
        plt.figure(figsize=(13, 7))
        for col in eq_df.columns:
            plt.plot(eq_df.index, eq_df[col], label=col, linewidth=1.5)
        plt.title('Cross-Asset Smart Money Breakout Equity Curves (Daily)')
        plt.grid(alpha=0.2)
        plt.legend(ncol=4, fontsize=9)
        plt.tight_layout()
        plt.savefig(chart_dir / 'equity_curves.png', dpi=160)
        plt.close()

    if not results_df.empty:
        plot_df = results_df.sort_values('total_return_pct', ascending=False)
        x = np.arange(len(plot_df))
        plt.figure(figsize=(13, 7))
        plt.bar(x - 0.2, plot_df['total_return_pct'], width=0.4, label='Total Return %')
        plt.bar(x + 0.2, plot_df['max_drawdown_pct'], width=0.4, label='Max Drawdown %')
        plt.xticks(x, plot_df['ticker'], rotation=45, ha='right')
        plt.axhline(0, color='black', linewidth=0.8)
        plt.title('Cross-Asset Return vs Drawdown')
        plt.grid(alpha=0.2, axis='y')
        plt.legend()
        plt.tight_layout()
        plt.savefig(chart_dir / 'return_drawdown_summary.png', dpi=160)
        plt.close()


def write_report(out_dir: Path, start_date: str, end_date: str, results_df: pd.DataFrame) -> None:
    report = out_dir / 'report.md'
    now = dt.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'

    lines = [
        '# Smart Money Breakout Cross-Asset Daily Test',
        '',
        f'- Generated: `{now}`',
        f'- Data range: `{start_date}` to `{end_date}`',
        '- Strategy: Smart Money Breakout port (BOS + TP/SL distance model).',
        '',
        '## Results',
        '',
        results_df.to_markdown(index=False) if not results_df.empty else '_No results._',
        '',
        '## Charts',
        '',
        '- `charts/normalized_performance.png`',
        '- `charts/equity_curves.png`',
        '- `charts/return_drawdown_summary.png`',
        '',
    ]
    report.write_text('\n'.join(lines), encoding='utf-8')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--tickers', default='BTC-USD,ETH-USD,SOL-USD,GC=F,SI=F,GLD,SLV,SPY,QQQ')
    ap.add_argument('--start-date', default='2024-01-01')
    ap.add_argument('--swing-size', type=int, default=25)
    ap.add_argument('--fee-per-side-pct', type=float, default=0.04)
    ap.add_argument('--out-root', default='output/backtests')
    args = ap.parse_args()

    tickers = _normalize_tickers(args.tickers)
    end_date = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    stamp = dt.datetime.utcnow().strftime('%Y-%m-%d_%H%M%S')
    out_dir = Path(args.out_root) / f'cross_asset_daily_{stamp}'
    data_dir = out_dir / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)

    price_frames: dict[str, pd.DataFrame] = {}
    equities: dict[str, pd.Series] = {}
    rows = []

    for t in tickers:
        print(f'[fetch] {t} ...', flush=True)
        df = download_daily(t, args.start_date, end_date)
        if df.empty or len(df) < (args.swing_size * 3):
            print(f'[skip] {t}', flush=True)
            continue
        df.to_csv(data_dir / f'{t.replace("=", "_")}_daily.csv')
        price_frames[t] = df

        bt, eq = run_smart_money_backtest(
            df,
            swing_size=args.swing_size,
            fee_per_side_pct=args.fee_per_side_pct,
        )
        bt.symbol = t
        equities[t] = eq
        rows.append({
            'ticker': t,
            'bars': bt.bars,
            'trades': bt.trades,
            'win_rate_pct': bt.win_rate_pct,
            'total_return_pct': bt.total_return_pct,
            'max_drawdown_pct': bt.max_drawdown_pct,
            'avg_trade_return_pct': bt.avg_trade_return_pct,
            'profit_factor': bt.profit_factor,
        })
        print(f"[done] {t}: ret={bt.total_return_pct:.2f}% win={bt.win_rate_pct:.2f}% trades={bt.trades}", flush=True)

    results_df = pd.DataFrame(rows).sort_values('total_return_pct', ascending=False)
    results_df.to_csv(out_dir / 'cross_asset_backtest_results.csv', index=False)
    make_charts(out_dir, price_frames, equities, results_df)
    write_report(out_dir, args.start_date, end_date, results_df)

    summary = {
        'generated_at': dt.datetime.utcnow().isoformat() + 'Z',
        'tickers': tickers,
        'start_date': args.start_date,
        'symbols_tested': int(len(results_df)),
        'output_dir': str(out_dir.resolve()),
    }
    (out_dir / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
