#!/usr/bin/env python3
"""Pine Script Backtesting Feedback Loop.

Uses TradingView MCP to:
1. Load a Pine Script strategy onto the chart
2. Switch through multiple symbols
3. Read strategy tester results after each run
4. Log win rate, Sortino, max drawdown per symbol
5. Compare across parameter sets
6. Suggest optimizations based on actual results

Requires TradingView Desktop with --remote-debugging-port=9222.

Usage:
    python3 backtest.py                          # Run on default symbols
    python3 backtest.py --symbols BTCUSDT,ETHUSDT
    python3 backtest.py --history                # Show backtest history
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
BACKTEST_PATH = SAPPHIRE_DIR / "data" / "backtest_results.jsonl"
PINE_DIR = SAPPHIRE_DIR / "pine" / "standalone"

DEFAULT_SYMBOLS = ["PYTH:BTCUSD", "PYTH:ETHUSD", "PYTH:SOLUSD", "PYTH:HYPEUSD"]
DEFAULT_TIMEFRAMES = ["60"]  # 1H


def _tv(args: list[str], timeout: int = 15) -> dict:
    """Run tv CLI command."""
    try:
        r = subprocess.run(["tv"] + args, capture_output=True, text=True, timeout=timeout)
        if r.stdout.strip():
            return json.loads(r.stdout)
        return {"error": r.stderr.strip() or "no output"}
    except json.JSONDecodeError:
        return {"raw": r.stdout.strip()[:500]}
    except Exception as e:
        return {"error": str(e)}


def check_tv_connection() -> bool:
    """Verify TradingView is connected via CDP."""
    status = _tv(["status"])
    return status.get("cdp_connected", False)


def switch_symbol(symbol: str) -> bool:
    """Switch chart to a new symbol."""
    result = _tv(["symbol", symbol])
    time.sleep(3)  # Wait for chart to load
    return result.get("success", False)


def read_strategy_results() -> dict:
    """Read strategy tester results from TradingView."""
    # Wait for strategy to calculate
    time.sleep(5)
    result = _tv(["data", "strategy"], timeout=20)
    return result


def run_backtest(
    symbols: list[str] | None = None,
    timeframes: list[str] | None = None,
    pine_script: str | None = None,
) -> list[dict]:
    """Run backtests across multiple symbols."""
    if not check_tv_connection():
        print("❌ TradingView not connected. Launch with --remote-debugging-port=9222")
        return []

    symbols = symbols or DEFAULT_SYMBOLS
    timeframes = timeframes or DEFAULT_TIMEFRAMES
    results = []

    # Load Pine Script if provided
    if pine_script:
        script_path = PINE_DIR / pine_script
        if script_path.exists():
            print(f"📝 Loading {pine_script}...")
            _tv(["ui", "panel", "pine-editor", "open"])
            time.sleep(2)
            subprocess.run(["tv", "pine", "set"], input=script_path.read_text(),
                           capture_output=True, text=True, timeout=10)
            compile_result = _tv(["pine", "compile"], timeout=30)
            if compile_result.get("errors"):
                errors = [e for e in compile_result["errors"] if e.get("severity", 0) >= 8]
                if errors:
                    print(f"❌ Compile errors: {len(errors)}")
                    return []
            print("✅ Strategy compiled")

    for tf in timeframes:
        for symbol in symbols:
            print(f"  📊 Testing {symbol} @ {tf}m...")
            switch_symbol(symbol)

            if tf != "60":
                _tv(["timeframe", tf])
                time.sleep(2)

            strategy = read_strategy_results()
            metrics = strategy.get("metrics", {})

            result = {
                "timestamp": datetime.now(UTC).isoformat(),
                "symbol": symbol,
                "timeframe": tf,
                "strategy": pine_script or "active",
                "metrics": metrics,
                "metric_count": strategy.get("metric_count", 0),
            }

            if metrics:
                print(f"    Win rate: {metrics.get('percentProfitable', 'n/a')}")
                print(f"    Net profit: {metrics.get('netProfit', 'n/a')}")
                print(f"    Max DD: {metrics.get('maxDrawdown', 'n/a')}")
            else:
                print(f"    No strategy results (may need strategy on chart)")

            results.append(result)

    # Save results
    BACKTEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    for r in results:
        with open(BACKTEST_PATH, "a") as f:
            f.write(json.dumps(r) + "\n")

    print(f"\n✅ {len(results)} backtests complete, saved to {BACKTEST_PATH}")
    return results


def show_history() -> None:
    """Display backtest history."""
    if not BACKTEST_PATH.exists():
        print("No backtest history. Run a backtest first.")
        return

    lines = BACKTEST_PATH.read_text().strip().splitlines()
    print(f"\n{'='*60}")
    print(f"  BACKTEST HISTORY ({len(lines)} runs)")
    print(f"{'='*60}\n")

    for line in lines[-20:]:
        r = json.loads(line)
        m = r.get("metrics", {})
        ts = r["timestamp"][:19]
        sym = r["symbol"]
        wp = m.get("percentProfitable", "?")
        np_ = m.get("netProfit", "?")
        dd = m.get("maxDrawdown", "?")
        print(f"  {ts} | {sym:15s} | WR: {wp} | PnL: {np_} | DD: {dd}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Pine Script Backtesting Loop")
    parser.add_argument("--symbols", help="Comma-separated symbols")
    parser.add_argument("--pine", help="Pine script filename in pine/standalone/")
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()

    if args.history:
        show_history()
    else:
        syms = args.symbols.split(",") if args.symbols else None
        run_backtest(symbols=syms, pine_script=args.pine)
