import logging
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PerformanceAnalyzer:
    """Analyzes trading performance metrics for agents and strategies."""

    def __init__(self, database_enabled: bool = False):
        self.database_enabled = database_enabled
        # In-memory fallback storage for metrics if DB unavailable
        self._daily_metrics: Dict[str, Any] = {}

    def calculate_metrics(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate core performance metrics from a list of trades."""
        if not trades:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "total_pnl": 0.0,
                "avg_trade_pnl": 0.0,
                "max_drawdown": 0.0,
                "sharpe_ratio": 0.0,
            }

        winning_trades = [t for t in trades if t.get("pnl", 0) > 0]
        losing_trades = [t for t in trades if t.get("pnl", 0) <= 0]

        total_trades = len(trades)
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0.0

        gross_profit = sum(t.get("pnl", 0) for t in winning_trades)
        gross_loss = abs(sum(t.get("pnl", 0) for t in losing_trades))

        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > 0
            else float("inf") if gross_profit > 0 else 0.0
        )
        total_pnl = sum(t.get("pnl", 0) for t in trades)

        # Calculate Max Drawdown
        # Assuming trades are sorted by time
        cumulative_pnl = [0.0]
        current_pnl = 0.0
        peak = 0.0
        max_dd = 0.0

        for t in trades:
            current_pnl += t.get("pnl", 0)
            cumulative_pnl.append(current_pnl)
            if current_pnl > peak:
                peak = current_pnl
            dd = peak - current_pnl
            if dd > max_dd:
                max_dd = dd

        # Calculate Sharpe Ratio (simplified annualization)
        returns = [t.get("pnl", 0) for t in trades]
        if len(returns) > 1:
            avg_return = sum(returns) / len(returns)
            variance = sum((x - avg_return) ** 2 for x in returns) / (len(returns) - 1)
            std_dev = math.sqrt(variance)
            # Annualize assuming ~6 trades/day * 365 (very rough approx for high freq)
            sharpe = (avg_return / std_dev) * math.sqrt(252 * 6) if std_dev > 0 else 0.0
        else:
            sharpe = 0.0

        return {
            "total_trades": total_trades,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "total_pnl": total_pnl,
            "avg_trade_pnl": total_pnl / total_trades if total_trades > 0 else 0.0,
            "max_drawdown": max_dd,
            "sharpe_ratio": sharpe,
        }

    async def analyze_agent_performance(
        self, agent_id: str, timeframe_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Analyze performance for a specific agent over a timeframe.
        Currently uses mock/in-memory data structure until DB is fully live.
        """
        # TODO: Wire up to actual database query when Cloud SQL is ready
        # For now, we return a structure that the system can consume
        return {
            "agent_id": agent_id,
            "period": f"{timeframe_hours}h",
            "metrics": self.calculate_metrics([]),  # Empty until DB connection
            "status": "pending_db_connection",
        }
