#!/usr/bin/env python3
"""Walk-forward + regime decomposition build script.

Enumerates the seven Sapphire strategy classes, runs walk-forward over
each with three horizons (90 / 180 / 365 day windows by default), joins
the OOS test returns to the cross-asset regime feed, computes a
Deflated Sharpe Ratio per strategy/horizon, and persists per-strategy
JSON to ``data/backtests/walkforward/<date>/<strategy>.json``.

Dry-run by default — never calls live data, never publishes events,
never sends Telegram. Operator-friendly invocation:

    python3 -m services.walkforward.build --days 365 --strategies all
    python3 -m services.walkforward.build --strategies RegimeAwareRSI \
            --bars-source synthetic --train 90 --test 30

Bars source:
    --bars-source synthetic   Deterministic stdlib OHLCV (default — no network).
    --bars-source yfinance    Use lib.analytics.backtest_engine.fetch_ohlcv.

Output: ``data/backtests/walkforward/<YYYY-MM-DD>/<strategy>.json`` plus a
top-level ``manifest.json`` listing all artifacts written.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.analytics.backtest_engine import Bar  # noqa: E402
from lib.analytics.strategies import (  # noqa: E402
    ALL_STRATEGIES,
    PARAM_GRID,
    Strategy,
)
from lib.analytics.walkforward import (  # noqa: E402
    WalkforwardConfig,
    decompose_by_regime,
    deflated_sharpe_for_walkforward,
    load_regime_labels,
    run_walkforward,
)

log = logging.getLogger("services.walkforward.build")

VERSION = "0.1.0"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "backtests" / "walkforward"
DEFAULT_HORIZONS = (90, 180, 365)


# ---------------------------------------------------------------------------
# Strategy registry — names → classes (lowercase keys allowed)
# ---------------------------------------------------------------------------


STRATEGY_REGISTRY: dict[str, type[Strategy]] = {cls.__name__: cls for cls in ALL_STRATEGIES}


def _resolve_strategy(name: str) -> type[Strategy]:
    if name in STRATEGY_REGISTRY:
        return STRATEGY_REGISTRY[name]
    lowered = name.lower()
    for cname, cls in STRATEGY_REGISTRY.items():
        if cname.lower() == lowered:
            return cls
    raise ValueError(
        f"unknown strategy '{name}' (known: {sorted(STRATEGY_REGISTRY)})"
    )


# ---------------------------------------------------------------------------
# Synthetic bars (deterministic, no network)
# ---------------------------------------------------------------------------


def synthetic_bars(symbol: str, n: int) -> list[Bar]:
    """Deterministic OHLCV bars. Mirrors backtest_engine._synthetic_bars shape
    but with a wider regime mix so walk-forward windows traverse multiple
    market states. Pure stdlib.
    """
    seed_factor = sum(ord(c) for c in symbol) or 1
    bars: list[Bar] = []
    base_ts = datetime(2025, 1, 1, tzinfo=UTC)
    price = 100.0 + (seed_factor % 50)
    for i in range(n):
        # Three superimposed cycles + drift change to span 4 regime regions.
        d1 = math.sin(i / 7.0 + seed_factor / 13.0) * 1.4
        d2 = math.cos(i / 21.0 + seed_factor / 5.0) * 0.7
        d3 = math.sin(i / 91.0) * 2.0
        regime_drift = -1.5 if (i // 90) % 4 == 1 else (1.0 if (i // 90) % 4 == 3 else 0.0)
        delta = (d1 + d2 + d3 + regime_drift) / 100.0
        price = max(5.0, price * (1.0 + delta))
        bars.append(
            Bar(
                ts=base_ts + timedelta(days=i),
                open=price * 0.997,
                high=price * 1.014,
                low=price * 0.986,
                close=price,
                volume=1_000_000.0 + (i % 7) * 50_000,
            )
        )
    return bars


def _aux_for(_symbol: str, n: int) -> dict[str, list[Bar]]:
    """Build aligned aux series so strategies that look at BTC/SPY work in synthetic mode."""
    return {
        "btc": synthetic_bars("BTC-USD", n),
        "spy": synthetic_bars("SPY", n),
    }


# ---------------------------------------------------------------------------
# Bars source dispatch
# ---------------------------------------------------------------------------


def _live_bars(symbol: str, days: int) -> list[Bar]:
    """Network-bound: only used when --bars-source yfinance and operator opts in."""
    from lib.analytics.backtest_engine import fetch_ohlcv

    return fetch_ohlcv(symbol, days=days)


def get_bars(*, symbol: str, days: int, source: str) -> list[Bar]:
    if source == "yfinance":
        return _live_bars(symbol, days)
    if source == "synthetic":
        return synthetic_bars(symbol, days)
    raise ValueError(f"unknown bars source {source!r}")


# ---------------------------------------------------------------------------
# Build a single (strategy, horizon) result block
# ---------------------------------------------------------------------------


def _build_block(
    *,
    strategy_cls: type[Strategy],
    bars: list[Bar],
    aux: dict[str, list[Bar]],
    horizon_days: int,
    train_bars: int,
    test_bars: int,
    advance_bars: int | None,
    purge_bars: int,
    embargo_bars: int,
    symbol: str,
    selection_metric: str,
    bankroll: float,
    regime_labels: dict[str, str],
) -> dict[str, Any]:
    cfg = WalkforwardConfig(
        train_bars=train_bars,
        test_bars=test_bars,
        advance_bars=advance_bars,
        purge_bars=purge_bars,
        embargo_bars=embargo_bars,
        symbol=symbol,
        selection_metric=selection_metric,
        bankroll=bankroll,
    )
    bars_window = bars[-horizon_days:] if horizon_days <= len(bars) else bars
    aux_window = {k: v[-horizon_days:] if horizon_days <= len(v) else v for k, v in aux.items()}
    result = run_walkforward(strategy_cls, bars_window, aux=aux_window, config=cfg)

    decomp = decompose_by_regime(
        result.concatenated_test_returns,
        result.concatenated_test_timestamps,
        labels=regime_labels,
        strategy_cls=result.strategy_cls,
        symbol=result.symbol,
    )

    dsr = deflated_sharpe_for_walkforward(result)

    return {
        "horizon_days": horizon_days,
        "config": result.config,
        "result": result.to_dict(),
        "regime_decomposition": decomp.to_dict(),
        "deflated_sharpe": dsr.to_dict(),
    }


# ---------------------------------------------------------------------------
# Top-level build
# ---------------------------------------------------------------------------


def build(
    *,
    strategies: list[str],
    horizons: list[int],
    bars_source: str,
    symbol: str,
    train_bars: int,
    test_bars: int,
    advance_bars: int | None,
    purge_bars: int,
    embargo_bars: int,
    selection_metric: str,
    bankroll: float,
    output_root: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    issued_at = now or datetime.now(UTC)
    target_dir = output_root / issued_at.strftime("%Y-%m-%d")
    target_dir.mkdir(parents=True, exist_ok=True)

    max_days = max(horizons)
    bars = get_bars(symbol=symbol, days=max_days, source=bars_source)
    aux = _aux_for(symbol, len(bars))

    regime_labels = load_regime_labels()

    manifest: dict[str, Any] = {
        "version": VERSION,
        "generated_at": issued_at.isoformat(),
        "symbol": symbol,
        "bars_source": bars_source,
        "n_bars": len(bars),
        "horizons_days": horizons,
        "selection_metric": selection_metric,
        "bankroll": bankroll,
        "regime_label_count": len(regime_labels),
        "artifacts": [],
    }

    for sname in strategies:
        cls = _resolve_strategy(sname)
        blocks = []
        for h in horizons:
            try:
                blocks.append(
                    _build_block(
                        strategy_cls=cls,
                        bars=bars,
                        aux=aux,
                        horizon_days=h,
                        train_bars=train_bars,
                        test_bars=test_bars,
                        advance_bars=advance_bars,
                        purge_bars=purge_bars,
                        embargo_bars=embargo_bars,
                        symbol=symbol,
                        selection_metric=selection_metric,
                        bankroll=bankroll,
                        regime_labels=regime_labels,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("walkforward block failed for %s/%dd: %s", cls.__name__, h, exc)
                blocks.append({"horizon_days": h, "error": f"{type(exc).__name__}: {exc}"})

        payload = {
            "version": VERSION,
            "generated_at": issued_at.isoformat(),
            "strategy_cls": cls.__name__,
            "symbol": symbol,
            "param_grid": dict(PARAM_GRID),
            "horizons": blocks,
        }
        out = target_dir / f"{cls.__name__}.json"
        out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        manifest["artifacts"].append({"strategy": cls.__name__, "path": str(out)})

    (target_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="services.walkforward.build")
    parser.add_argument(
        "--strategies",
        default="all",
        help="Comma-separated strategy class names, or 'all'.",
    )
    parser.add_argument("--symbol", default="BTC-USD")
    parser.add_argument(
        "--horizons",
        default="90,180,365",
        help="Comma-separated horizon-day lengths.",
    )
    parser.add_argument("--train", type=int, default=90)
    parser.add_argument("--test", type=int, default=30)
    parser.add_argument("--advance", type=int, default=None)
    parser.add_argument("--purge", type=int, default=0)
    parser.add_argument("--embargo", type=int, default=0)
    parser.add_argument(
        "--selection-metric",
        default="sortino",
        choices=["sortino", "sharpe", "calmar", "profit_factor", "total_return"],
    )
    parser.add_argument("--bankroll", type=float, default=10_000.0)
    parser.add_argument(
        "--bars-source", choices=["synthetic", "yfinance"], default="synthetic"
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.WARNING if ns.quiet else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    if ns.strategies.strip().lower() == "all":
        strategies = list(STRATEGY_REGISTRY.keys())
    else:
        strategies = [s.strip() for s in ns.strategies.split(",") if s.strip()]

    horizons = [int(h.strip()) for h in ns.horizons.split(",") if h.strip()]

    manifest = build(
        strategies=strategies,
        horizons=horizons,
        bars_source=ns.bars_source,
        symbol=ns.symbol,
        train_bars=ns.train,
        test_bars=ns.test,
        advance_bars=ns.advance,
        purge_bars=ns.purge,
        embargo_bars=ns.embargo,
        selection_metric=ns.selection_metric,
        bankroll=ns.bankroll,
        output_root=Path(ns.output),
    )
    print(json.dumps({"ok": True, "manifest": manifest}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
