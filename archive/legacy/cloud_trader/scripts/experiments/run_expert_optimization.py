import asyncio
import logging

import numpy as np
import pandas as pd
from tabulate import tabulate

from cloud_trader.backtesting.data_manager import BacktestDataManager

# Setup
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)


class ExpertOptimizationRunner:
    def __init__(self, df):
        self.df = df

    def run_baseline(self):
        """Baseline (BB 20, 2.0)"""
        capital = 10000.0
        position = 0.0
        tx_cost = 0.001
        trades = 0

        for i, row in self.df.iterrows():
            price = row["close"]
            if position == 0 and price < row["bb_lower"]:
                buy_amt = capital
                cost = buy_amt * tx_cost
                if (capital - cost) > 0:
                    capital = 0
                    position = (buy_amt - cost) / price
                    trades += 1
            elif position > 0 and price > row["sma_20"]:
                revenue = position * price
                cost = revenue * tx_cost
                capital = revenue - cost
                position = 0
                trades += 1

        if position > 0:
            return position * self.df.iloc[-1]["close"], trades
        return capital, trades

    def run_adaptive_z_score(self):
        """
        Variant 4: Granular Z-Score Scaling
        - Scale IN:
          - 30% size at Z = -2.0
          - +30% size at Z = -2.5
          - +40% size at Z = -3.0
        - Exit: Z > 0 (Mean)
        """
        capital = 10000.0
        position = 0.0
        avg_entry = 0.0
        tx_cost = 0.001
        trades = 0

        # State
        entries_made = 0  # 0, 1, 2, 3

        for i, row in self.df.iterrows():
            price = row["close"]
            sma = row["sma_20"]
            std = row["std_20"]

            if std == 0:
                continue

            z_score = (price - sma) / std

            # EXIT CONDITION (Mean Reversion)
            if position > 0 and z_score > 0:  # Returned to mean
                revenue = position * price
                cost = revenue * tx_cost
                capital += revenue - cost
                position = 0
                entries_made = 0
                trades += 1
                continue

            # ENTRY SCALING
            # Level 1: Z < -2.0 (Initiate)
            if entries_made == 0 and z_score < -2.0:
                # Deploy 30% of CURRENT capital (approx)
                # Actually, deploy 30% of INITIAL capacity strategy
                # Let's say max deployment is current capital.
                # Deploy 1/3 of available cash

                investment = capital * 0.33
                size = investment / price
                cost = investment * tx_cost

                capital -= investment + cost  # Logic check: cost is extra or inclusive?
                # Inclusive for safety

                position += size
                entries_made = 1
                trades += 1

            # Level 2: Z < -2.5 (Add)
            elif entries_made == 1 and z_score < -2.5:
                # Deploy 50% of REMAINING cash (approx equal chunk)
                investment = capital * 0.5
                size = investment / price
                cost = investment * tx_cost

                capital -= investment + cost
                position += size
                entries_made = 2

            # Level 3: Z < -3.0 (All In)
            elif entries_made == 2 and z_score < -3.0:
                # Deploy ALL remaining
                investment = capital
                size = investment / price
                cost = investment * tx_cost

                # Check bounds
                if capital > cost:
                    capital = 0
                    position += (investment - cost) / price
                    entries_made = 3

        if position > 0:
            equity = position * self.df.iloc[-1]["close"]
        else:
            equity = capital

        return equity, trades

    def run_vwap_bands(self):
        """
        Variant 5: Institutional VWAP Bands (Approx)
        Using 'typical price' * volume to approx VWAP since start of 'period' (24h).
        """
        # Need to calculate VWAP
        # Rolling 24h VWAP
        df = self.df.copy()
        df["tp"] = (df["high"] + df["low"] + df["close"]) / 3
        df["tpv"] = df["tp"] * df["volume"]

        # Rolling 24 sum
        df["cum_tpv"] = df["tpv"].rolling(24).sum()
        df["cum_vol"] = df["volume"].rolling(24).sum()
        df["vwap"] = df["cum_tpv"] / df["cum_vol"]

        # VWAP Bands: VWAP +/- 2 * StdDev (of close relative to VWAP? or just std20)
        # Often VWAP bands use standard deviation of price itself.
        # Let's use standard deviation of price over last 24h
        df["std_24"] = df["close"].rolling(24).std()

        df["vwap_lower"] = df["vwap"] - (2.0 * df["std_24"])

        capital = 10000.0
        position = 0.0
        tx_cost = 0.001
        trades = 0

        for i, row in df.iterrows():
            price = row["close"]
            vwap = row["vwap"]

            if np.isnan(vwap):
                continue

            # Entry: Price < VWAP Lower
            if position == 0 and price < row["vwap_lower"]:
                buy_amt = capital
                cost = buy_amt * tx_cost
                if (capital - cost) > 0:
                    capital = 0
                    position = (buy_amt - cost) / price
                    trades += 1

            # Exit: Price > VWAP (Mean)
            elif position > 0 and price > vwap:
                revenue = position * price
                cost = revenue * tx_cost
                capital = revenue - cost
                position = 0
                trades += 1

        if position > 0:
            return position * df.iloc[-1]["close"], trades
        return capital, trades


async def main():
    print("🧠 RUNNING EXPERT STRATEGY OPTIMIZATION (GRANULAR TWEAKS)...")

    # 1. Data
    dm = BacktestDataManager()
    # Ensure fresh load if new columns needed? No, calc on fly in runner for VWAP
    raw_df = await dm.fetch_ohlcv("SOL/USD", interval="1h")
    df = dm.prepare_features(raw_df)
    print(f"Loaded {len(df)} candles.")

    runner = ExpertOptimizationRunner(df)
    results = []

    # Baseline
    eq1, tr1 = runner.run_baseline()
    results.append(["1. Baseline (BB 20,2)", f"${eq1:.2f}", f"{(eq1/10000 - 1)*100:.2f}%", tr1])

    # Adaptive Z-Score
    eq2, tr2 = runner.run_adaptive_z_score()
    results.append(
        ["4. Adaptive Z-Score (Scale-in)", f"${eq2:.2f}", f"{(eq2/10000 - 1)*100:.2f}%", tr2]
    )

    # VWAP Bands
    eq3, tr3 = runner.run_vwap_bands()
    results.append(
        ["5. Institutional VWAP Bands", f"${eq3:.2f}", f"{(eq3/10000 - 1)*100:.2f}%", tr3]
    )

    print("\n" + "=" * 65)
    print("💎 EXPERT OPTIMIZATION RESULTS")
    print("=" * 65)
    print(
        tabulate(
            results, headers=["Variant", "Final Equity", "Return", "Trades"], tablefmt="github"
        )
    )
    print("=" * 65)

    if eq2 > eq1:
        print("\n🚀 WINNER: ADAPTIVE SCALING! The granular approach paid off.")
    else:
        print("\n🛡 WINNER: BASELINE. Simple execution beat complexity.")


if __name__ == "__main__":
    asyncio.run(main())
