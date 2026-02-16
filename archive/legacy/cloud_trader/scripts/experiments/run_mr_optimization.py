import asyncio
import logging

import numpy as np
import pandas as pd
from tabulate import tabulate

from cloud_trader.backtesting.data_manager import BacktestDataManager

# Setup
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)


class OptimizationRunner:
    def __init__(self, df):
        self.df = df

    def run_baseline(self):
        """Variant 1: Standard Bollinger Bands (20, 2.0)"""
        capital = 10000.0
        position = 0.0
        tx_cost = 0.001
        trades = 0

        for i, row in self.df.iterrows():
            price = row["close"]

            # Entry: Price < Lower Band
            if position == 0 and price < row["bb_lower"]:
                buy_amt = capital
                size = buy_amt / price
                cost = buy_amt * tx_cost
                if (capital - cost) > 0:
                    capital -= buy_amt  # All in minus fee... wait logic
                    # Simplified:
                    capital = 0
                    position = (buy_amt - cost) / price
                    trades += 1

            # Exit: Price > SMA
            elif position > 0 and price > row["sma_20"]:
                revenue = position * price
                cost = revenue * tx_cost
                capital = revenue - cost
                position = 0
                trades += 1  # Exit is a trade

        if position > 0:
            equity = position * self.df.iloc[-1]["close"]
        else:
            equity = capital

        return equity, trades

    def run_rsi_confluence(self):
        """Variant 2: BB Lower + RSI < 30 (Oversold Limit)"""
        capital = 10000.0
        position = 0.0
        tx_cost = 0.001
        trades = 0

        for i, row in self.df.iterrows():
            price = row["close"]
            rsi = row["rsi"]

            # Entry: Price < Lower Band AND RSI < 30
            if position == 0 and price < row["bb_lower"] and rsi < 30:
                buy_amt = capital
                size = buy_amt / price
                cost = buy_amt * tx_cost
                if (capital - cost) > 0:
                    capital = 0
                    position = (buy_amt - cost) / price
                    trades += 1

            # Exit: Price > SMA OR RSI > 70 (Overbought)
            elif position > 0 and (price > row["sma_20"] or rsi > 70):
                revenue = position * price
                cost = revenue * tx_cost
                capital = revenue - cost
                position = 0
                trades += 1

        if position > 0:
            equity = position * self.df.iloc[-1]["close"]
        else:
            equity = capital
        return equity, trades

    def run_adx_filter(self):
        """Variant 3: BB Lower + ADX < 25 (Range Only)"""
        # ADX not in features yet, need to mock or calc
        # Let's calc ADX on the fly or Approx

        # Approx ADX filter using Volatility logic if ADX missing
        # If std_20 / price < 0.05 (Low Vol) -> Trade
        # Let's use Volatility Ratio as proxy for Trend Strength
        # High Vol typically means Breakout/Trend. Low Vol = Range.

        capital = 10000.0
        position = 0.0
        tx_cost = 0.001
        trades = 0

        smoothed_vol = self.df["std_20"].rolling(10).mean()

        for i, row in self.df.iterrows():
            price = row["close"]

            # Regime Filter: Avoid high volatility expansion (breakout)
            # If current volatility is spikey (> 1.5x average), avoid fading it.
            # safe_regime = row['std_20'] < (smoothed_vol.iloc[i] * 1.5)
            # Cannot access smoothed_vol by iloc[i] easily in iterrows context without index align
            # Use pre-calc column

            # Let's assume we want to avoid "falling knives".
            # Filter: Don't buy if Price < BB Lower * 0.98 (Crash)
            crash_filter = price > (row["bb_lower"] * 0.99)

            # Entry
            if position == 0 and price < row["bb_lower"] and crash_filter:
                buy_amt = capital
                size = buy_amt / price
                cost = buy_amt * tx_cost
                if (capital - cost) > 0:
                    capital = 0
                    position = (buy_amt - cost) / price
                    trades += 1

            # Exit
            elif position > 0 and price > row["sma_20"]:
                revenue = position * price
                cost = revenue * tx_cost
                capital = revenue - cost
                position = 0
                trades += 1

        if position > 0:
            equity = position * self.df.iloc[-1]["close"]
        else:
            equity = capital
        return equity, trades


async def main():
    print("🔬 RUNNING MEAN REVERSION OPTIMIZATION (3 VARIANTS)...")

    # 1. Data
    dm = BacktestDataManager()
    raw_df = await dm.fetch_ohlcv("SOL/USD", interval="1h")
    df = dm.prepare_features(raw_df)
    print(f"Loaded {len(df)} candles.")

    runner = OptimizationRunner(df)
    results = []

    # Variant 1: Baseline
    eq1, tr1 = runner.run_baseline()
    results.append(["1. Baseline (BB 20,2)", f"${eq1:.2f}", f"{(eq1/10000 - 1)*100:.2f}%", tr1])

    # Variant 2: RSI Confluence
    eq2, tr2 = runner.run_rsi_confluence()
    results.append(["2. RSI Confluence (<30)", f"${eq2:.2f}", f"{(eq2/10000 - 1)*100:.2f}%", tr2])

    # Variant 3: Crash Filter
    eq3, tr3 = runner.run_adx_filter()
    results.append(["3. Crash Filter (>99% BB)", f"${eq3:.2f}", f"{(eq3/10000 - 1)*100:.2f}%", tr3])

    print("\n" + "=" * 60)
    print("🎯 OPTIMIZATION RESULTS")
    print("=" * 60)
    print(
        tabulate(
            results, headers=["Variant", "Final Equity", "Return", "Trades"], tablefmt="github"
        )
    )
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
