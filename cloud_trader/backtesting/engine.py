"""
Vectorized Backtesting Engine.
Simulates trading strategies with realistic slippage and fees.
"""

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    equity_curve: pd.Series
    trade_log: pd.DataFrame


class BacktestEngine:
    def __init__(
        self,
        initial_capital: float = 10000.0,
        commission_rate: float = 0.001,  # 0.1%
        slippage_bps: float = 5.0,  # 5 basis points
    ):
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage = slippage_bps / 10000.0

    def run(
        self,
        data: pd.DataFrame,
        strategy_func: Callable[[pd.DataFrame, Dict], pd.Series],
        params: Dict[str, Any],
    ) -> BacktestResult:
        """
        Run backtest.

        Args:
            data: OHLCV DataFrame with indicators
            strategy_func: Function returning signal Series (1=Long, -1=Short, 0=Neutral)
            params: Strategy parameters
        """
        df = data.copy()

        # Generate Signals
        # Signal: 1 (Enter Long), 0 (Exit), -1 (Enter Short - optionally)
        # For this MVP, let's assume Long-Only or Long/Short switching
        df["signal"] = strategy_func(df, params)

        # Shift signals to represent execution at NEXT OPEN or close delay
        # standard is signal at close -> trade at next open
        # For simplicity in vectorized: trade at 'close' of signal candle with slippage
        # OR trade at next 'open'. Let's use current Close with slippage penalty

        df["position"] = df["signal"].shift(1).fillna(0)  # Position held during this candle

        # Calculate Returns
        # pct_change is (Current - Previous) / Previous
        df["asset_return"] = df["close"].pct_change()
        df["strategy_return"] = df["position"] * df["asset_return"]

        # Transaction Costs
        # Trades happen when position changes
        df["trade"] = df["position"].diff().abs().fillna(0)

        # Cost = Commission + Slippage on the turnover
        # Assuming turnover = price * amount. In % terms relative to equity:
        # Cost % = trade_size * (comm + slip)
        transaction_cost_pct = df["trade"] * (self.commission_rate + self.slippage)
        df["net_return"] = df["strategy_return"] - transaction_cost_pct

        # Equity Curve
        df["equity_factor"] = (1 + df["net_return"]).cumprod()
        df["equity"] = self.initial_capital * df["equity_factor"]

        # Calculate Metrics
        return self._calculate_metrics(df)

    def _calculate_metrics(self, df: pd.DataFrame) -> BacktestResult:
        total_return = (df["equity"].iloc[-1] / self.initial_capital) - 1

        # Sharpe (Annualized) - Assuming hourly data?
        # Need to detect frequency.
        # Approx 24*365 = 8760 hours/year.
        # If daily, 252.

        time_span_days = (df.index[-1] - df.index[0]).days
        if time_span_days > 0:
            years = time_span_days / 365.25
            periods_per_year = len(df) / years if years > 0 else 252
        else:
            periods_per_year = 252  # Fallback

        returns = df["net_return"]
        if returns.std() > 0:
            sharpe = (returns.mean() / returns.std()) * np.sqrt(periods_per_year)
        else:
            sharpe = 0.0

        # Max Drawdown
        cummax = df["equity"].cummax()
        drawdown = (df["equity"] - cummax) / cummax
        max_drawdown = drawdown.min()

        # Trade Stats
        # Simple extraction based on 'trade' > 0
        trade_indices = df[df["trade"] > 0].index
        trades_count = len(trade_indices)

        # Estimate Win Rate (candles with positive return while in position)
        # This is granular. For real trade-by-trade, iteration is better, but this is vectorized.
        # Approx:
        winning_periods = len(df[df["net_return"] > 0])
        losing_periods = len(df[df["net_return"] < 0])
        win_rate = (
            winning_periods / (winning_periods + losing_periods)
            if (winning_periods + losing_periods) > 0
            else 0
        )

        avg_win = df[df["net_return"] > 0]["net_return"].mean()
        avg_loss = abs(df[df["net_return"] < 0]["net_return"].mean())
        profit_factor = avg_win / avg_loss if avg_loss > 0 else 0

        return BacktestResult(
            total_return=total_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=trades_count,
            equity_curve=df["equity"],
            trade_log=df[["close", "position", "equity"]],
        )
