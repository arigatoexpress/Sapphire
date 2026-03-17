"""
Iterative Backtesting Engine for RL Agents.
Simulates trading step-by-step to allow stateful agent interactions.
"""

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class IterativeResult:
    total_return: float
    equity_curve: pd.Series
    metrics: Dict[str, Any]


class IterativeBacktestEngine:
    def __init__(self, initial_capital=10000.0, commission=0.001):
        self.initial_capital = initial_capital
        self.commission = commission

    def run_agent(
        self,
        df: pd.DataFrame,
        agent_step_func: Callable[
            [pd.Series, Any], Tuple[int, float]
        ],  # args: (row, state) -> (action, size)
        agent_state: Any = None,
    ) -> IterativeResult:
        """
        Run backtest iterating row by row.
        action: 1 (Buy), -1 (Sell), 0 (Hold/Close)
        """
        capital = self.initial_capital
        position = 0.0  # Asset amount
        equity_curve = []

        # State tracking
        current_equity = capital

        for i in range(len(df)):
            row = df.iloc[i]
            price = row["close"]

            # Update Equity (Mark to Market)
            current_equity = capital + (position * price)
            equity_curve.append(current_equity)

            # Agent Decision
            # Agent sees current row (state) and internal state
            action, size_fraction = agent_step_func(row, agent_state)

            # Execute
            if action == 1:  # Buy / Long
                # If we are flat, buy
                # If we are short, close then buy (flip)
                if position <= 0:
                    # Close Short if exists
                    if position < 0:
                        cost = abs(position * price) * self.commission
                        capital -= cost
                        capital += position * price  # Return short collateral + profit
                        position = 0

                    # Open Long
                    # size_fraction of EQUITY
                    target_size = (current_equity * size_fraction) / price
                    cost = (target_size * price) * self.commission
                    if capital >= cost:
                        capital -= (target_size * price) + cost
                        position += target_size

            elif action == -1:  # Sell / Short
                if position >= 0:
                    # Close Long
                    if position > 0:
                        revenue = position * price
                        cost = revenue * self.commission
                        capital += revenue - cost
                        position = 0

                    # Open Short
                    # Simplified: Assume we can leverage or just inverse
                    # For this test, let's treat -1 as "Exit Long" or "Go Short"
                    # If simplified to Long/Flat:
                    pass

            elif action == 0:  # Flat / Exit
                if position != 0:
                    # Close all
                    val = abs(position * price)
                    cost = val * self.commission
                    if position > 0:
                        capital += (position * price) - cost
                    else:
                        capital += (position * price) - cost  # Logic for short closing
                    position = 0

        # Final Close
        final_price = df.iloc[-1]["close"]
        if position != 0:
            val = abs(position * final_price)
            capital += (position * final_price) - (val * self.commission)

        total_ret = (capital / self.initial_capital) - 1
        return IterativeResult(
            total_return=total_ret,
            equity_curve=pd.Series(equity_curve, index=df.index),
            metrics={"final_equity": capital},
        )
