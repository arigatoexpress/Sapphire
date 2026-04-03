#!/usr/bin/env python3
"""
High-leverage HFT perpetual grid backtest + optimizer.

- Data: Binance Vision monthly futures UM klines (no live API dependency)
- Strategy: Neutral/bi-directional grid around EMA anchor
- Scope: HFT timeframes (default 1m,5m,15m)

Outputs:
  output/backtests/hft_grid_<timestamp>/
    - hft_grid_results.csv
    - selected_params.csv
    - report.md
    - charts/returns_heatmap.png
    - charts/equity_<SYMBOL>_<TF>.png
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import itertools
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

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
BARS_PER_YEAR = {
    "1m": 525600,
    "3m": 175200,
    "5m": 105120,
    "15m": 35040,
    "1h": 8760,
}


@dataclass(frozen=True)
class GridConfig:
    leverage: int
    grid_step_bps: int
    levels: int
    tp_mult: float
    anchor_span: int
    slot_margin_frac: float
    max_positions: int


@dataclass
class BacktestMetrics:
    symbol: str
    timeframe: str
    bars: int
    trades: int
    win_rate_pct: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe: float
    profit_factor: float
    liquidation_count: int
    pnl_7d_pct: float
    pnl_30d_pct: float
    pnl_90d_pct: float
    pnl_180d_pct: float
    pnl_ytd_pct: float
    score: float


def _normalize_symbols(raw: str) -> list[str]:
    out, seen = [], set()
    for tok in raw.split(','):
        s = tok.strip().upper()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out or ["BTC", "ETH", "SOL"]


def _normalize_timeframes(raw: str) -> list[str]:
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
    frames: list[pd.DataFrame] = []

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


def _asof_equity(eq: pd.Series, ts: pd.Timestamp) -> float:
    if eq.empty:
        return float('nan')
    ts = pd.Timestamp(ts)
    if eq.index.tz is not None and ts.tzinfo is None:
        ts = ts.tz_localize(eq.index.tz)
    if eq.index.tz is None and ts.tzinfo is not None:
        ts = ts.tz_convert(None)
    v = eq.asof(ts)
    if pd.isna(v):
        return float(eq.iloc[0])
    return float(v)


def _window_return(eq: pd.Series, days: int) -> float:
    if eq.empty:
        return float('nan')
    end_ts = pd.Timestamp(eq.index[-1])
    start_ts = end_ts - pd.Timedelta(days=days)
    start_v = _asof_equity(eq, start_ts)
    end_v = float(eq.iloc[-1])
    if start_v <= 0:
        return float('nan')
    return (end_v / start_v - 1.0) * 100.0


def backtest_hft_grid(
    df: pd.DataFrame,
    timeframe: str,
    cfg: GridConfig,
    maker_fee_pct: float = 0.02,
    funding_rate_per_8h: float = 0.0001,
    liquidation_buffer: float = 0.92,
) -> tuple[BacktestMetrics, pd.Series]:
    # maker_fee_pct in percent, e.g. 0.02 = 0.02%
    fee = maker_fee_pct / 100.0
    grid_step = cfg.grid_step_bps / 10_000.0

    close = df["close"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    idx = pd.to_datetime(df.index)

    anchor = pd.Series(close, index=idx).ewm(span=cfg.anchor_span, adjust=False).mean().to_numpy(dtype=float)

    # funding cadence by timeframe
    mins = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "1h": 60}[timeframe]
    funding_every_bars = max(1, int((8 * 60) / mins))

    # per-slot state
    open_longs: dict[int, tuple[float, float, float]] = {}
    open_shorts: dict[int, tuple[float, float, float]] = {}
    # tuple: (entry, tp, liq)

    equity = 1.0
    eq_points = [equity]
    eq_index = [idx[0]]

    trade_pnls: list[float] = []
    wins = 0
    liquidations = 0

    for i in range(len(df)):
        a = anchor[i]
        if not np.isfinite(a) or a <= 0:
            eq_points.append(equity)
            eq_index.append(idx[i])
            continue

        # periodic funding cost/gain on open perpetual slots
        if i > 0 and (i % funding_every_bars == 0):
            exposure_factor = cfg.slot_margin_frac * cfg.leverage
            funding_frac = (
                (-funding_rate_per_8h * exposure_factor * len(open_longs))
                + (funding_rate_per_8h * exposure_factor * len(open_shorts))
            )
            equity = max(1e-9, equity * (1.0 + funding_frac))

        # exits first (conservative on same-bar TP+LIQ)
        for k, (entry, tp, liq) in list(open_longs.items()):
            hit_tp = high[i] >= tp
            hit_liq = low[i] <= liq
            if not (hit_tp or hit_liq):
                continue

            if hit_liq:
                # liquidation-like hard loss close
                pnl_frac = -cfg.slot_margin_frac * liquidation_buffer - (cfg.slot_margin_frac * cfg.leverage * fee)
                liquidations += 1
            else:
                move = (tp - entry) / entry
                pnl_frac = (cfg.slot_margin_frac * cfg.leverage * move) - (cfg.slot_margin_frac * cfg.leverage * fee)

            equity = max(1e-9, equity * (1.0 + pnl_frac))
            trade_pnls.append(pnl_frac)
            if pnl_frac > 0:
                wins += 1
            del open_longs[k]

        for k, (entry, tp, liq) in list(open_shorts.items()):
            hit_tp = low[i] <= tp
            hit_liq = high[i] >= liq
            if not (hit_tp or hit_liq):
                continue

            if hit_liq:
                pnl_frac = -cfg.slot_margin_frac * liquidation_buffer - (cfg.slot_margin_frac * cfg.leverage * fee)
                liquidations += 1
            else:
                move = (entry - tp) / entry
                pnl_frac = (cfg.slot_margin_frac * cfg.leverage * move) - (cfg.slot_margin_frac * cfg.leverage * fee)

            equity = max(1e-9, equity * (1.0 + pnl_frac))
            trade_pnls.append(pnl_frac)
            if pnl_frac > 0:
                wins += 1
            del open_shorts[k]

        # entries
        total_open = len(open_longs) + len(open_shorts)
        if total_open < cfg.max_positions:
            for level in range(1, cfg.levels + 1):
                lower = a * (1.0 - (grid_step * level))
                upper = a * (1.0 + (grid_step * level))

                # long ladder entry
                if level not in open_longs and low[i] <= lower and (len(open_longs) + len(open_shorts)) < cfg.max_positions:
                    entry = lower
                    tp = entry * (1.0 + (grid_step * cfg.tp_mult))
                    liq = entry * (1.0 - ((1.0 / cfg.leverage) * liquidation_buffer))
                    open_longs[level] = (entry, tp, liq)
                    open_fee = cfg.slot_margin_frac * cfg.leverage * fee
                    equity = max(1e-9, equity * (1.0 - open_fee))

                # short ladder entry
                if level not in open_shorts and high[i] >= upper and (len(open_longs) + len(open_shorts)) < cfg.max_positions:
                    entry = upper
                    tp = entry * (1.0 - (grid_step * cfg.tp_mult))
                    liq = entry * (1.0 + ((1.0 / cfg.leverage) * liquidation_buffer))
                    open_shorts[level] = (entry, tp, liq)
                    open_fee = cfg.slot_margin_frac * cfg.leverage * fee
                    equity = max(1e-9, equity * (1.0 - open_fee))

        eq_points.append(equity)
        eq_index.append(idx[i])

    # mark-to-market remaining at final close
    last_close = float(close[-1])
    for _k, (entry, _tp, _liq) in list(open_longs.items()):
        move = (last_close - entry) / entry
        pnl_frac = (cfg.slot_margin_frac * cfg.leverage * move) - (cfg.slot_margin_frac * cfg.leverage * fee)
        equity = max(1e-9, equity * (1.0 + pnl_frac))
        trade_pnls.append(pnl_frac)
        if pnl_frac > 0:
            wins += 1
    for _k, (entry, _tp, _liq) in list(open_shorts.items()):
        move = (entry - last_close) / entry
        pnl_frac = (cfg.slot_margin_frac * cfg.leverage * move) - (cfg.slot_margin_frac * cfg.leverage * fee)
        equity = max(1e-9, equity * (1.0 + pnl_frac))
        trade_pnls.append(pnl_frac)
        if pnl_frac > 0:
            wins += 1

    eq = pd.Series(eq_points, index=pd.to_datetime(eq_index), name="equity").sort_index()
    eq = eq[~eq.index.duplicated(keep="last")]

    trades = len(trade_pnls)
    if trades == 0:
        trade_pnls = [0.0]
        trades = 1

    tr = np.array(trade_pnls, dtype=float)
    win_rate = float((wins / trades) * 100.0)
    total_return_pct = float((equity - 1.0) * 100.0)

    # drawdown
    rolling_peak = eq.cummax()
    dd = (eq / rolling_peak) - 1.0
    max_dd_pct = float(dd.min() * 100.0) if not dd.empty else 0.0

    # sharpe from per-bar returns
    rets = eq.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    if len(rets) > 2 and float(rets.std()) > 0:
        sharpe = float((rets.mean() / rets.std()) * np.sqrt(BARS_PER_YEAR[timeframe]))
    else:
        sharpe = 0.0

    wins_sum = float(tr[tr > 0].sum())
    losses_sum = float(abs(tr[tr < 0].sum()))
    profit_factor = (wins_sum / losses_sum) if losses_sum > 0 else float("inf")

    # optimization objective: reward return+stability, penalize liquidation events
    score = (
        total_return_pct
        - (0.9 * abs(max_dd_pct))
        + (0.25 * win_rate)
        + (1.5 * sharpe)
        - (3.0 * liquidations)
    )

    end_ts = pd.Timestamp(eq.index[-1])
    ytd_start = pd.Timestamp(year=end_ts.year, month=1, day=1)

    metrics = BacktestMetrics(
        symbol="",
        timeframe=timeframe,
        bars=int(len(df)),
        trades=int(trades),
        win_rate_pct=round(win_rate, 2),
        total_return_pct=round(total_return_pct, 2),
        max_drawdown_pct=round(max_dd_pct, 2),
        sharpe=round(sharpe, 3),
        profit_factor=round(profit_factor, 3) if np.isfinite(profit_factor) else float("inf"),
        liquidation_count=int(liquidations),
        pnl_7d_pct=round(_window_return(eq, 7), 2),
        pnl_30d_pct=round(_window_return(eq, 30), 2),
        pnl_90d_pct=round(_window_return(eq, 90), 2),
        pnl_180d_pct=round(_window_return(eq, 180), 2),
        pnl_ytd_pct=round((float(eq.iloc[-1]) / _asof_equity(eq, ytd_start) - 1.0) * 100.0, 2),
        score=round(score, 2),
    )
    return metrics, eq


def _build_candidate_configs(seed: int = 42, max_configs: int = 24) -> list[GridConfig]:
    leverage = [10, 15, 20]
    step_bps = [8, 12, 16, 24]
    levels = [3, 5]
    tp_mult = [0.75, 1.0]
    anchor_span = [60, 120, 200]
    slot_margin = [0.0125, 0.02]

    all_cfg = [
        GridConfig(
            leverage=l,
            grid_step_bps=s,
            levels=lv,
            tp_mult=t,
            anchor_span=a,
            slot_margin_frac=m,
            max_positions=max(4, lv * 2),
        )
        for l, s, lv, t, a, m in itertools.product(leverage, step_bps, levels, tp_mult, anchor_span, slot_margin)
    ]

    if len(all_cfg) <= max_configs:
        return all_cfg

    rng = np.random.default_rng(seed)
    idx = rng.choice(len(all_cfg), size=max_configs, replace=False)
    return [all_cfg[i] for i in sorted(idx)]


def _plot_equity(out_dir: Path, symbol: str, timeframe: str, eq: pd.Series) -> None:
    cdir = out_dir / "charts"
    cdir.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(11, 5.5))
    plt.plot(eq.index, eq.values, linewidth=1.3)
    plt.title(f"HFT Grid Equity Curve — {symbol} {timeframe}")
    plt.xlabel("Date")
    plt.ylabel("Equity")
    plt.grid(alpha=0.2)
    plt.tight_layout()
    plt.savefig(cdir / f"equity_{symbol}_{timeframe}.png", dpi=160)
    plt.close()


def _plot_returns_heatmap(out_dir: Path, results_df: pd.DataFrame) -> None:
    if results_df.empty:
        return
    pivot = results_df.pivot(index="timeframe", columns="symbol", values="total_return_pct")
    tf_order = ["1m", "3m", "5m", "15m", "1h"]
    pivot = pivot.reindex([t for t in tf_order if t in pivot.index])

    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    arr = pivot.to_numpy(dtype=float)
    im = ax.imshow(arr, aspect="auto", cmap="RdYlGn")
    ax.set_xticks(np.arange(len(pivot.columns)))
    ax.set_yticks(np.arange(len(pivot.index)))
    ax.set_xticklabels(pivot.columns)
    ax.set_yticklabels(pivot.index)
    ax.set_title("HFT Grid Total Return (%)")

    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            v = arr[i, j]
            txt = "--" if np.isnan(v) else f"{v:.1f}"
            ax.text(j, i, txt, ha="center", va="center", color="black", fontsize=8)

    cbar = fig.colorbar(im, ax=ax)
    cbar.ax.set_ylabel("Return %")
    plt.tight_layout()
    plt.savefig(out_dir / "charts" / "returns_heatmap.png", dpi=160)
    plt.close(fig)


def _write_report(out_dir: Path, start_date: str, end_date_exclusive: str, results_df: pd.DataFrame, params_df: pd.DataFrame) -> None:
    p = out_dir / "report.md"
    now = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    lines = [
        "# HFT Perpetual Grid Backtest",
        "",
        f"- Generated: `{now}`",
        f"- Data range: `{start_date}` -> `{end_date_exclusive}` (end exclusive)",
        "- Engine: high-leverage bi-directional EMA-anchored perpetual grid",
        "- Includes: entry/exit maker fees, periodic funding, liquidation-like loss model",
        "",
        "## Selected Parameters",
        "",
        params_df.to_markdown(index=False) if not params_df.empty else "_No params_",
        "",
        "## Results",
        "",
        results_df.to_markdown(index=False) if not results_df.empty else "_No results_",
        "",
        "## Charts",
        "",
        "- `charts/returns_heatmap.png`",
        "- `charts/equity_<SYMBOL>_<TF>.png`",
        "",
    ]
    p.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="BTC,ETH,SOL")
    ap.add_argument("--timeframes", default="1m,5m,15m")
    ap.add_argument("--start-date", default="2024-01-01")
    ap.add_argument("--max-configs", type=int, default=24)
    ap.add_argument("--opt-bars", type=int, default=50000)
    ap.add_argument("--maker-fee-pct", type=float, default=0.02)
    ap.add_argument("--funding-rate-8h", type=float, default=0.0001)
    ap.add_argument("--out-root", default="output/backtests")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    symbols = _normalize_symbols(args.symbols)
    timeframes = _normalize_timeframes(args.timeframes)
    start_date = dt.date.fromisoformat(args.start_date)

    today = dt.datetime.utcnow().date()
    end_date_exclusive = dt.date(today.year, today.month, 1)
    if end_date_exclusive <= start_date:
        raise SystemExit("No full-month window in requested range")

    stamp = dt.datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
    out_dir = Path(args.out_root) / f"hft_grid_{stamp}"
    (out_dir / "data").mkdir(parents=True, exist_ok=True)
    (out_dir / "charts").mkdir(parents=True, exist_ok=True)

    candidate_cfgs = _build_candidate_configs(seed=args.seed, max_configs=args.max_configs)

    result_rows: list[dict[str, object]] = []
    param_rows: list[dict[str, object]] = []

    for symbol in symbols:
        for tf in timeframes:
            print(f"[fetch] {symbol} {tf} ...", flush=True)
            df = download_klines(symbol, tf, start_date, end_date_exclusive)
            if df.empty:
                print(f"[skip] {symbol} {tf}: no data", flush=True)
                continue
            df.to_csv(out_dir / "data" / f"{symbol}_{tf}.csv")
            if len(df) < 3000:
                print(f"[skip] {symbol} {tf}: too few bars ({len(df)})", flush=True)
                continue

            # optimization sample from tail window
            sample = df.tail(min(args.opt_bars, len(df))).copy()

            best_cfg = None
            best_score = -1e18
            for cfg in candidate_cfgs:
                metrics, _eq = backtest_hft_grid(
                    sample,
                    timeframe=tf,
                    cfg=cfg,
                    maker_fee_pct=args.maker_fee_pct,
                    funding_rate_per_8h=args.funding_rate_8h,
                )
                if metrics.score > best_score:
                    best_score = metrics.score
                    best_cfg = cfg

            if best_cfg is None:
                print(f"[skip] {symbol} {tf}: no viable config", flush=True)
                continue

            # full backtest using best config
            full_metrics, eq = backtest_hft_grid(
                df,
                timeframe=tf,
                cfg=best_cfg,
                maker_fee_pct=args.maker_fee_pct,
                funding_rate_per_8h=args.funding_rate_8h,
            )
            full_metrics.symbol = symbol
            _plot_equity(out_dir, symbol, tf, eq)

            result_rows.append({
                "symbol": symbol,
                "timeframe": tf,
                "bars": full_metrics.bars,
                "trades": full_metrics.trades,
                "win_rate_pct": full_metrics.win_rate_pct,
                "total_return_pct": full_metrics.total_return_pct,
                "max_drawdown_pct": full_metrics.max_drawdown_pct,
                "sharpe": full_metrics.sharpe,
                "profit_factor": full_metrics.profit_factor,
                "liquidation_count": full_metrics.liquidation_count,
                "pnl_7d_pct": full_metrics.pnl_7d_pct,
                "pnl_30d_pct": full_metrics.pnl_30d_pct,
                "pnl_90d_pct": full_metrics.pnl_90d_pct,
                "pnl_180d_pct": full_metrics.pnl_180d_pct,
                "pnl_ytd_pct": full_metrics.pnl_ytd_pct,
                "score": full_metrics.score,
            })

            param_rows.append({
                "symbol": symbol,
                "timeframe": tf,
                "leverage": best_cfg.leverage,
                "grid_step_bps": best_cfg.grid_step_bps,
                "levels": best_cfg.levels,
                "tp_mult": best_cfg.tp_mult,
                "anchor_span": best_cfg.anchor_span,
                "slot_margin_frac": best_cfg.slot_margin_frac,
                "max_positions": best_cfg.max_positions,
            })

            print(
                f"[done] {symbol} {tf}: ret={full_metrics.total_return_pct:.2f}% "
                f"dd={full_metrics.max_drawdown_pct:.2f}% trades={full_metrics.trades} "
                f"liq={full_metrics.liquidation_count} sharpe={full_metrics.sharpe:.2f}",
                flush=True,
            )

    results_df = pd.DataFrame(result_rows)
    params_df = pd.DataFrame(param_rows)

    if not results_df.empty:
        tf_order = {"1m": 0, "3m": 1, "5m": 2, "15m": 3}
        results_df["_tf_order"] = results_df["timeframe"].map(tf_order).fillna(99)
        results_df = results_df.sort_values(["symbol", "_tf_order"]).drop(columns=["_tf_order"])

    results_path = out_dir / "hft_grid_results.csv"
    params_path = out_dir / "selected_params.csv"
    results_df.to_csv(results_path, index=False)
    params_df.to_csv(params_path, index=False)

    _plot_returns_heatmap(out_dir, results_df)
    _write_report(out_dir, start_date.isoformat(), end_date_exclusive.isoformat(), results_df, params_df)

    summary = {
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "symbols": symbols,
        "timeframes": timeframes,
        "start_date": start_date.isoformat(),
        "end_date_exclusive": end_date_exclusive.isoformat(),
        "max_configs": args.max_configs,
        "opt_bars": args.opt_bars,
        "results_rows": int(len(results_df)),
        "output_dir": str(out_dir.resolve()),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
