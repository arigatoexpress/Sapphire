"""
Performance Analytics Module for Aster Self-Learning Agents.
Tracks Sharpe Ratio, Sortino Ratio, Win Rate, and Alpha relative to Benchmark.

Now with GCS-backed persistence for durability across deployments.
"""

import asyncio
import json
import logging
import math
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Import persistent storage
try:
    from ..persistent_metrics import (
        get_metrics_store,
        load_analytics_metrics,
        save_analytics_metrics,
    )

    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False
    logger.warning("⚠️ Persistent metrics not available, using local-only mode")


@dataclass
class AgentMetrics:
    agent_id: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    equity_curve: List[float] = field(default_factory=list)
    timestamps: List[float] = field(default_factory=list)
    returns_history: List[float] = field(default_factory=list)
    max_drawdown: float = 0.0
    peak_equity: float = 0.0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0  # Return / Max Drawdown
    recovery_factor: float = 0.0  # Total PnL / Max Drawdown
    expectancy: float = 0.0  # (Win% * AvgWin) - (Loss% * AvgLoss)
    alpha: float = 0.0  # Excess return vs benchmark
    beta: float = 0.0  # Correlation with benchmark
    profit_factor: float = 0.0
    average_win: float = 0.0
    average_loss: float = 0.0
    last_updated: float = 0.0


class PerformanceTracker:
    """Analytics performance tracker with GCS-backed persistence."""

    def __init__(self, storage_path: str = "/tmp/sapphire_metrics/analytics_metrics.json"):
        self.storage_path = storage_path
        self.metrics: Dict[str, AgentMetrics] = {}
        self.risk_free_rate = 0.02  # 2% annual risk free
        self.use_gcs = GCS_AVAILABLE
        self._pending_save = False

        # Ensure directory exists
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        self._load_metrics()

    def _load_metrics(self):
        """Load metrics from disk."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                    for agent_id, m_data in data.items():
                        if not agent_id.startswith("_"):
                            self.metrics[agent_id] = AgentMetrics(**m_data)
                logger.info(f"📊 Loaded analytics metrics for {len(self.metrics)} agents")
            except Exception as e:
                logger.error(f"Failed to load metrics: {e}")

    async def initialize(self):
        """Async initialization - loads from GCS on startup."""
        if self.use_gcs:
            try:
                loaded = await load_analytics_metrics()
                if loaded:
                    for agent_id, m_data in loaded.items():
                        if not agent_id.startswith("_"):
                            if agent_id not in self.metrics:
                                self.metrics[agent_id] = AgentMetrics(**m_data)
                    logger.info(f"☁️ Synced analytics metrics from GCS: {len(self.metrics)} agents")
            except Exception as e:
                logger.warning(f"⚠️ GCS sync failed: {e}")

    def save_metrics(self):
        """Save metrics to disk and queue GCS sync."""
        try:
            data = {k: asdict(v) for k, v in self.metrics.items()}
            with open(self.storage_path, "w") as f:
                json.dump(data, f, indent=2)

            # Schedule async GCS save
            if self.use_gcs:
                self._pending_save = True
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(self._save_to_gcs())
                except RuntimeError:
                    pass
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")

    async def _save_to_gcs(self):
        """Async save to GCS."""
        if not self._pending_save:
            return
        try:
            data = {k: asdict(v) for k, v in self.metrics.items()}
            await save_analytics_metrics(data)
            self._pending_save = False
        except Exception as e:
            logger.error(f"❌ GCS save failed: {e}")

    def record_trade(self, agent_id: str, pnl: float, capital_used: float = 1000.0):
        """Record a completed trade for an agent."""
        if agent_id not in self.metrics:
            self.metrics[agent_id] = AgentMetrics(agent_id=agent_id)

        m = self.metrics[agent_id]
        m.total_trades += 1
        m.total_pnl += pnl
        m.timestamps.append(time.time())

        # Update Equity Curve (simplified relative to initial capital)
        # Using a base of 0 for PnL steps
        current_equity = m.total_pnl
        m.equity_curve.append(current_equity)

        # Track Returns %
        if capital_used > 0:
            ret_pct = pnl / capital_used
            m.returns_history.append(ret_pct)

        # Win/Loss Stats
        if pnl > 0:
            m.wins += 1
        elif pnl < 0:
            m.losses += 1

        # Drawdown logic
        if current_equity > m.peak_equity:
            m.peak_equity = current_equity
        drawdown = m.peak_equity - current_equity
        if drawdown > m.max_drawdown:
            m.max_drawdown = drawdown

        # Ratios
        self._recalculate_ratios(m)

        m.last_updated = time.time()
        self.save_metrics()

    def _recalculate_ratios(self, m: AgentMetrics):
        """Calculate advanced metrics."""
        # Win Rate
        if m.total_trades > 0:
            m.win_rate = m.wins / m.total_trades

        # Profit Factor
        gross_loss = abs(
            sum([x for x in self._get_pnl_history(m) if x < 0]) or 1.0
        )  # Avoid div by zero
        gross_win = sum([x for x in self._get_pnl_history(m) if x > 0])
        m.profit_factor = gross_win / gross_loss if gross_loss > 0 else float("inf")

        # Returns for Sharpe/Sortino
        returns = self._get_returns_series(m)
        if len(returns) > 1:
            avg_return = sum(returns) / len(returns)
            std_dev = self._std_dev(returns)

            # Sharpe (Annualized approx assuming daily trades, simplified)
            if std_dev > 0:
                m.sharpe_ratio = (avg_return) / std_dev * math.sqrt(365)

            # Sortino
            negative_returns = [r for r in returns if r < 0]
            downside_dev = self._std_dev(negative_returns) if negative_returns else 1.0
            if downside_dev > 0:
                # Penalize only downside
                m.sortino_ratio = (avg_return) / downside_dev * math.sqrt(365)

        # Calmar Ratio: Annualized Return / Max Drawdown
        if m.max_drawdown > 0 and len(m.returns_history) > 0:
            annualized_return = sum(m.returns_history) * 365 / max(len(m.returns_history), 1)
            m.calmar_ratio = annualized_return / m.max_drawdown
        else:
            m.calmar_ratio = 0.0

        # Recovery Factor
        if m.max_drawdown > 0:
            m.recovery_factor = m.total_pnl / m.max_drawdown
        else:
            m.recovery_factor = 0.0

        # Expectancy
        total_pnl_history = self._get_pnl_history(m)
        wins = [x for x in total_pnl_history if x > 0]
        losses = [abs(x) for x in total_pnl_history if x < 0]

        m.average_win = sum(wins) / len(wins) if wins else 0.0
        m.average_loss = sum(losses) / len(losses) if losses else 0.0

        if m.total_trades > 0:
            # (Win Rate * Avg Win) - (Loss Rate * Avg Loss)
            win_rate = m.wins / m.total_trades
            loss_rate = m.losses / m.total_trades
            m.expectancy = (win_rate * m.average_win) - (loss_rate * m.average_loss)

        # Alpha/Beta (simplified - assumes SOL benchmark ~0.1% daily return, 2% std dev)
        # In production, this would fetch actual SOL price history
        benchmark_daily_return = 0.001  # Approx 36% annual
        benchmark_std = 0.02  # 2% daily std dev

        if len(returns) > 1:
            avg_return = sum(returns) / len(returns)
            agent_std = self._std_dev(returns)

            # Beta = Cov(agent, benchmark) / Var(benchmark)
            # Simplified: Beta = agent_std / benchmark_std (correlation assumption)
            m.beta = agent_std / benchmark_std if benchmark_std > 0 else 1.0

            # Alpha = Agent Return - (Risk-free + Beta * (Benchmark - Risk-free))
            risk_free_daily = self.risk_free_rate / 365
            m.alpha = (
                avg_return - risk_free_daily - m.beta * (benchmark_daily_return - risk_free_daily)
            ) * 365

    def _get_pnl_history(self, m: AgentMetrics) -> List[float]:
        """Reconstruct PnL steps from equity curve."""
        if not m.equity_curve:
            return []
        # First point is just the PnL of first trade
        history = [m.equity_curve[0]]
        for i in range(1, len(m.equity_curve)):
            history.append(m.equity_curve[i] - m.equity_curve[i - 1])
        return history

    def _get_returns_series(self, m: AgentMetrics) -> List[float]:
        """Get % returns per trade."""
        if m.returns_history:
            return m.returns_history
        # Fallback for old data: assume $1000 base
        base_capital = 1000.0
        return [pnl / base_capital for pnl in self._get_pnl_history(m)]

    def _std_dev(self, data: List[float]) -> float:
        if len(data) < 2:
            return 0.0
        avg = sum(data) / len(data)
        variance = sum((x - avg) ** 2 for x in data) / (len(data) - 1)
        return math.sqrt(variance)

    def get_top_performing_agent(self) -> str:
        """Return ID of agent with best Sharpe."""
        if not self.metrics:
            return "random"
        return max(self.metrics.items(), key=lambda x: x[1].sharpe_ratio)[0]
