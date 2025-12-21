import asyncio
import json
import logging

import pandas as pd
from tabulate import tabulate

from cloud_trader.backtesting.data_manager import BacktestDataManager
from cloud_trader.backtesting.engine import BacktestEngine
from cloud_trader.backtesting.strategies import (
    mean_reversion_strategy,
    momentum_strategy,
    trend_following_strategy,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    logger.info("🧪 STARTING SCIENTIFIC BACKTEST")

    # 1. Fetch Data
    dm = BacktestDataManager()
    # Using SOLUSDT as proxy for high beta / volatility
    raw_df = await dm.fetch_ohlcv("SOL/USD", interval="1h", limit=2000)
    df = dm.prepare_features(raw_df)

    logger.info(f"📊 Loaded {len(df)} candles for analysis.")

    # 2. Setup Engine
    engine = BacktestEngine(initial_capital=10000, slippage_bps=5)

    strategies = [
        ("Momentum", momentum_strategy, {}),
        ("Mean Reversion", mean_reversion_strategy, {"bb_dev": 2.0}),
        ("Trend Following", trend_following_strategy, {"fast": 12, "slow": 26}),
    ]

    results = []

    # 3. Run Experiments
    for name, func, params in strategies:
        try:
            logger.info(f"RUNNING: {name}...")
            res = engine.run(df, func, params)

            results.append(
                {
                    "Strategy": name,
                    "Return %": f"{res.total_return * 100:.2f}%",
                    "Sharpe": f"{res.sharpe_ratio:.2f}",
                    "Max DD %": f"{res.max_drawdown * 100:.2f}%",
                    "Win Rate": f"{res.win_rate * 100:.1f}%",
                    "Profit Factor": f"{res.profit_factor:.2f}",
                    "Trades": res.total_trades,
                }
            )
        except Exception as e:
            logger.error(f"Failed {name}: {e}")

    # 4. Report
    print("\n" + "=" * 50)
    print("🔬 SCIENTIFIC BACKTEST RESULTS (SOL/USD 1h)")
    print("=" * 50)
    print(tabulate(results, headers="keys", tablefmt="github"))
    print("=" * 50 + "\n")

    # Save to JSON for frontend
    with open("backtest_results.json", "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
