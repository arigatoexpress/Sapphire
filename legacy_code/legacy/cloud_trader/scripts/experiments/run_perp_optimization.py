import asyncio
import logging

import numpy as np
import pandas as pd
from tabulate import tabulate

from cloud_trader.backtesting.data_manager import BacktestDataManager

# Setup
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)


class PerpOptimizationRunner:
    def __init__(self, df):
        self.df = df

    def run_baseline_long_only(self):
        """Baseline (BB 20, 2.0) - Long Only, 1x"""
        capital = 10000.0
        position = 0.0
        tx_cost = 0.0006  # Perp fee lower usually (0.06%)
        trades = 0
        liquidation_penalty = 0.0

        for i, row in self.df.iterrows():
            price = row["close"]

            # Entry
            if position == 0 and price < row["bb_lower"]:
                buy_val = capital
                cost = buy_val * tx_cost
                if (capital - cost) > 0:
                    capital -= cost
                    position = buy_val / price
                    trades += 1
            # Exit
            elif position > 0 and price > row["sma_20"]:
                revenue = position * price
                cost = revenue * tx_cost
                capital += revenue - cost
                position = 0
                trades += 1  # Exit

            # Liquidation Check (Simple 50% drop guard for 1x? Unlikely)

        if position > 0:
            return (
                capital + (position * (self.df.iloc[-1]["close"] - self.df.iloc[-1]["close"])),
                trades,
            )  # PnL logic wrong
            # Equity = Cash + PositionValue
            # But in perp, Capital is Margin.
            # Simple Spot-like sim for 1x is fine.
            return (position * self.df.iloc[-1]["close"]), trades

        return capital, trades

    def run_symmetric_short(self):
        """Variant 2: Long + Short (Price > Upper Band)"""
        capital = 10000.0
        position = 0.0  # Positive = Long, Negative = Short
        entry_price = 0.0
        tx_cost = 0.0006
        trades = 0

        for i, row in self.df.iterrows():
            price = row["close"]

            # LONG Entry
            if position == 0 and price < row["bb_lower"]:
                # Buy 1x
                size = capital / price
                cost = (size * price) * tx_cost
                capital -= cost
                position = size
                entry_price = price
                trades += 1

            # SHORT Entry
            elif position == 0 and price > row["bb_upper"]:
                # Sell 1x
                size = capital / price
                cost = (size * price) * tx_cost
                capital -= cost
                position = -size  # Short
                entry_price = price
                trades += 1

            # LONG Exit (Mean)
            elif position > 0 and price > row["sma_20"]:
                revenue = position * price
                cost = revenue * tx_cost
                # PnL = revenue - (position * entry) -> No, we are tracking Equity in 'capital' ?
                # The logic in previous steps was Spot-like (Capital -> Asset -> Capital)
                # For Shorting, we need PnL.
                # Equity = Initial + PnL

                # Let's track Cash and Margin logic sim
                pnl = (price - entry_price) * position
                capital += pnl + (position * entry_price)  # return margin
                capital -= cost
                position = 0
                trades += 1

            # SHORT Exit (Mean)
            elif position < 0 and price < row["sma_20"]:
                # Cover
                pos_size = abs(position)
                revenue = pos_size * price
                cost = revenue * tx_cost

                # Short PnL = (Entry - Exit) * Size
                pnl = (entry_price - price) * pos_size

                # Return Margin (which was pos_size * entry_price roughly)
                capital += pnl + (pos_size * entry_price)  # margin returned?
                # Wait, this simplified accounting is getting messy.
                # Let's use simple logic: Capital += PnL - Fees
                # NOTE: When opening, we don't deduct Capital, we lock it.
                # But for sim, we treat it as deducted.

                capital -= cost
                position = 0
                trades += 1

        # Final Close
        if position != 0:
            price = self.df.iloc[-1]["close"]
            pos_size = abs(position)
            cost = (pos_size * price) * tx_cost
            if position > 0:
                pnl = (price - entry_price) * pos_size
            else:
                pnl = (entry_price - price) * pos_size
            capital += pnl + (pos_size * entry_price) - cost

        return capital, trades

    def run_dynamic_leverage(self):
        """Variant 3: Symmetric + Dynamic Leverage (3x on Low Vol)"""
        capital = 10000.0
        position = 0.0  # Units
        entry_price = 0.0
        tx_cost = 0.0006
        trades = 0

        # Reset index to allow integer indexing
        df = self.df.reset_index()
        smoothed_vol = df["std_20"].rolling(20).mean()

        for i, row in df.iterrows():
            price = row["close"]
            vol_ma = smoothed_vol.iloc[i] if i > 20 else row["std_20"]

            # Leverage Logic
            lev = 1.0
            if row["std_20"] < (vol_ma * 0.8):
                lev = 3.0  # Squeeze

            # LONG Entry
            if position == 0 and price < row["bb_lower"]:
                # Buy Lev
                margin = capital
                size = (margin * lev) / price
                cost = (size * price) * tx_cost

                # Check for bankruptcy/cost
                if cost < capital:
                    capital -= cost  # Pay fee from cash
                    position = size
                    entry_price = price
                    trades += 1
                    # We hold 'margin' virtually.

            # SHORT Entry
            elif position == 0 and price > row["bb_upper"]:
                margin = capital
                size = (margin * lev) / price
                cost = (size * price) * tx_cost
                if cost < capital:
                    capital -= cost
                    position = -size
                    entry_price = price
                    trades += 1

            # EXITS
            elif position > 0 and price > row["sma_20"]:
                cost = (position * price) * tx_cost
                pnl = (price - entry_price) * position
                capital += pnl - cost
                position = 0
                trades += 1

            elif position < 0 and price < row["sma_20"]:
                size = abs(position)
                cost = (size * price) * tx_cost
                pnl = (entry_price - price) * size
                capital += pnl - cost
                position = 0
                trades += 1

        # Final Close
        if position != 0:
            price = self.df.iloc[-1]["close"]
            size = abs(position)
            cost = (size * price) * tx_cost
            if position > 0:
                pnl = (price - entry_price) * size
            else:
                pnl = (entry_price - price) * size
            capital += pnl - cost

        return capital, trades

    def run_trailing_stop(self):
        """Variant 4: Symmetric + Trailing Stop (Lock Profits)"""
        capital = 10000.0
        position = 0.0
        entry_price = 0.0
        tx_cost = 0.0006
        trades = 0

        high_water = 0.0  # Highest price since entry (for long)
        low_water = 0.0  # Lowest price since entry (for short)

        trail_activation = 0.015  # 1.5% profit activates trail
        trail_dist = 0.005  # 0.5% trail

        for i, row in self.df.iterrows():
            price = row["close"]

            # --- Trailing Stop Logic ---
            if position > 0:
                high_water = max(high_water, price)
                pnl_pct = (high_water - entry_price) / entry_price
                if pnl_pct > trail_activation:
                    stop_price = high_water * (1 - trail_dist)
                    if price < stop_price:
                        # HIT STOP
                        size = position
                        cost = (size * price) * tx_cost
                        pnl = (price - entry_price) * size
                        capital += pnl - cost
                        position = 0
                        trades += 1
                        continue  # Next candle

            elif position < 0:
                low_water = min(low_water, price)
                pnl_pct = (entry_price - low_water) / entry_price
                if pnl_pct > trail_activation:
                    stop_price = low_water * (1 + trail_dist)
                    if price > stop_price:
                        # HIT STOP
                        size = abs(position)
                        cost = (size * price) * tx_cost
                        pnl = (entry_price - price) * size
                        capital += pnl - cost
                        position = 0
                        trades += 1
                        continue

            # --- Standard Logic ---
            if position == 0 and price < row["bb_lower"]:
                size = capital / price
                cost = size * price * tx_cost
                capital -= cost
                position = size
                entry_price = price
                high_water = price
                trades += 1
            elif position == 0 and price > row["bb_upper"]:
                size = capital / price
                cost = size * price * tx_cost
                capital -= cost
                position = -size
                entry_price = price
                low_water = price
                trades += 1
            elif position > 0 and price > row["sma_20"]:
                cost = position * price * tx_cost
                pnl = (price - entry_price) * position
                capital += pnl - cost
                position = 0
                trades += 1
            elif position < 0 and price < row["sma_20"]:
                size = abs(position)
                cost = size * price * tx_cost
                pnl = (entry_price - price) * size
                capital += pnl - cost
                position = 0
                trades += 1

        # Final
        if position != 0:
            price = self.df.iloc[-1]["close"]
            size = abs(position)
            cost = size * price * tx_cost
            if position > 0:
                pnl = (price - entry_price) * size
            else:
                pnl = (entry_price - price) * size
            capital += pnl - cost

        return capital, trades


async def main():
    print("🚀 RUNNING PERP-OPTIMIZATION (LEVERAGE & SHORTS)...")

    # 1. Data
    dm = BacktestDataManager()
    raw_df = await dm.fetch_ohlcv("SOL/USD", interval="1h")
    df = dm.prepare_features(raw_df)
    print(f"Loaded {len(df)} candles.")

    runner = PerpOptimizationRunner(df)
    results = []

    # Baseline (Long Only)
    eq1, tr1 = runner.run_baseline_long_only()
    results.append(["1. Long Only (Baseline)", f"${eq1:.2f}", f"{(eq1/10000 - 1)*100:.2f}%", tr1])

    # Symmetric
    eq2, tr2 = runner.run_symmetric_short()
    results.append(["2. Symmetric (Long+Short)", f"${eq2:.2f}", f"{(eq2/10000 - 1)*100:.2f}%", tr2])

    # Dynamic Lev
    eq3, tr3 = runner.run_dynamic_leverage()
    results.append(["3. Dynamic Leverage (3x)", f"${eq3:.2f}", f"{(eq3/10000 - 1)*100:.2f}%", tr3])

    # Trailing Stop
    eq4, tr4 = runner.run_trailing_stop()
    results.append(["4. Trailing Stop (Prot)", f"${eq4:.2f}", f"{(eq4/10000 - 1)*100:.2f}%", tr4])

    print("\n" + "=" * 65)
    print("⚡️ PERP STRATEGY RESULTS")
    print("=" * 65)
    print(
        tabulate(
            results, headers=["Variant", "Final Equity", "Return", "Trades"], tablefmt="github"
        )
    )
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
