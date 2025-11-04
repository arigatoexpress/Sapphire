"""Prometheus metrics used across the Cloud Trader service."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram


# --- Trading loop level metrics -------------------------------------------------

TRADING_DECISIONS = Counter(
    "trading_decisions_total",
    "Total trading decisions emitted by the trading loop",
    labelnames=["bot_id", "symbol", "action"],
)

PORTFOLIO_BALANCE = Gauge(
    "trading_portfolio_balance_usd",
    "Current portfolio balance reported by the trading service",
)

PORTFOLIO_LEVERAGE = Gauge(
    "trading_portfolio_leverage_ratio",
    "Current portfolio leverage based on total exposure / balance",
)

POSITION_SIZE = Gauge(
    "trading_open_position_notional",
    "Latest notional exposure per symbol",
    labelnames=["symbol"],
)

RISK_LIMITS_BREACHED = Counter(
    "trading_risk_limits_breached_total",
    "Count of events where risk checks prevented an action",
    labelnames=["limit_type"],
)

RATE_LIMIT_EVENTS = Counter(
    "aster_rate_limit_events_total",
    "Occurrences of 429 responses from the Aster API",
    labelnames=["component", "endpoint"],
)


# --- External integration metrics ------------------------------------------------

ASTER_API_REQUESTS = Counter(
    "aster_api_requests_total",
    "Number of requests performed against the Aster REST API",
    labelnames=["component", "method", "endpoint", "status"],
)

ASTER_API_LATENCY = Histogram(
    "aster_api_request_duration_seconds",
    "Latency distribution for Aster REST API calls",
    labelnames=["component", "method", "endpoint"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)

REDIS_STREAM_FAILURES = Counter(
    "redis_stream_failures_total",
    "Telemetry publish attempts that failed due to Redis errors",
    labelnames=["stream"],
)

# --- Circuit breaker metrics ----------------------------------------------------

CIRCUIT_BREAKER_STATE = Gauge(
    "circuit_breaker_state",
    "Current state of circuit breaker (0=closed, 1=open, 2=half-open)",
    labelnames=["service"],
)

CIRCUIT_BREAKER_FAILURES = Counter(
    "circuit_breaker_failures_total",
    "Total number of failures that triggered circuit breaker",
    labelnames=["service"],
)

CIRCUIT_BREAKER_OPEN_DURATION = Histogram(
    "circuit_breaker_open_duration_seconds",
    "Duration circuit breaker remains open",
    labelnames=["service"],
    buckets=(10, 30, 60, 120, 300, 600),
)


# --- LLM related telemetry -------------------------------------------------------

LLM_CONFIDENCE = Histogram(
    "trading_llm_confidence",
    "Confidence distribution for LLM generated decisions",
    buckets=(0.1, 0.3, 0.5, 0.7, 0.9, 1.0),
)

LLM_INFERENCE_TIME = Histogram(
    "trading_llm_inference_duration_seconds",
    "Duration for external LLM inference calls",
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0),
)

# --- Enhanced instrumentation metrics -----------------------------------------

HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration",
    labelnames=["method", "endpoint", "status"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0),
)

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    labelnames=["method", "endpoint", "status"],
)

MARKET_FEED_LATENCY = Histogram(
    "market_feed_latency_seconds",
    "Market data feed fetch latency",
    labelnames=["symbol"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0),
)

MARKET_FEED_ERRORS = Counter(
    "market_feed_errors_total",
    "Market data feed errors",
    labelnames=["symbol", "error_type"],
)

POSITION_VERIFICATION_TIME = Histogram(
    "position_verification_duration_seconds",
    "Time taken to verify position after execution",
    labelnames=["symbol", "status"],
    buckets=(1.0, 2.0, 5.0, 10.0, 30.0),
)

TRADE_EXECUTION_TIME = Histogram(
    "trade_execution_duration_seconds",
    "Time from decision to verified execution",
    labelnames=["symbol", "side"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
)

MCP_MESSAGES_TOTAL = Counter(
    "mcp_messages_total",
    "Total MCP messages sent/received",
    labelnames=["message_type", "direction"],
)

CONSENSUS_VOTES_TOTAL = Counter(
    "consensus_votes_total",
    "Total consensus votes cast",
    labelnames=["proposal_id", "approved"],
)

CONSENSUS_REACHED = Counter(
    "consensus_reached_total",
    "Number of times consensus reached",
    labelnames=["approved"],
)


