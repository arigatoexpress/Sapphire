"""Backtesting engine using VectorBT for historical strategy simulation."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ..service import AGENT_DEFINITIONS
from .agents import BacktestAgent, BacktestAgentDecision, create_backtest_agent
from .data_loader import BacktestDataLoader

logger = logging.getLogger(__name__)


@dataclass
class BacktestResults:
    """Results from a backtest run."""

    run_id: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    total_return: float
    annualized_return: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    agent_performance: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    equity_curve: List[float] = field(default_factory=list)
    trades: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)


class BacktestEngine:
    """Backtesting engine for simulating trading strategies on historical data."""

    def __init__(
        self,
        initial_capital: float = 10000.0,
        data_loader: Optional[BacktestDataLoader] = None,
    ):
        self.initial_capital = initial_capital
        self.data_loader = data_loader or BacktestDataLoader()
        self.agents: Dict[str, BacktestAgent] = {}
        self._initialize_agents()

    def _initialize_agents(self) -> None:
        """Initialize backtest-compatible agents from AGENT_DEFINITIONS."""
        for agent_def in AGENT_DEFINITIONS:
            agent_id = agent_def["id"]
            agent_type = agent_def["id"]

            # Create agent config from definition
            agent_config = {
                "baseline_win_rate": agent_def.get("baseline_win_rate", 0.5),
                "risk_multiplier": agent_def.get("risk_multiplier", 1.0),
                "profit_target": agent_def.get("profit_target", 0.01),
                "margin_allocation": agent_def.get("margin_allocation", 500.0),
                "min_position_size_pct": agent_def.get("min_position_size_pct", 0.005),
                "max_position_size_pct": agent_def.get("max_position_size_pct", 0.08),
                "stop_loss": agent_def.get("profit_target", 0.01) * 0.5,  # SL at 50% of TP
            }

            agent = create_backtest_agent(agent_id, agent_type, agent_config)
            self.agents[agent_id] = agent
            logger.info(f"Initialized backtest agent: {agent_id}")

    async def run_backtest(
        self,
        symbols: List[str],
        start_date: datetime,
        end_date: datetime,
        interval: str = "1h",
    ) -> BacktestResults:
        """Run backtest on historical data for specified symbols and date range."""
        run_id = str(uuid.uuid4())
        logger.info(f"Starting backtest {run_id} from {start_date} to {end_date}")

        # Load historical market data
        market_data: Dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            data = await self.data_loader.load_market_data(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                interval=interval,
            )
            if data is not None and not data.empty:
                market_data[symbol] = data

        if not market_data:
            logger.error("No market data loaded for backtesting")
            return BacktestResults(
                run_id=run_id,
                start_date=start_date,
                end_date=end_date,
                initial_capital=self.initial_capital,
                final_capital=self.initial_capital,
                total_return=0.0,
                annualized_return=0.0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                max_drawdown=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                profit_factor=0.0,
                avg_win=0.0,
                avg_loss=0.0,
            )

        # Align timestamps across all symbols
        all_timestamps = set()
        for df in market_data.values():
            all_timestamps.update(df.index)
        timestamps = sorted(all_timestamps)

        # Simulate trading
        capital = self.initial_capital
        positions: Dict[str, Dict[str, Any]] = {}  # symbol -> position dict
        closed_trades: List[Dict[str, Any]] = []
        equity_curve: List[float] = [self.initial_capital]

        for timestamp in timestamps:
            # Get current market data
            current_market: Dict[str, pd.Series] = {}
            for symbol, df in market_data.items():
                try:
                    row = df.loc[timestamp]
                    current_market[symbol] = row
                except KeyError:
                    continue

            if not current_market:
                continue

            # Check existing positions for exit conditions
            positions_to_close = []
            for symbol, position in positions.items():
                if symbol not in current_market:
                    continue

                current_price = current_market[symbol]["close"]
                entry_price = position["entry_price"]
                side = position["side"]

                # Calculate P&L
                if side == "BUY":
                    pnl_pct = (current_price - entry_price) / entry_price
                else:  # SELL
                    pnl_pct = (entry_price - current_price) / entry_price

                # Check exit conditions
                take_profit_pct = position.get("take_profit_pct", 0.01)
                stop_loss_pct = position.get("stop_loss_pct", 0.005)

                should_exit = False
                exit_reason = None

                # Take profit
                if pnl_pct >= take_profit_pct:
                    should_exit = True
                    exit_reason = "take_profit"

                # Stop loss
                elif pnl_pct <= -stop_loss_pct:
                    should_exit = True
                    exit_reason = "stop_loss"

                # Time-based exit (24 hours)
                elif (timestamp - position["entry_time"]).total_seconds() > 86400:
                    should_exit = True
                    exit_reason = "time_exit"

                if should_exit:
                    positions_to_close.append((symbol, current_price, exit_reason))

            # Close positions
            for symbol, exit_price, exit_reason in positions_to_close:
                position = positions.pop(symbol)
                pnl_abs = self._calculate_pnl(position, exit_price)
                capital += pnl_abs

                closed_trades.append(
                    {
                        "symbol": symbol,
                        "side": position["side"],
                        "entry_price": position["entry_price"],
                        "exit_price": exit_price,
                        "entry_time": position["entry_time"],
                        "exit_time": timestamp,
                        "quantity": position["quantity"],
                        "notional": position["notional"],
                        "pnl_abs": pnl_abs,
                        "pnl_pct": (
                            (exit_price - position["entry_price"]) / position["entry_price"]
                            if position["side"] == "BUY"
                            else (position["entry_price"] - exit_price) / position["entry_price"]
                        ),
                        "agent_id": position["agent_id"],
                        "exit_reason": exit_reason,
                    }
                )

            # Check for new entry signals
            if len(positions) < 5:  # Max concurrent positions
                for symbol, row in current_market.items():
                    if symbol in positions:
                        continue

                    # Get historical window for analysis
                    historical = self._get_historical_window(
                        symbol, timestamp, market_data[symbol], window=30
                    )

                    # Create market snapshot
                    snapshot = self._create_market_snapshot(symbol, row, historical)

                    # Evaluate with all agents (similar to live system)
                    best_decision: Optional[BacktestAgentDecision] = None
                    best_confidence = 0.0

                    for agent_id, agent in self.agents.items():
                        decision = await agent.evaluate(
                            symbol=symbol,
                            timestamp=timestamp,
                            market_snapshot=snapshot,
                            historical_data=historical,
                        )

                        if decision and decision.confidence > best_confidence:
                            best_decision = decision
                            best_confidence = decision.confidence

                    # Open position if we have a good signal
                    if best_decision and best_confidence >= 0.6:
                        position_size = capital * best_decision.position_size_pct
                        quantity = position_size / row["close"]

                        positions[symbol] = {
                            "symbol": symbol,
                            "side": best_decision.signal.direction,
                            "entry_price": row["close"],
                            "quantity": quantity,
                            "notional": position_size,
                            "entry_time": timestamp,
                            "agent_id": best_decision.agent_id,
                            "take_profit_pct": best_decision.take_profit_pct,
                            "stop_loss_pct": best_decision.stop_loss_pct,
                        }

                        capital -= position_size * 0.1  # 10% margin requirement

            # Update equity curve
            total_equity = capital
            for symbol, position in positions.items():
                if symbol in current_market:
                    current_price = current_market[symbol]["close"]
                    pnl_abs = self._calculate_pnl(position, current_price)
                    total_equity += pnl_abs

            equity_curve.append(total_equity)

        # Close any remaining positions at end
        for symbol, position in list(positions.items()):
            if symbol in current_market:
                exit_price = current_market[symbol]["close"]
                pnl_abs = self._calculate_pnl(position, exit_price)
                capital += pnl_abs

                closed_trades.append(
                    {
                        "symbol": symbol,
                        "side": position["side"],
                        "entry_price": position["entry_price"],
                        "exit_price": exit_price,
                        "entry_time": position["entry_time"],
                        "exit_time": end_date,
                        "quantity": position["quantity"],
                        "notional": position["notional"],
                        "pnl_abs": pnl_abs,
                        "pnl_pct": (
                            (exit_price - position["entry_price"]) / position["entry_price"]
                            if position["side"] == "BUY"
                            else (position["entry_price"] - exit_price) / position["entry_price"]
                        ),
                        "agent_id": position["agent_id"],
                        "exit_reason": "end_of_backtest",
                    }
                )

        # Calculate results
        results = self._calculate_results(
            run_id=run_id,
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            final_capital=capital,
            equity_curve=equity_curve,
            closed_trades=closed_trades,
        )

        logger.info(
            f"Backtest {run_id} completed: {results.total_return:.2%} return, {results.total_trades} trades"
        )
        return results

    def _calculate_pnl(self, position: Dict[str, Any], current_price: float) -> float:
        """Calculate P&L for a position."""
        if position["side"] == "BUY":
            return (current_price - position["entry_price"]) * position["quantity"]
        else:  # SELL
            return (position["entry_price"] - current_price) * position["quantity"]

    def _create_market_snapshot(
        self,
        symbol: str,
        row: pd.Series,
        historical: pd.DataFrame,
    ) -> Any:
        """Create MarketSnapshot from market data row."""
        from ..strategy import MarketSnapshot

        # Calculate 24h change if we have enough historical data
        change_24h = 0.0
        if len(historical) >= 24:  # Assuming hourly data
            current_price = row["close"]
            past_price = historical.iloc[-24]["close"]
            change_24h = ((current_price - past_price) / past_price) * 100

        return MarketSnapshot(
            symbol=symbol,
            price=row["close"],
            volume=row["volume"],
            change_24h=change_24h,
        )

    def _get_historical_window(
        self,
        symbol: str,
        timestamp: datetime,
        df: pd.DataFrame,
        window: int,
    ) -> pd.DataFrame:
        """Get historical data window up to timestamp."""
        try:
            idx = df.index.get_loc(timestamp)
            start_idx = max(0, idx - window + 1)
            return df.iloc[start_idx : idx + 1]
        except (KeyError, IndexError):
            return pd.DataFrame()

    def _calculate_results(
        self,
        run_id: str,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float,
        final_capital: float,
        equity_curve: List[float],
        closed_trades: List[Dict[str, Any]],
    ) -> BacktestResults:
        """Calculate comprehensive backtest results."""
        if not closed_trades:
            return BacktestResults(
                run_id=run_id,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                final_capital=final_capital,
                total_return=0.0,
                annualized_return=0.0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                max_drawdown=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                profit_factor=0.0,
                avg_win=0.0,
                avg_loss=0.0,
                equity_curve=equity_curve,
                trades=closed_trades,
            )

        # Basic metrics
        total_trades = len(closed_trades)
        winning_trades = sum(1 for t in closed_trades if t["pnl_pct"] > 0)
        losing_trades = total_trades - winning_trades
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

        # Returns
        total_return = (final_capital - initial_capital) / initial_capital

        # Annualized return
        days = (end_date - start_date).days
        years = days / 365.25 if days > 0 else 1.0
        annualized_return = (
            ((final_capital / initial_capital) ** (1 / years) - 1) if years > 0 else 0.0
        )

        # Max drawdown
        equity_array = np.array(equity_curve)
        peak = np.maximum.accumulate(equity_array)
        drawdown = (peak - equity_array) / peak
        max_drawdown = float(np.max(drawdown)) if len(drawdown) > 0 else 0.0

        # Sharpe ratio
        returns = (
            np.diff(equity_array) / equity_array[:-1] if len(equity_array) > 1 else np.array([0.0])
        )
        sharpe_ratio = 0.0
        if len(returns) > 0 and np.std(returns) > 0:
            sharpe_ratio = float(
                np.mean(returns) / np.std(returns) * np.sqrt(252 * 24)
            )  # Hourly to annual

        # Sortino ratio
        sortino_ratio = 0.0
        negative_returns = returns[returns < 0]
        if len(negative_returns) > 0 and np.std(negative_returns) > 0:
            sortino_ratio = float(np.mean(returns) / np.std(negative_returns) * np.sqrt(252 * 24))

        # Profit factor
        gross_profit = sum(t["pnl_abs"] for t in closed_trades if t["pnl_abs"] > 0)
        gross_loss = abs(sum(t["pnl_abs"] for t in closed_trades if t["pnl_abs"] < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Average win/loss
        winning_trade_pnls = [t["pnl_pct"] for t in closed_trades if t["pnl_pct"] > 0]
        losing_trade_pnls = [t["pnl_pct"] for t in closed_trades if t["pnl_pct"] < 0]
        avg_win = float(np.mean(winning_trade_pnls)) if winning_trade_pnls else 0.0
        avg_loss = float(np.mean(losing_trade_pnls)) if losing_trade_pnls else 0.0

        # Agent performance breakdown
        agent_performance: Dict[str, Dict[str, Any]] = {}
        for trade in closed_trades:
            agent_id = trade.get("agent_id", "unknown")
            if agent_id not in agent_performance:
                agent_performance[agent_id] = {
                    "trades": 0,
                    "wins": 0,
                    "total_pnl": 0.0,
                    "win_rate": 0.0,
                }

            perf = agent_performance[agent_id]
            perf["trades"] += 1
            if trade["pnl_pct"] > 0:
                perf["wins"] += 1
            perf["total_pnl"] += trade["pnl_abs"]

        # Calculate agent metrics
        for agent_id, perf in agent_performance.items():
            perf["win_rate"] = perf["wins"] / perf["trades"] if perf["trades"] > 0 else 0.0

        return BacktestResults(
            run_id=run_id,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            final_capital=final_capital,
            total_return=total_return,
            annualized_return=annualized_return,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            agent_performance=agent_performance,
            equity_curve=equity_curve,
            trades=closed_trades,
        )
