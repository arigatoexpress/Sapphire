"""Analytics and reporting module for performance attribution and risk-adjusted metrics."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .storage import TradingStorage

logger = logging.getLogger(__name__)


class TradingAnalytics:
    """Analytics engine for performance attribution and risk metrics."""
    
    def __init__(self, storage: TradingStorage):
        self._storage = storage
    
    async def calculate_sharpe_ratio(
        self,
        agent_id: str,
        returns: List[float],
        risk_free_rate: float = 0.0,
    ) -> Optional[float]:
        """Calculate Sharpe ratio from returns."""
        if not returns or len(returns) < 2:
            return None
        
        returns_array = np.array(returns)
        excess_returns = returns_array - risk_free_rate
        
        if np.std(excess_returns) == 0:
            return None
        
        sharpe = np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)  # Annualized
        return float(sharpe)
    
    async def calculate_max_drawdown(self, equity_curve: List[Tuple[datetime, float]]) -> float:
        """Calculate maximum drawdown from equity curve."""
        if not equity_curve or len(equity_curve) < 2:
            return 0.0
        
        equity_values = [e[1] for e in equity_curve]
        peak = equity_values[0]
        max_dd = 0.0
        
        for value in equity_values:
            if value > peak:
                peak = value
            dd = (peak - value) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        
        return max_dd
    
    async def calculate_sortino_ratio(
        self,
        returns: List[float],
        risk_free_rate: float = 0.0,
    ) -> Optional[float]:
        """Calculate Sortino ratio (downside deviation only)."""
        if not returns or len(returns) < 2:
            return None
        
        returns_array = np.array(returns)
        excess_returns = returns_array - risk_free_rate
        downside_returns = excess_returns[excess_returns < 0]
        
        if len(downside_returns) == 0 or np.std(downside_returns) == 0:
            return None
        
        sortino = np.mean(excess_returns) / np.std(downside_returns) * np.sqrt(252)
        return float(sortino)
    
    async def calculate_calmar_ratio(
        self,
        total_return: float,
        max_drawdown: float,
    ) -> Optional[float]:
        """Calculate Calmar ratio (return / max drawdown)."""
        if max_drawdown == 0:
            return None
        return total_return / max_drawdown
    
    async def performance_attribution(
        self,
        agent_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Calculate performance attribution by strategy, symbol, and time period."""
        if not self._storage:
            return {}
        
        try:
            trades = await self._storage.get_trades(
                agent_id=agent_id,
                start_date=start_date,
                end_date=end_date,
                limit=10000,
            )
            
            if not trades:
                return {
                    "total_pnl": 0.0,
                    "by_strategy": {},
                    "by_symbol": {},
                    "by_period": {},
                }
            
            df = pd.DataFrame(trades)
            
            # Calculate P&L by strategy
            by_strategy = {}
            if "strategy" in df.columns:
                for strategy, group in df.groupby("strategy"):
                    pnl = group["notional"].sum() * 0.001  # Simplified P&L
                    by_strategy[strategy] = {
                        "pnl": float(pnl),
                        "trades": len(group),
                        "avg_notional": float(group["notional"].mean()),
                    }
            
            # Calculate P&L by symbol
            by_symbol = {}
            if "symbol" in df.columns:
                for symbol, group in df.groupby("symbol"):
                    pnl = group["notional"].sum() * 0.001
                    by_symbol[symbol] = {
                        "pnl": float(pnl),
                        "trades": len(group),
                        "avg_notional": float(group["notional"].mean()),
                    }
            
            # Calculate P&L by time period (daily)
            by_period = {}
            if "timestamp" in df.columns:
                df["date"] = pd.to_datetime(df["timestamp"]).dt.date
                for date, group in df.groupby("date"):
                    pnl = group["notional"].sum() * 0.001
                    by_period[str(date)] = {
                        "pnl": float(pnl),
                        "trades": len(group),
                    }
            
            total_pnl = df["notional"].sum() * 0.001
            
            return {
                "total_pnl": float(total_pnl),
                "by_strategy": by_strategy,
                "by_symbol": by_symbol,
                "by_period": by_period,
                "total_trades": len(df),
            }
        except Exception as e:
            logger.error(f"Failed to calculate performance attribution: {e}")
            return {}
    
    async def risk_adjusted_metrics(
        self,
        agent_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Calculate risk-adjusted performance metrics."""
        if not self._storage:
            return {}
        
        try:
            performance = await self._storage.get_agent_performance(
                agent_id=agent_id,
                start_date=start_date,
                end_date=end_date,
                limit=1000,
            )
            
            if not performance:
                return {}
            
            df = pd.DataFrame(performance)
            
            if len(df) < 2:
                return {}
            
            # Calculate returns
            df = df.sort_values("timestamp")
            df["returns"] = df["equity"].pct_change()
            returns = df["returns"].dropna().tolist()
            
            # Calculate metrics
            sharpe = await self.calculate_sharpe_ratio(agent_id, returns)
            sortino = await self.calculate_sortino_ratio(returns)
            
            # Max drawdown
            equity_curve = [
                (datetime.fromisoformat(p["timestamp"]), p["equity"])
                for p in performance
            ]
            max_dd = await self.calculate_max_drawdown(equity_curve)
            
            # Total return
            initial_equity = df["equity"].iloc[0]
            final_equity = df["equity"].iloc[-1]
            total_return = (final_equity - initial_equity) / initial_equity if initial_equity > 0 else 0.0
            
            # Calmar ratio
            calmar = await self.calculate_calmar_ratio(total_return, max_dd)
            
            # Volatility (annualized)
            volatility = np.std(returns) * np.sqrt(252) if returns else 0.0
            
            return {
                "sharpe_ratio": sharpe,
                "sortino_ratio": sortino,
                "max_drawdown": max_dd,
                "calmar_ratio": calmar,
                "total_return": total_return,
                "volatility": float(volatility),
                "initial_equity": float(initial_equity),
                "final_equity": float(final_equity),
            }
        except Exception as e:
            logger.error(f"Failed to calculate risk-adjusted metrics: {e}")
            return {}
    
    async def generate_daily_report(
        self,
        agent_id: Optional[str] = None,
        date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Generate daily performance report."""
        if date is None:
            date = datetime.utcnow()
        
        start_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=1)
        
        report = {
            "date": start_date.isoformat(),
            "agents": {},
            "portfolio": {
                "daily_pnl": 0.0,
                "total_trades": 0,
                "win_rate": 0.0,
            },
        }
        
        # If agent_id specified, generate report for that agent only
        if agent_id:
            attribution = await self.performance_attribution(agent_id, start_date, end_date)
            metrics = await self.risk_adjusted_metrics(agent_id, start_date, end_date)
            
            report["agents"][agent_id] = {
                "attribution": attribution,
                "metrics": metrics,
            }
        else:
            # Generate report for all agents
            # This would require getting all agent IDs from storage
            # For now, return structure
            pass
        
        return report


# Global analytics instance
_analytics: Optional[TradingAnalytics] = None


def get_analytics(storage: TradingStorage) -> TradingAnalytics:
    """Get or create analytics instance."""
    global _analytics
    if _analytics is None:
        _analytics = TradingAnalytics(storage)
    return _analytics

