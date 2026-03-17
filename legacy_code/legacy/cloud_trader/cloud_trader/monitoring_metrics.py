"""Comprehensive monitoring metrics for Sapphire AI."""

import logging

from prometheus_client import Counter, Gauge, Histogram, start_http_server

logger = logging.getLogger(__name__)


def init_metrics_server(port: int = 9090):
    """Initialize Prometheus metrics server."""
    try:
        start_http_server(port)
        logger.info(f"📊 Metrics server started on port {port}")
    except Exception as e:
        logger.warning(f"Failed to start metrics server: {e}")


# Trading execution metrics
TRADES_EXECUTED = Counter(
    "sapphire_trades_executed_total", "Total trades executed", ["agent_id", "symbol", "side"]
)

TRADE_PNL_USD = Gauge("sapphire_trade_pnl_usd", "P&L per trade in USD", ["agent_id"])

PORTFOLIO_VALUE_USD = Gauge("sapphire_portfolio_value_usd", "Total portfolio value in USD")

# Grok arbitration metrics
GROK_ARBITRATIONS_TOTAL = Counter(
    "sapphire_grok_arbitrations_total", "Total Grok arbitrations", ["outcome"]
)

GROK_LATENCY_SECONDS = Histogram(
    "sapphire_grok_latency_seconds",
    "Grok API call latency",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0],
)

# Agent collaboration metrics
AGENT_CONFLICT_SCORE = Histogram(
    "sapphire_agent_conflict_score",
    "Disagreement score between agents",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

AGENT_CONSENSUS_TIME_SECONDS = Histogram(
    "sapphire_agent_consensus_time_seconds",
    "Time to reach consensus among agents",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0],
)

# Paper vs Live trading
PAPER_PNL_USD = Gauge("sapphire_paper_trading_pnl_usd", "Paper trading P&L in USD")
LIVE_PNL_USD = Gauge("sapphire_live_trading_pnl_usd", "Live trading P&L in USD")

# Vertex AI performance
VERTEX_AI_INFERENCE_LATENCY = Histogram(
    "sapphire_vertex_ai_latency_seconds",
    "Vertex AI inference latency",
    ["agent_id", "model"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

VERTEX_AI_TOKEN_USAGE = Counter(
    "sapphire_vertex_ai_tokens_total",
    "Total Vertex AI tokens used",
    ["agent_id", "model", "type"],  # type: input/output
)

VERTEX_AI_COST_USD = Counter(
    "sapphire_vertex_ai_cost_usd", "Estimated Vertex AI cost in USD", ["agent_id", "model"]
)

# System health metrics
POD_STARTUP_TIME_SECONDS = Histogram(
    "sapphire_pod_startup_time_seconds",
    "Time from pod start to Ready status",
    buckets=[10, 30, 60, 120, 180, 300],
)

HEALTH_CHECK_FAILURES = Counter(
    "sapphire_health_check_failures_total", "Total health check failures", ["component"]
)
