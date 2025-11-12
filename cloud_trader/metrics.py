"""Prometheus metrics definitions."""
from prometheus_client import Counter, Gauge, Histogram

# General API metrics
ASTER_API_REQUESTS = Counter(
    "aster_api_requests_total",
    "Total requests to the Aster API",
    ["endpoint", "method"],
)

ASTER_API_LATENCY = Histogram(
    "aster_api_latency_seconds",
    "Latency of requests to the Aster API",
    ["endpoint", "method"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# Trading decision metrics
TRADING_DECISIONS = Counter(
    "trading_decisions_total",
    "Total trading decisions made by the bot",
    ["bot_id", "symbol", "action"],
)

# LLM-specific metrics
LLM_INFERENCE_TIME = Histogram(
    "llm_inference_time_seconds",
    "Time taken for LLM inference",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)
LLM_CONFIDENCE = Histogram(
    "llm_confidence",
    "Confidence score of LLM decisions",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

# Portfolio and risk metrics
PORTFOLIO_BALANCE = Gauge("portfolio_balance_usd", "Current portfolio balance in USD")
PORTFOLIO_LEVERAGE = Gauge("portfolio_leverage_ratio", "Current portfolio leverage ratio")
POSITION_SIZE = Gauge("position_size_usd", "Current position size in USD", ["symbol"])
RISK_LIMITS_BREACHED = Counter(
    "risk_limits_breached_total",
    "Total number of times risk limits were breached",
    ["limit_type"],
)
AGENT_MARGIN_REMAINING = Gauge(
    "agent_margin_remaining_usd",
    "Remaining margin allocation per agent",
    ["agent_id"],
)
AGENT_MARGIN_UTILIZATION = Gauge(
    "agent_margin_utilization_ratio",
    "Margin utilization ratio (0-1) per agent",
    ["agent_id"],
)
PORTFOLIO_DRAWDOWN = Gauge(
    "portfolio_drawdown_pct",
    "Current portfolio drawdown percentage",
)

TRADE_EXECUTION_SUCCESS = Counter(
    "trade_execution_success_total",
    "Successful trade executions routed to the venue",
    ["symbol", "mode", "source"],
)

TRADE_EXECUTION_FAILURE = Counter(
    "trade_execution_failure_total",
    "Failed trade executions and their reasons",
    ["symbol", "reason"],
)

# Snapshot and telemetry metrics
DASHBOARD_SNAPSHOT_TIME = Histogram(
    "dashboard_snapshot_duration_seconds",
    "Time taken to assemble the dashboard payload",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

PUBSUB_PUBLISH_FAILURES = Counter(
    "pubsub_publish_failures_total",
    "Number of Pub/Sub publish attempts that resulted in an error",
    ["topic"],
)

TELEGRAM_NOTIFICATIONS_SENT = Counter(
    "telegram_notifications_total",
    "Count of Telegram notifications attempted",
    ["category", "status"],
)

SLIPPAGE_VIOLATIONS = Counter(
    "slippage_violations_total",
    "Orders skipped because live prices exceeded the configured slippage tolerance",
    ["symbol"],
)

LAST_TRADE_UNREALIZED_PNL = Gauge(
    "last_trade_unrealized_pnl_usd",
    "Unrealized PnL of the most recently verified position",
    ["symbol"],
)

# System health metrics
RATE_LIMIT_EVENTS = Counter(
    "rate_limit_events_total",
    "Total number of rate limit events encountered",
    ["service"],
)

REDIS_STREAM_FAILURES = Counter(
    "redis_stream_failures_total",
    "Total failures to publish to Redis streams",
    ["stream_name"],
)

MARKET_FEED_LATENCY = Histogram(
    "market_feed_latency_seconds",
    "Latency of the market data feed",
    ["symbol"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

MARKET_FEED_ERRORS = Counter(
    "market_feed_errors_total",
    "Total errors from the market data feed",
    ["symbol", "error_type"],
)

# Order execution metrics
POSITION_VERIFICATION_TIME = Histogram(
    "position_verification_time_seconds",
    "Time taken to verify position execution",
    ["symbol", "status"],
    buckets=[1.0, 2.5, 5.0, 10.0, 20.0, 30.0],
)

TRADE_EXECUTION_TIME = Histogram(
    "trade_execution_time_seconds",
    "Time taken from order placement to confirmation",
    ["symbol", "side"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)


# MCP metrics
MCP_MESSAGES_TOTAL = Counter(
    "mcp_messages_total",
    "Total number of MCP messages sent or received",
    ["message_type", "direction"],
)


