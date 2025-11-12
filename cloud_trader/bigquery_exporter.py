"""BigQuery exporter for trading metrics and events."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from google.api_core.exceptions import GoogleAPIError
from google.cloud import bigquery

from .config import get_settings

logger = logging.getLogger(__name__)


class BigQueryExporter:
    """Exports trading metrics and events to BigQuery."""

    def __init__(self):
        self.settings = get_settings()
        self.client: Optional[bigquery.Client] = None
        self.dataset_id = "trading_metrics"
        self._initialize_client()

    def _initialize_client(self):
        """Initialize BigQuery client."""
        if self.settings.gcp_project_id:
            try:
                self.client = bigquery.Client(project=self.settings.gcp_project_id)
                self._ensure_dataset_exists()
                logger.info("BigQuery exporter initialized")
            except Exception as e:
                logger.error(f"Failed to initialize BigQuery client: {e}")
                self.client = None

    def _ensure_dataset_exists(self):
        """Ensure the trading metrics dataset exists."""
        if not self.client:
            return

        try:
            dataset_ref = self.client.dataset(self.dataset_id)
            self.client.get_dataset(dataset_ref)  # Check if exists
        except Exception:
            # Create dataset if it doesn't exist
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = "US"
            self.client.create_dataset(dataset)
            logger.info(f"Created BigQuery dataset: {self.dataset_id}")

    async def export_hft_signal(self, signal: Dict[str, Any]):
        """Export HFT signal to BigQuery."""
        await self._insert_row("hft_signals", {
            "timestamp": datetime.utcnow().isoformat(),
            "symbol": signal.get("symbol"),
            "side": signal.get("side"),
            "confidence": signal.get("confidence"),
            "notional": signal.get("notional"),
            "price": signal.get("price"),
            "rationale": signal.get("rationale"),
            "source": signal.get("source"),
            "strategy": signal.get("strategy"),
            "indicators": json.dumps(signal.get("indicators", {})),
        })

    async def export_order_execution(self, execution: Dict[str, Any]):
        """Export order execution to BigQuery."""
        await self._insert_row("order_executions", {
            "timestamp": execution.get("timestamp", datetime.utcnow().isoformat()),
            "symbol": execution.get("symbol"),
            "side": execution.get("side"),
            "quantity": execution.get("quantity"),
            "price": execution.get("price"),
            "order_id": execution.get("order_id"),
            "status": execution.get("status", "filled"),
            "source": execution.get("source"),
            "fees": execution.get("fees"),
        })

    async def export_risk_update(self, risk_data: Dict[str, Any]):
        """Export risk update to BigQuery."""
        await self._insert_row("risk_updates", {
            "timestamp": risk_data.get("timestamp", datetime.utcnow().isoformat()),
            "symbol": risk_data.get("symbol"),
            "portfolio_risk": risk_data.get("portfolio_risk"),
            "position_risk": json.dumps(risk_data.get("position_risk", {})),
            "drawdown": risk_data.get("drawdown"),
            "leverage": risk_data.get("leverage"),
            "alerts": json.dumps(risk_data.get("alerts", [])),
        })

    async def export_consensus_decision(self, consensus: Dict[str, Any]):
        """Export consensus decision to BigQuery."""
        await self._insert_row("consensus_decisions", {
            "timestamp": consensus.get("timestamp", datetime.utcnow().isoformat()),
            "symbol": consensus.get("symbol"),
            "decision": consensus.get("decision"),
            "confidence": consensus.get("confidence"),
            "signal_count": consensus.get("signal_count"),
            "rationale": consensus.get("rationale"),
        })

    async def export_strategy_adjustment(self, adjustment: Dict[str, Any]):
        """Export strategy adjustment to BigQuery."""
        await self._insert_row("strategy_adjustments", {
            "timestamp": adjustment.get("timestamp", datetime.utcnow().isoformat()),
            "strategy_name": adjustment.get("strategy_name"),
            "parameter": adjustment.get("parameter"),
            "old_value": json.dumps(adjustment.get("old_value")),
            "new_value": json.dumps(adjustment.get("new_value")),
            "reason": adjustment.get("reason"),
            "source": adjustment.get("source"),
        })

    async def export_market_data(self, data: Dict[str, Any]):
        """Export market data snapshot to BigQuery."""
        await self._insert_row("market_data", {
            "timestamp": data.get("timestamp", datetime.utcnow().isoformat()),
            "symbol": data.get("symbol"),
            "price": data.get("price"),
            "volume": data.get("volume"),
            "bid_price": data.get("bid_price"),
            "ask_price": data.get("ask_price"),
            "source": data.get("source"),
        })

    async def _insert_row(self, table_name: str, row_data: Dict[str, Any]):
        """Insert a row into BigQuery table."""
        if not self.client:
            return

        try:
            table_ref = self.client.dataset(self.dataset_id).table(table_name)
            table = self.client.get_table(table_ref)

            errors = self.client.insert_rows_json(table, [row_data])
            if errors:
                logger.error(f"BigQuery insert errors for {table_name}: {errors}")

        except Exception as e:
            logger.error(f"Failed to insert row into {table_name}: {e}")

    async def export_trade_thesis(self, thesis: Dict[str, Any]):
        """Export trade thesis to BigQuery."""
        await self._insert_row("trade_theses", {
            "timestamp": thesis.get("timestamp", datetime.utcnow().isoformat()),
            "agent": thesis.get("agent"),
            "symbol": thesis.get("symbol"),
            "thesis": thesis.get("thesis"),
            "entry_point": thesis.get("entry_point"),
            "take_profit": thesis.get("take_profit"),
            "stop_loss": thesis.get("stop_loss"),
            "risk_reward_ratio": thesis.get("risk_reward_ratio"),
            "timeframe": thesis.get("timeframe"),
            "conviction_level": thesis.get("conviction_level"),
            "market_context": json.dumps(thesis.get("market_context", {})),
        })

    async def export_strategy_discussion(self, discussion: Dict[str, Any]):
        """Export strategy discussion to BigQuery."""
        await self._insert_row("strategy_discussions", {
            "timestamp": discussion.get("timestamp", datetime.utcnow().isoformat()),
            "from_agent": discussion.get("from_agent"),
            "to_agent": discussion.get("to_agent"),
            "topic": discussion.get("topic"),
            "content": discussion.get("content"),
            "context": json.dumps(discussion.get("context", {})),
            "discussion_type": discussion.get("discussion_type", "question"),
        })

    def create_tables_if_not_exist(self):
        """Create BigQuery tables if they don't exist."""
        if not self.client:
            return

        tables = [
            ("hft_signals", """
                timestamp:TIMESTAMP,
                symbol:STRING,
                side:STRING,
                confidence:FLOAT64,
                notional:FLOAT64,
                price:FLOAT64,
                rationale:STRING,
                source:STRING,
                strategy:STRING,
                indicators:STRING
            """),
            ("order_executions", """
                timestamp:TIMESTAMP,
                symbol:STRING,
                side:STRING,
                quantity:FLOAT64,
                price:FLOAT64,
                order_id:STRING,
                status:STRING,
                source:STRING,
                fees:FLOAT64
            """),
            ("risk_updates", """
                timestamp:TIMESTAMP,
                symbol:STRING,
                portfolio_risk:FLOAT64,
                position_risk:STRING,
                drawdown:FLOAT64,
                leverage:FLOAT64,
                alerts:STRING
            """),
            ("consensus_decisions", """
                timestamp:TIMESTAMP,
                symbol:STRING,
                decision:STRING,
                confidence:FLOAT64,
                signal_count:INT64,
                rationale:STRING
            """),
            ("strategy_adjustments", """
                timestamp:TIMESTAMP,
                strategy_name:STRING,
                parameter:STRING,
                old_value:STRING,
                new_value:STRING,
                reason:STRING,
                source:STRING
            """),
            ("market_data", """
                timestamp:TIMESTAMP,
                symbol:STRING,
                price:FLOAT64,
                volume:FLOAT64,
                bid_price:FLOAT64,
                ask_price:FLOAT64,
                source:STRING
            """),
            ("trade_theses", """
                timestamp:TIMESTAMP,
                agent:STRING,
                symbol:STRING,
                thesis:STRING,
                entry_point:FLOAT64,
                take_profit:FLOAT64,
                stop_loss:FLOAT64,
                risk_reward_ratio:FLOAT64,
                timeframe:STRING,
                conviction_level:STRING,
                market_context:STRING
            """),
            ("strategy_discussions", """
                timestamp:TIMESTAMP,
                from_agent:STRING,
                to_agent:STRING,
                topic:STRING,
                content:STRING,
                context:STRING,
                discussion_type:STRING
            """),
        ]

        for table_name, schema_str in tables:
            try:
                table_ref = self.client.dataset(self.dataset_id).table(table_name)
                self.client.get_table(table_ref)
            except Exception:
                # Create table
                schema = []
                for field_def in schema_str.split(","):
                    field_def = field_def.strip()
                    if ":" in field_def:
                        name, type_ = field_def.split(":", 1)
                        schema.append(bigquery.SchemaField(name.strip(), type_.strip()))

                table = bigquery.Table(table_ref, schema=schema)
                self.client.create_table(table)
                logger.info(f"Created BigQuery table: {table_name}")


# Global exporter instance
_bigquery_exporter: Optional[BigQueryExporter] = None


def get_bigquery_exporter() -> BigQueryExporter:
    """Get or create global BigQuery exporter instance."""
    global _bigquery_exporter
    if _bigquery_exporter is None:
        _bigquery_exporter = BigQueryExporter()
    return _bigquery_exporter
