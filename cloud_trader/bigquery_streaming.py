"""BigQuery streaming inserts for real-time analytics."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from google.cloud import bigquery
from google.cloud.exceptions import NotFound

from .config import Settings, get_settings

logger = logging.getLogger(__name__)


class BigQueryStreamer:
    """Stream trading data to BigQuery for analytics."""
    
    def __init__(self, settings: Optional[Settings] = None):
        self._settings = settings or get_settings()
        self._client: Optional[bigquery.Client] = None
        self._initialized = False
        self._project_id = self._settings.gcp_project_id
        self._dataset_id = "trading_analytics"
        self._tables = {
            "trades": "trades_stream",
            "positions": "positions_stream",
            "market_data": "market_data_stream",
            "agent_performance": "agent_performance_stream",
            "liquidity_updates": "liquidity_updates_stream",
            "market_making_status": "market_making_status_stream",
            "portfolio_rebalances": "portfolio_rebalances_stream",
            "strategy_performance": "strategy_performance_stream",
            "trade_theses": "trade_theses_stream",
            "strategy_discussions": "strategy_discussions_stream",
        }
    
    async def initialize(self) -> None:
        """Initialize BigQuery client and ensure dataset/tables exist."""
        if not self._project_id:
            logger.warning("GCP project ID not configured, BigQuery streaming disabled")
            return
        
        try:
            self._client = bigquery.Client(project=self._project_id)
            
            # Ensure dataset exists
            dataset_ref = bigquery.DatasetReference(self._project_id, self._dataset_id)
            try:
                self._client.get_dataset(dataset_ref)
                logger.info(f"BigQuery dataset {self._dataset_id} exists")
            except NotFound:
                dataset = bigquery.Dataset(dataset_ref)
                dataset.location = "US"
                dataset.description = "Real-time trading analytics data"
                self._client.create_dataset(dataset, exists_ok=True)
                logger.info(f"Created BigQuery dataset {self._dataset_id}")
            
            # Ensure tables exist
            await self._ensure_tables()
            
            self._initialized = True
            logger.info("BigQuery streaming initialized")
        except Exception as e:
            logger.error(f"Failed to initialize BigQuery streaming: {e}")
            self._client = None
    
    async def _ensure_tables(self) -> None:
        """Create tables if they don't exist."""
        if not self._client:
            return
        
        # Trades table schema
        trades_schema = [
            bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("symbol", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("side", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("price", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("quantity", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("notional", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("agent_id", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("agent_model", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("strategy", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("order_id", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("fee", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("slippage_bps", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("metadata", "JSON", mode="NULLABLE"),
        ]
        
        # Positions table schema
        positions_schema = [
            bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("symbol", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("agent_id", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("side", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("size", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("entry_price", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("current_price", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("notional", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("unrealized_pnl", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("unrealized_pnl_pct", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("leverage", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("status", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("metadata", "JSON", mode="NULLABLE"),
        ]
        
        # Market data table schema
        market_data_schema = [
            bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("symbol", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("price", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("volume_24h", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("change_24h", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("high_24h", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("low_24h", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("funding_rate", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("open_interest", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("metadata", "JSON", mode="NULLABLE"),
        ]
        
        # Agent performance table schema
        agent_performance_schema = [
            bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("agent_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("total_trades", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("total_pnl", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("exposure", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("equity", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("win_rate", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("sharpe_ratio", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("max_drawdown", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("active_positions", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("metadata", "JSON", mode="NULLABLE"),
        ]

        # Liquidity updates table schema
        liquidity_updates_schema = [
            bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("symbol", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("bid_orders", "JSON", mode="REQUIRED"),
            bigquery.SchemaField("ask_orders", "JSON", mode="REQUIRED"),
            bigquery.SchemaField("total_liquidity", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("imbalance_ratio", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("source", "STRING", mode="REQUIRED"),
        ]

        # Market making status table schema
        market_making_status_schema = [
            bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("symbol", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("active", "BOOLEAN", mode="REQUIRED"),
            bigquery.SchemaField("spread_bps", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("inventory_ratio", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("pnl_24h", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("order_count", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("last_update", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("issues", "JSON", mode="NULLABLE"),
        ]

        # Portfolio rebalances table schema
        portfolio_rebalances_schema = [
            bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("target_allocations", "JSON", mode="REQUIRED"),
            bigquery.SchemaField("current_allocations", "JSON", mode="REQUIRED"),
            bigquery.SchemaField("rebalance_trades", "JSON", mode="REQUIRED"),
            bigquery.SchemaField("reason", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("expected_impact", "JSON", mode="REQUIRED"),
        ]

        # Strategy performance table schema
        strategy_performance_schema = [
            bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("strategy_name", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("symbol", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("timeframe", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("total_trades", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("win_rate", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("profit_factor", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("max_drawdown", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("sharpe_ratio", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("sortino_ratio", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("calmar_ratio", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("period_start", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("period_end", "STRING", mode="REQUIRED"),
        ]

        # Trade theses table schema
        trade_theses_schema = [
            bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("symbol", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("agent_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("thesis", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("entry_point", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("stop_loss", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("take_profit", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("confidence", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("timeframe", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("rationale", "STRING", mode="REQUIRED"),
        ]

        # Strategy discussions table schema
        strategy_discussions_schema = [
            bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("topic", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("agent_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("content", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("discussion_type", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("related_symbols", "JSON", mode="NULLABLE"),
            bigquery.SchemaField("confidence", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("references", "JSON", mode="NULLABLE"),
        ]

        schemas = {
            "trades": trades_schema,
            "positions": positions_schema,
            "market_data": market_data_schema,
            "agent_performance": agent_performance_schema,
            "liquidity_updates": liquidity_updates_schema,
            "market_making_status": market_making_status_schema,
            "portfolio_rebalances": portfolio_rebalances_schema,
            "strategy_performance": strategy_performance_schema,
            "trade_theses": trade_theses_schema,
            "strategy_discussions": strategy_discussions_schema,
        }
        
        for table_name, schema in schemas.items():
            table_id = self._tables[table_name]
            table_ref = bigquery.TableReference(
                bigquery.DatasetReference(self._project_id, self._dataset_id),
                table_id
            )
            
            try:
                self._client.get_table(table_ref)
                logger.debug(f"BigQuery table {table_id} exists")
            except NotFound:
                table = bigquery.Table(table_ref, schema=schema)
                table.description = f"Streaming table for {table_name}"
                self._client.create_table(table)
                logger.info(f"Created BigQuery table {table_id}")
    
    async def stream_trade(
        self,
        timestamp: datetime,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        notional: float,
        agent_id: Optional[str] = None,
        agent_model: Optional[str] = None,
        strategy: Optional[str] = None,
        order_id: Optional[str] = None,
        fee: Optional[float] = None,
        slippage_bps: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Stream a trade to BigQuery."""
        if not self._initialized or not self._client:
            return False
        
        try:
            table_id = self._tables["trades"]
            table_ref = self._client.get_table(
                f"{self._project_id}.{self._dataset_id}.{table_id}"
            )
            
            row = {
                "timestamp": timestamp.isoformat(),
                "symbol": symbol.upper(),
                "side": side.upper(),
                "price": price,
                "quantity": quantity,
                "notional": notional,
                "agent_id": agent_id,
                "agent_model": agent_model,
                "strategy": strategy,
                "order_id": order_id,
                "fee": fee,
                "slippage_bps": slippage_bps,
                "metadata": json.dumps(metadata) if metadata else None,
            }
            
            errors = self._client.insert_rows_json(table_ref, [row])
            if errors:
                logger.warning(f"BigQuery insert errors: {errors}")
                return False
            
            return True
        except Exception as e:
            logger.warning(f"Failed to stream trade to BigQuery: {e}")
            return False
    
    async def stream_position(
        self,
        timestamp: datetime,
        symbol: str,
        agent_id: Optional[str],
        side: str,
        size: float,
        entry_price: float,
        current_price: float,
        notional: float,
        unrealized_pnl: float,
        unrealized_pnl_pct: float,
        leverage: Optional[float] = None,
        status: str = "open",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Stream a position snapshot to BigQuery."""
        if not self._initialized or not self._client:
            return False
        
        try:
            table_id = self._tables["positions"]
            table_ref = self._client.get_table(
                f"{self._project_id}.{self._dataset_id}.{table_id}"
            )
            
            row = {
                "timestamp": timestamp.isoformat(),
                "symbol": symbol.upper(),
                "agent_id": agent_id,
                "side": side.upper(),
                "size": size,
                "entry_price": entry_price,
                "current_price": current_price,
                "notional": notional,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": unrealized_pnl_pct,
                "leverage": leverage,
                "status": status,
                "metadata": json.dumps(metadata) if metadata else None,
            }
            
            errors = self._client.insert_rows_json(table_ref, [row])
            if errors:
                logger.warning(f"BigQuery insert errors: {errors}")
                return False
            
            return True
        except Exception as e:
            logger.warning(f"Failed to stream position to BigQuery: {e}")
            return False
    
    async def stream_market_data(
        self,
        timestamp: datetime,
        symbol: str,
        price: float,
        volume_24h: Optional[float] = None,
        change_24h: Optional[float] = None,
        high_24h: Optional[float] = None,
        low_24h: Optional[float] = None,
        funding_rate: Optional[float] = None,
        open_interest: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Stream market data to BigQuery."""
        if not self._initialized or not self._client:
            return False
        
        try:
            table_id = self._tables["market_data"]
            table_ref = self._client.get_table(
                f"{self._project_id}.{self._dataset_id}.{table_id}"
            )
            
            row = {
                "timestamp": timestamp.isoformat(),
                "symbol": symbol.upper(),
                "price": price,
                "volume_24h": volume_24h,
                "change_24h": change_24h,
                "high_24h": high_24h,
                "low_24h": low_24h,
                "funding_rate": funding_rate,
                "open_interest": open_interest,
                "metadata": json.dumps(metadata) if metadata else None,
            }
            
            errors = self._client.insert_rows_json(table_ref, [row])
            if errors:
                logger.warning(f"BigQuery insert errors: {errors}")
                return False
            
            return True
        except Exception as e:
            logger.warning(f"Failed to stream market data to BigQuery: {e}")
            return False
    
    async def stream_agent_performance(
        self,
        timestamp: datetime,
        agent_id: str,
        equity: float,
        total_trades: int = 0,
        total_pnl: float = 0.0,
        exposure: float = 0.0,
        win_rate: Optional[float] = None,
        sharpe_ratio: Optional[float] = None,
        max_drawdown: Optional[float] = None,
        active_positions: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Stream agent performance to BigQuery."""
        if not self._initialized or not self._client:
            return False
        
        try:
            table_id = self._tables["agent_performance"]
            table_ref = self._client.get_table(
                f"{self._project_id}.{self._dataset_id}.{table_id}"
            )
            
            row = {
                "timestamp": timestamp.isoformat(),
                "agent_id": agent_id,
                "total_trades": total_trades,
                "total_pnl": total_pnl,
                "exposure": exposure,
                "equity": equity,
                "win_rate": win_rate,
                "sharpe_ratio": sharpe_ratio,
                "max_drawdown": max_drawdown,
                "active_positions": active_positions,
                "metadata": json.dumps(metadata) if metadata else None,
            }
            
            errors = self._client.insert_rows_json(table_ref, [row])
            if errors:
                logger.warning(f"BigQuery insert errors: {errors}")
                return False
            
            return True
        except Exception as e:
            logger.warning(f"Failed to stream agent performance to BigQuery: {e}")
            return False

    async def stream_liquidity_update(
        self,
        timestamp: datetime,
        symbol: str,
        bid_orders: List[Dict[str, Any]],
        ask_orders: List[Dict[str, Any]],
        total_liquidity: float,
        imbalance_ratio: float,
        source: str,
    ) -> bool:
        """Stream liquidity update to BigQuery."""
        if not self.is_ready():
            return False

        row = {
            "timestamp": timestamp,
            "symbol": symbol,
            "bid_orders": json.dumps(bid_orders),
            "ask_orders": json.dumps(ask_orders),
            "total_liquidity": total_liquidity,
            "imbalance_ratio": imbalance_ratio,
            "source": source,
        }

        return await self._insert_row("liquidity_updates", row)

    async def stream_market_making_status(
        self,
        timestamp: datetime,
        symbol: str,
        active: bool,
        spread_bps: float,
        inventory_ratio: float,
        pnl_24h: float,
        order_count: int,
        last_update: str,
        issues: Optional[List[str]] = None,
    ) -> bool:
        """Stream market making status to BigQuery."""
        if not self.is_ready():
            return False

        row = {
            "timestamp": timestamp,
            "symbol": symbol,
            "active": active,
            "spread_bps": spread_bps,
            "inventory_ratio": inventory_ratio,
            "pnl_24h": pnl_24h,
            "order_count": order_count,
            "last_update": last_update,
            "issues": json.dumps(issues) if issues else None,
        }

        return await self._insert_row("market_making_status", row)

    async def stream_portfolio_rebalance(
        self,
        timestamp: datetime,
        target_allocations: Dict[str, float],
        current_allocations: Dict[str, float],
        rebalance_trades: List[Dict[str, Any]],
        reason: str,
        expected_impact: Dict[str, float],
    ) -> bool:
        """Stream portfolio rebalance to BigQuery."""
        if not self.is_ready():
            return False

        row = {
            "timestamp": timestamp,
            "target_allocations": json.dumps(target_allocations),
            "current_allocations": json.dumps(current_allocations),
            "rebalance_trades": json.dumps(rebalance_trades),
            "reason": reason,
            "expected_impact": json.dumps(expected_impact),
        }

        return await self._insert_row("portfolio_rebalances", row)

    async def stream_strategy_performance(
        self,
        timestamp: datetime,
        strategy_name: str,
        symbol: str,
        timeframe: str,
        total_trades: int,
        win_rate: float,
        profit_factor: float,
        max_drawdown: float,
        sharpe_ratio: Optional[float] = None,
        sortino_ratio: Optional[float] = None,
        calmar_ratio: Optional[float] = None,
        period_start: str = "",
        period_end: str = "",
    ) -> bool:
        """Stream strategy performance to BigQuery."""
        if not self.is_ready():
            return False

        row = {
            "timestamp": timestamp,
            "strategy_name": strategy_name,
            "symbol": symbol,
            "timeframe": timeframe,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "calmar_ratio": calmar_ratio,
            "period_start": period_start,
            "period_end": period_end,
        }

        return await self._insert_row("strategy_performance", row)

    async def stream_trade_thesis(
        self,
        timestamp: datetime,
        symbol: str,
        agent_id: str,
        thesis: str,
        entry_point: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        confidence: float = 0.5,
        timeframe: str = "",
        rationale: str = "",
    ) -> bool:
        """Stream trade thesis to BigQuery."""
        if not self.is_ready():
            return False

        row = {
            "timestamp": timestamp,
            "symbol": symbol,
            "agent_id": agent_id,
            "thesis": thesis,
            "entry_point": entry_point,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "confidence": confidence,
            "timeframe": timeframe,
            "rationale": rationale,
        }

        return await self._insert_row("trade_theses", row)

    async def stream_strategy_discussion(
        self,
        timestamp: datetime,
        topic: str,
        agent_id: str,
        content: str,
        discussion_type: str,
        related_symbols: Optional[List[str]] = None,
        confidence: Optional[float] = None,
        references: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Stream strategy discussion to BigQuery."""
        if not self.is_ready():
            return False

        row = {
            "timestamp": timestamp,
            "topic": topic,
            "agent_id": agent_id,
            "content": content,
            "discussion_type": discussion_type,
            "related_symbols": json.dumps(related_symbols) if related_symbols else None,
            "confidence": confidence,
            "references": json.dumps(references) if references else None,
        }

        return await self._insert_row("strategy_discussions", row)

    async def close(self) -> None:
        """Close BigQuery client."""
        if self._client:
            self._client.close()
        self._initialized = False
        logger.info("BigQuery streaming closed")

    def is_ready(self) -> bool:
        return self._initialized and self._client is not None


# Global streamer instance
_streamer: Optional[BigQueryStreamer] = None


async def get_bigquery_streamer() -> BigQueryStreamer:
    """Get or create BigQuery streamer instance."""
    global _streamer
    if _streamer is None:
        _streamer = BigQueryStreamer()
        await _streamer.initialize()
    return _streamer


async def close_bigquery_streamer() -> None:
    """Close BigQuery streamer connection."""
    global _streamer
    if _streamer:
        await _streamer.close()
        _streamer = None

