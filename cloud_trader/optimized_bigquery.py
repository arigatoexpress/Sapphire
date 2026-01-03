"""Optimized BigQuery streaming with batching and compression."""

from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import lz4.frame  # type: ignore
from google.api_core import retry
from google.api_core.exceptions import ServiceUnavailable
from google.cloud import bigquery
from google.cloud.exceptions import NotFound

from .config import get_settings
from .optimized_config import get_optimized_settings

logger = logging.getLogger(__name__)


class OptimizedBigQueryStreamer:
    """Optimized BigQuery streaming with batching, compression, and intelligent partitioning."""

    def __init__(self, settings=None, optimized_settings=None):
        self._settings = settings or get_settings()
        self._optimized_settings = optimized_settings or get_optimized_settings()
        self._client: Optional[bigquery.Client] = None
        self._initialized = False
        self._project_id = self._settings.gcp_project_id
        self._dataset_id = "trading_analytics_optimized"

        # Optimization settings
        self._batch_size = self._optimized_settings.bigquery_batch_size
        self._compression = self._optimized_settings.bigquery_compression
        self._partitioning = self._optimized_settings.bigquery_partitioning

        # Performance optimizations
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bigquery")
        self._batch_queues: Dict[str, List[Tuple[datetime, Dict[str, Any]]]] = {}
        self._flush_tasks: Dict[str, asyncio.Task] = {}

        # Tables configuration with optimized schemas
        self._tables = {
            "trades_optimized": "trades_optimized_stream",
            "positions_optimized": "positions_optimized_stream",
            "market_data_optimized": "market_data_optimized_stream",
            "agent_performance_optimized": "agent_performance_optimized_stream",
            "liquidity_updates_optimized": "liquidity_updates_optimized_stream",
            "market_making_status_optimized": "market_making_status_optimized_stream",
            "portfolio_rebalances_optimized": "portfolio_rebalances_optimized_stream",
            "strategy_performance_optimized": "strategy_performance_optimized_stream",
            "trade_theses_optimized": "trade_theses_optimized_stream",
            "strategy_discussions_optimized": "strategy_discussions_optimized_stream",
            "portfolio_history_optimized": "portfolio_history_optimized_stream",
        }

    async def initialize(self) -> None:
        """Initialize optimized BigQuery client and ensure dataset/tables exist."""
        if not self._project_id:
            logger.warning("GCP project ID not configured, optimized BigQuery streaming disabled")
            return

        try:
            # Validate settings
            if not self._dataset_id or not self._tables:
                raise ValueError("Invalid BigQuery configuration")

            self._client = bigquery.Client(project=self._project_id)
            await self._ensure_dataset_and_tables()
            self._initialized = True

            # Start batch flushers with error handling
            try:
                asyncio.create_task(self._batch_flusher())
            except Exception as task_error:
                logger.error(f"Failed to start batch flusher: {task_error}")
                self._initialized = False
                return

            logger.info("✅ Optimized BigQuery streaming initialized")

        except Exception as e:
            logger.error(f"Failed to initialize optimized BigQuery: {e}")
            self._initialized = False
            # Clean up on failure
            if hasattr(self, "_client") and self._client:
                try:
                    self._client.close()
                except Exception:
                    pass
                self._client = None

    async def _ensure_dataset_and_tables(self) -> None:
        """Create optimized dataset and tables with compression and partitioning."""
        if not self._client:
            return

        # Create optimized dataset
        dataset_ref = bigquery.DatasetReference(self._project_id, self._dataset_id)
        try:
            dataset = self._client.get_dataset(dataset_ref)
            logger.info(f"Optimized BigQuery dataset {self._dataset_id} exists")
        except NotFound:
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = "US"
            dataset.description = "Optimized trading analytics with compression and partitioning"
            self._client.create_dataset(dataset)
            logger.info(f"Created optimized BigQuery dataset {self._dataset_id}")

        # Create optimized tables with compression and partitioning
        schemas = self._get_optimized_schemas()
        for table_name, schema in schemas.items():
            await self._ensure_optimized_table(table_name, schema)

    def _get_optimized_schemas(self) -> Dict[str, List[bigquery.SchemaField]]:
        """Get optimized schemas with compression-friendly data types."""
        return {
            "trades_optimized": [
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
            ],
            # Add other optimized schemas...
            "market_data_optimized": [
                bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
                bigquery.SchemaField("symbol", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("price", "FLOAT", mode="REQUIRED"),
                bigquery.SchemaField("volume_24h", "FLOAT", mode="NULLABLE"),
                bigquery.SchemaField("change_24h", "FLOAT", mode="NULLABLE"),
                bigquery.SchemaField("high_24h", "FLOAT", mode="NULLABLE"),
                bigquery.SchemaField("low_24h", "FLOAT", mode="NULLABLE"),
                bigquery.SchemaField("funding_rate", "FLOAT", mode="NULLABLE"),
                bigquery.SchemaField("open_interest", "FLOAT", mode="NULLABLE"),
                bigquery.SchemaField("compressed_data", "BYTES", mode="NULLABLE"),  # LZ4 compressed
            ],
            "portfolio_history_optimized": [
                bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
                bigquery.SchemaField("balance", "FLOAT", mode="REQUIRED"),
                bigquery.SchemaField("equity", "FLOAT", mode="REQUIRED"),
                bigquery.SchemaField("pnl_drawn_down", "FLOAT", mode="NULLABLE"),
                bigquery.SchemaField("metadata", "JSON", mode="NULLABLE"),
            ],
            "agent_performance_optimized": [
                bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
                bigquery.SchemaField("agent_id", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("total_trades", "INTEGER", mode="REQUIRED"),
                bigquery.SchemaField("win_rate", "FLOAT", mode="REQUIRED"),
                bigquery.SchemaField("pnl_total", "FLOAT", mode="REQUIRED"),
                bigquery.SchemaField("metadata", "JSON", mode="NULLABLE"),
            ],
        }

    async def _ensure_optimized_table(
        self, table_name: str, schema: List[bigquery.SchemaField]
    ) -> None:
        """Ensure optimized table exists with partitioning and clustering."""
        if not self._client:
            return

        table_id = self._tables[table_name]
        table_ref = bigquery.TableReference(
            bigquery.DatasetReference(self._project_id, self._dataset_id), table_id
        )

        try:
            self._client.get_table(table_ref)
            logger.debug(f"Optimized BigQuery table {table_id} exists")
        except NotFound:
            table = bigquery.Table(table_ref, schema=schema)
            table.description = f"Optimized streaming table for {table_name}"

            # Add partitioning and clustering for performance
            table.time_partitioning = bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="timestamp",
            )
            table.clustering_fields = ["symbol", "agent_id"]

            self._client.create_table(table)
            logger.info(f"Created optimized BigQuery table {table_id}")

    async def stream_optimized(
        self, table_name: str, timestamp: datetime, data: Dict[str, Any]
    ) -> bool:
        """Stream data with optimization (batching, compression, async)."""
        if not self.is_ready():
            return False

        if table_name not in self._batch_queues:
            self._batch_queues[table_name] = []

        # Add to batch queue
        self._batch_queues[table_name].append((timestamp, data))

        # Flush if batch is full
        if len(self._batch_queues[table_name]) >= self._batch_size:
            await self._flush_batch(table_name)

        return True

    async def _batch_flusher(self) -> None:
        """Background task to flush batches periodically."""
        consecutive_errors = 0
        max_consecutive_errors = 5

        while True:
            try:
                await asyncio.sleep(30)  # Flush every 30 seconds

                if not self.is_ready():
                    logger.warning("BigQuery client not ready, skipping batch flush")
                    continue

                tables_to_flush = list(self._batch_queues.keys())
                for table_name in tables_to_flush:
                    try:
                        if self._batch_queues.get(table_name):
                            await self._flush_batch(table_name)
                    except Exception as table_error:
                        logger.error(f"Failed to flush batch for table {table_name}: {table_error}")
                        # Continue with other tables

                # Reset error counter on successful iteration
                consecutive_errors = 0

            except Exception as e:
                consecutive_errors += 1
                logger.error(
                    f"Batch flusher error (attempt {consecutive_errors}/{max_consecutive_errors}): {e}"
                )

                if consecutive_errors >= max_consecutive_errors:
                    logger.critical("Batch flusher failed too many times, shutting down")
                    break

                # Exponential backoff
                await asyncio.sleep(min(5 * (2**consecutive_errors), 300))  # Max 5 minutes

    async def _flush_batch(self, table_name: str) -> None:
        """Flush batch to BigQuery with compression and optimization."""
        if not self._client or table_name not in self._batch_queues:
            return

        batch = self._batch_queues[table_name]
        if not batch:
            return

        self._batch_queues[table_name] = []

        try:
            # Prepare batch data
            rows = []
            for timestamp, data in batch:
                row = {"timestamp": timestamp, **data}

                # Compress large fields if enabled
                if self._compression == "LZ4" and "metadata" in row:
                    metadata_str = json.dumps(row["metadata"], default=str)
                    compressed = lz4.frame.compress(metadata_str.encode("utf-8"))
                    row["compressed_metadata"] = compressed
                    del row["metadata"]

                rows.append(row)

            # Insert batch
            table_id = self._tables[table_name]
            table_ref = f"{self._project_id}.{self._dataset_id}.{table_id}"

            errors = self._client.insert_rows_json(table_ref, rows, retry=retry.Retry())

            if errors:
                logger.warning(f"BigQuery batch insert errors for {table_name}: {errors}")
                # Re-queue failed items
                self._batch_queues[table_name].extend(batch[: len(errors)])
                return False

            logger.debug(f"Flushed {len(rows)} rows to {table_name}")
            return True

        except ServiceUnavailable:
            # Re-queue on service unavailable
            self._batch_queues[table_name].extend(batch)
            await asyncio.sleep(1)
            return False

        except Exception as e:
            logger.error(f"Failed to flush batch for {table_name}: {e}")
            # Re-queue on error
            self._batch_queues[table_name].extend(batch)
            return False

    async def stream_trade_optimized(self, **kwargs) -> bool:
        """Stream trade with optimization."""
        return await self.stream_optimized("trades_optimized", **kwargs)

    async def stream_market_data_optimized(self, **kwargs) -> bool:
        """Stream market data with compression."""
        return await self.stream_optimized("market_data_optimized", **kwargs)

    async def stream_portfolio_snapshot(self, **kwargs) -> bool:
        """Stream portfolio balance/equity snapshot."""
        return await self.stream_optimized("portfolio_history_optimized", **kwargs)

    async def stream_agent_metrics(self, **kwargs) -> bool:
        """Stream agent performance metrics."""
        return await self.stream_optimized("agent_performance_optimized", **kwargs)

    async def close(self) -> None:
        """Flush all pending batches and close."""
        # Flush all remaining batches
        for table_name in list(self._batch_queues.keys()):
            if self._batch_queues[table_name]:
                await self._flush_batch(table_name)

        if self._client:
            self._client.close()

        self._executor.shutdown(wait=True)
        self._initialized = False
        logger.info("Optimized BigQuery streaming closed")

    def is_ready(self) -> bool:
        """Check if optimized streamer is ready."""
        return self._initialized and self._client is not None


# Global optimized streamer instance
_optimized_streamer: Optional[OptimizedBigQueryStreamer] = None


async def get_optimized_bigquery_streamer() -> OptimizedBigQueryStreamer:
    """Get or create optimized BigQuery streamer instance."""
    global _optimized_streamer
    if _optimized_streamer is None:
        _optimized_streamer = OptimizedBigQueryStreamer()
        await _optimized_streamer.initialize()
    return _optimized_streamer


async def close_optimized_bigquery_streamer() -> None:
    """Close optimized BigQuery streamer."""
    global _optimized_streamer
    if _optimized_streamer:
        await _optimized_streamer.close()
        _optimized_streamer = None
