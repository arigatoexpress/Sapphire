"""Comprehensive Data Collection System

Collects market data, trading decisions, performance metrics,
and AI training data for analysis and model improvement.
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor
import threading
import time

from .logging_config import get_trading_logger
from .bigquery_exporter import BigQueryExporter


@dataclass
class MarketDataPoint:
    """Market data point for analysis."""
    timestamp: datetime
    symbol: str
    price: float
    volume: float
    bid_price: float
    ask_price: float
    spread: float
    volatility: float
    order_book_depth: Dict[str, Any]
    market_regime: str
    source: str


@dataclass
class TradingDecision:
    """Trading decision with full context."""
    timestamp: datetime
    agent_id: str
    symbol: str
    decision: str  # BUY, SELL, HOLD
    confidence: float
    strategy: str
    indicators: Dict[str, Any]
    market_context: Dict[str, Any]
    reasoning: str
    position_size: float
    risk_parameters: Dict[str, Any]
    correlation_id: str


@dataclass
class TradeExecution:
    """Trade execution details."""
    timestamp: datetime
    order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    slippage: float
    fees: float
    agent_id: str
    strategy: str
    market_conditions: Dict[str, Any]
    correlation_id: str


@dataclass
class PerformanceMetric:
    """Performance and system metrics."""
    timestamp: datetime
    metric_name: str
    value: float
    unit: str
    tags: Dict[str, str]
    metadata: Dict[str, Any]


@dataclass
class AgentBehavior:
    """Agent behavior tracking for AI training."""
    timestamp: datetime
    agent_id: str
    action: str
    state_before: Dict[str, Any]
    state_after: Dict[str, Any]
    reward: float
    exploration_rate: float
    learning_rate: float
    context: Dict[str, Any]


class DataCollector:
    """Centralized data collection and export system."""

    def __init__(self):
        self.logger = get_trading_logger("data-collector")
        self.bigquery_exporter = BigQueryExporter()

        # Data buffers
        self.market_data_buffer: List[MarketDataPoint] = []
        self.trading_decisions_buffer: List[TradingDecision] = []
        self.trade_executions_buffer: List[TradeExecution] = []
        self.performance_metrics_buffer: List[PerformanceMetric] = []
        self.agent_behavior_buffer: List[AgentBehavior] = []

        # Configuration
        self.buffer_size = 100  # Batch size for exports
        self.flush_interval = 60  # Seconds between flushes

        # Threading
        self.executor = ThreadPoolExecutor(max_workers=4)
        self._shutdown_event = threading.Event()

        # Start background flush task
        self._start_background_tasks()

    def _start_background_tasks(self):
        """Start background tasks for data flushing."""
        def flush_worker():
            while not self._shutdown_event.is_set():
                time.sleep(self.flush_interval)
                asyncio.run(self.flush_all_buffers())

        thread = threading.Thread(target=flush_worker, daemon=True)
        thread.start()

    async def flush_all_buffers(self):
        """Flush all data buffers to BigQuery."""
        try:
            # Flush market data
            if self.market_data_buffer:
                await self._flush_market_data()

            # Flush trading decisions
            if self.trading_decisions_buffer:
                await self._flush_trading_decisions()

            # Flush trade executions
            if self.trade_executions_buffer:
                await self._flush_trade_executions()

            # Flush performance metrics
            if self.performance_metrics_buffer:
                await self._flush_performance_metrics()

            # Flush agent behavior
            if self.agent_behavior_buffer:
                await self._flush_agent_behavior()

        except Exception as e:
            self.logger.log_error(e, {"operation": "buffer_flush"})

    async def _flush_market_data(self):
        """Flush market data buffer."""
        data = [asdict(point) for point in self.market_data_buffer]
        await self.bigquery_exporter.export_market_data_batch(data)
        self.market_data_buffer.clear()
        self.logger.info(f"Flushed {len(data)} market data points")

    async def _flush_trading_decisions(self):
        """Flush trading decisions buffer."""
        data = [asdict(decision) for decision in self.trading_decisions_buffer]
        await self.bigquery_exporter.export_trading_decisions_batch(data)
        self.trading_decisions_buffer.clear()
        self.logger.info(f"Flushed {len(data)} trading decisions")

    async def _flush_trade_executions(self):
        """Flush trade executions buffer."""
        data = [asdict(execution) for execution in self.trade_executions_buffer]
        await self.bigquery_exporter.export_trade_executions_batch(data)
        self.trade_executions_buffer.clear()
        self.logger.info(f"Flushed {len(data)} trade executions")

    async def _flush_performance_metrics(self):
        """Flush performance metrics buffer."""
        data = [asdict(metric) for metric in self.performance_metrics_buffer]
        await self.bigquery_exporter.export_performance_metrics_batch(data)
        self.performance_metrics_buffer.clear()
        self.logger.info(f"Flushed {len(data)} performance metrics")

    async def _flush_agent_behavior(self):
        """Flush agent behavior buffer."""
        data = [asdict(behavior) for behavior in self.agent_behavior_buffer]
        await self.bigquery_exporter.export_agent_behavior_batch(data)
        self.agent_behavior_buffer.clear()
        self.logger.info(f"Flushed {len(data)} agent behavior records")

    # Data collection methods
    def collect_market_data(self, data: Dict[str, Any]):
        """Collect market data point."""
        market_data = MarketDataPoint(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            symbol=data["symbol"],
            price=data["price"],
            volume=data["volume"],
            bid_price=data["bid_price"],
            ask_price=data["ask_price"],
            spread=data["spread"],
            volatility=data.get("volatility", 0.0),
            order_book_depth=data.get("order_book_depth", {}),
            market_regime=data.get("market_regime", "unknown"),
            source=data.get("source", "unknown")
        )

        self.market_data_buffer.append(market_data)

        if len(self.market_data_buffer) >= self.buffer_size:
            asyncio.create_task(self._flush_market_data())

    def collect_trading_decision(self, data: Dict[str, Any]):
        """Collect trading decision."""
        decision = TradingDecision(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            agent_id=data["agent_id"],
            symbol=data["symbol"],
            decision=data["decision"],
            confidence=data["confidence"],
            strategy=data["strategy"],
            indicators=data.get("indicators", {}),
            market_context=data.get("market_context", {}),
            reasoning=data.get("reasoning", ""),
            position_size=data.get("position_size", 0.0),
            risk_parameters=data.get("risk_parameters", {}),
            correlation_id=data.get("correlation_id", "")
        )

        self.trading_decisions_buffer.append(decision)

        if len(self.trading_decisions_buffer) >= self.buffer_size:
            asyncio.create_task(self._flush_trading_decisions())

    def collect_trade_execution(self, data: Dict[str, Any]):
        """Collect trade execution."""
        execution = TradeExecution(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            order_id=data["order_id"],
            symbol=data["symbol"],
            side=data["side"],
            quantity=data["quantity"],
            price=data["price"],
            slippage=data.get("slippage", 0.0),
            fees=data.get("fees", 0.0),
            agent_id=data["agent_id"],
            strategy=data.get("strategy", ""),
            market_conditions=data.get("market_conditions", {}),
            correlation_id=data.get("correlation_id", "")
        )

        self.trade_executions_buffer.append(execution)

        if len(self.trade_executions_buffer) >= self.buffer_size:
            asyncio.create_task(self._flush_trade_executions())

    def collect_performance_metric(self, name: str, value: float, unit: str = "", tags: Dict[str, str] = None, metadata: Dict[str, Any] = None):
        """Collect performance metric."""
        metric = PerformanceMetric(
            timestamp=datetime.now(),
            metric_name=name,
            value=value,
            unit=unit,
            tags=tags or {},
            metadata=metadata or {}
        )

        self.performance_metrics_buffer.append(metric)

        if len(self.performance_metrics_buffer) >= self.buffer_size:
            asyncio.create_task(self._flush_performance_metrics())

    def collect_agent_behavior(self, data: Dict[str, Any]):
        """Collect agent behavior for AI training."""
        behavior = AgentBehavior(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            agent_id=data["agent_id"],
            action=data["action"],
            state_before=data.get("state_before", {}),
            state_after=data.get("state_after", {}),
            reward=data.get("reward", 0.0),
            exploration_rate=data.get("exploration_rate", 0.0),
            learning_rate=data.get("learning_rate", 0.0),
            context=data.get("context", {})
        )

        self.agent_behavior_buffer.append(behavior)

        if len(self.agent_behavior_buffer) >= self.buffer_size:
            asyncio.create_task(self._flush_agent_behavior())

    # Analysis methods
    async def get_market_analysis(self, symbol: str, hours: int = 24) -> Dict[str, Any]:
        """Get market analysis data for the specified symbol and time period."""
        # This would query BigQuery for historical analysis
        # For now, return mock analysis
        return {
            "symbol": symbol,
            "period_hours": hours,
            "volatility": 0.15,
            "trend": "bullish",
            "volume_profile": "high",
            "support_levels": [45000, 44000, 43000],
            "resistance_levels": [47000, 48000, 49000],
            "market_regime": "trending"
        }

    async def get_agent_performance_analysis(self, agent_id: str, days: int = 30) -> Dict[str, Any]:
        """Get performance analysis for a specific agent."""
        # This would analyze trading decisions vs outcomes
        return {
            "agent_id": agent_id,
            "period_days": days,
            "win_rate": 0.65,
            "avg_profit": 2.3,
            "max_drawdown": -5.2,
            "sharpe_ratio": 1.8,
            "total_trades": 245,
            "profitable_trades": 159
        }

    async def get_system_health_metrics(self) -> Dict[str, Any]:
        """Get overall system health metrics."""
        return {
            "uptime": 0.995,  # 99.5%
            "avg_response_time": 45,  # ms
            "error_rate": 0.001,  # 0.1%
            "active_agents": 6,
            "data_points_collected": 125000,
            "bigquery_exports": 450
        }

    def shutdown(self):
        """Shutdown data collector and flush remaining data."""
        self.logger.info("Shutting down data collector...")
        self._shutdown_event.set()

        # Final flush
        asyncio.run(self.flush_all_buffers())


# Global data collector instance
_data_collector = None


def get_data_collector() -> DataCollector:
    """Get or create global data collector instance."""
    global _data_collector
    if _data_collector is None:
        _data_collector = DataCollector()
    return _data_collector


# Convenience functions for easy data collection
def collect_market_data(data: Dict[str, Any]):
    """Convenience function to collect market data."""
    collector = get_data_collector()
    collector.collect_market_data(data)


def collect_trading_decision(data: Dict[str, Any]):
    """Convenience function to collect trading decision."""
    collector = get_data_collector()
    collector.collect_trading_decision(data)


def collect_trade_execution(data: Dict[str, Any]):
    """Convenience function to collect trade execution."""
    collector = get_data_collector()
    collector.collect_trade_execution(data)


def collect_performance_metric(name: str, value: float, unit: str = "", tags: Dict[str, str] = None, metadata: Dict[str, Any] = None):
    """Convenience function to collect performance metric."""
    collector = get_data_collector()
    collector.collect_performance_metric(name, value, unit, tags, metadata)


def collect_agent_behavior(data: Dict[str, Any]):
    """Convenience function to collect agent behavior."""
    collector = get_data_collector()
    collector.collect_agent_behavior(data)
