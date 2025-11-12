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
        
        schemas = {
            "trades": trades_schema,
            "positions": positions_schema,
            "market_data": market_data_schema,
            "agent_performance": agent_performance_schema,
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

