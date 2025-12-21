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

# AI Prompt Engineering metrics
AI_PROMPT_GENERATION_DURATION_SECONDS = Histogram(
    "ai_prompt_generation_duration_seconds",
    "Time taken to generate AI prompts",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5],
)
AI_RESPONSE_PARSE_ERRORS_TOTAL = Counter(
    "ai_response_parse_errors_total",
    "Total number of AI response parsing errors",
    ["error_type"],
)
AI_RESPONSE_VALIDATION_ERRORS_TOTAL = Counter(
    "ai_response_validation_errors_total",
    "Total number of AI response validation errors",
    ["error_type"],
)
AI_PROMPT_VERSION_USAGE_TOTAL = Counter(
    "ai_prompt_version_usage_total",
    "Total usage of each prompt version",
    ["version"],
)
AI_CONFIDENCE_DISTRIBUTION = Histogram(
    "ai_confidence_distribution",
    "Distribution of AI confidence scores",
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

# Per-agent performance metrics
AGENT_INFERENCE_TIME = Histogram(
    "agent_inference_time_seconds",
    "Time taken for agent inference per agent",
    ["agent_id", "model"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)
AGENT_DECISION_LATENCY = Histogram(
    "agent_decision_latency_seconds",
    "Time from market data to trading decision per agent",
    ["agent_id"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)
AGENT_THROUGHPUT = Counter(
    "agent_throughput_total",
    "Total number of decisions made per agent",
    ["agent_id"],
)
AGENT_INFERENCE_TOKENS = Histogram(
    "agent_inference_tokens",
    "Number of tokens used per inference per agent",
    ["agent_id", "model", "type"],  # type: input, output
    buckets=[10, 50, 100, 250, 500, 1000, 2000, 5000],
)
AGENT_INFERENCE_COST = Histogram(
    "agent_inference_cost_usd",
    "Estimated cost per inference in USD per agent",
    ["agent_id", "model"],
    buckets=[0.0001, 0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05],
)
AGENT_ERROR_RATE = Counter(
    "agent_errors_total",
    "Total number of errors per agent",
    ["agent_id", "error_type"],
)
AGENT_SUCCESS_RATE = Gauge(
    "agent_success_rate",
    "Success rate of agent decisions (0-1)",
    ["agent_id"],
)
AGENT_AVG_CONFIDENCE = Gauge(
    "agent_avg_confidence",
    "Average confidence score of agent decisions",
    ["agent_id"],
)
AGENT_LAST_INFERENCE_TIME = Gauge(
    "agent_last_inference_time_seconds",
    "Last inference time for each agent",
    ["agent_id"],
)
AGENT_INFERENCE_COUNT = Counter(
    "agent_inference_count_total",
    "Total number of inferences per agent",
    ["agent_id", "model"],
)
AGENT_RESPONSE_TIME = Histogram(
    "agent_response_time_seconds",
    "Total response time from request to response per agent",
    ["agent_id"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0],
)
AGENT_MARKET_DATA_LATENCY = Histogram(
    "agent_market_data_latency_seconds",
    "Latency from market data timestamp to agent receipt",
    ["agent_id", "symbol"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0],
)
AGENT_TRADE_EXECUTION_LATENCY = Histogram(
    "agent_trade_execution_latency_seconds",
    "Time from decision to trade execution per agent",
    ["agent_id", "symbol"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)
AGENT_CIRCUIT_BREAKER_STATE = Gauge(
    "agent_circuit_breaker_state",
    "Circuit breaker state per agent (0=closed, 1=open, 2=half-open)",
    ["agent_id"],
)
AGENT_FALLBACK_USAGE = Counter(
    "agent_fallback_usage_total",
    "Total number of times fallback was used per agent",
    ["agent_id", "fallback_type"],
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

PAPER_TRADES_TOTAL = Counter(
    "paper_trades_total",
    "Total paper trading orders executed",
    ["symbol", "side"],
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

# Granular Transaction Metrics (User Request)
TOTAL_FEES_PAID = Counter(
    "total_fees_paid_usd",
    "Total trading fees paid in USD",
    ["platform", "symbol"],
)

SLIPPAGE_PERCENTAGE = Histogram(
    "slippage_percentage",
    "Realized slippage percentage per trade",
    ["symbol", "side"],
    buckets=[0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0],
)

AVERAGE_FEE_GAUGE = Gauge(
    "average_fee_usd",
    "Moving average of fees paid per trade",
)


# MCP metrics
MCP_MESSAGES_TOTAL = Counter(
    "mcp_messages_total",
    "Total number of MCP messages sent or received",
    ["message_type", "direction"],
)

# HFT-specific metrics
HFT_SIGNALS_GENERATED = Counter(
    "hft_signals_generated_total",
    "Total HFT signals generated by bots",
    ["bot_type", "strategy", "symbol"],
)

HFT_ORDER_EXECUTIONS = Counter(
    "hft_order_executions_total",
    "Total HFT order executions",
    ["bot_type", "symbol", "side", "status"],
)

HFT_LATENCY = Histogram(
    "hft_latency_seconds",
    "HFT decision to execution latency",
    ["bot_type", "operation"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25],
)

MARKET_MAKING_SPREAD = Gauge(
    "market_making_spread_bps",
    "Current market making spread in basis points",
    ["symbol", "bot_type"],
)

INVENTORY_SKEW_RATIO = Gauge(
    "inventory_skew_ratio",
    "Current inventory skew ratio (-1 to 1, where 0 is balanced)",
    ["symbol", "bot_type"],
)

CONSENSUS_DECISIONS = Counter(
    "consensus_decisions_total",
    "Total consensus decisions reached",
    ["decision_type", "confidence_range"],
)

STRATEGY_ADJUSTMENTS = Counter(
    "strategy_adjustments_total",
    "Total strategy parameter adjustments",
    ["component", "parameter", "reason"],
)

# Grok 4.1 Arbitration metrics
GROK_ARBITRATION_COUNT = Counter(
    "grok_arbitration_total", "Total number of Grok arbitrations", ["outcome"]
)

GROK_ARBITRATION_LATENCY = Histogram(
    "grok_arbitration_latency_seconds",
    "Grok API call latency",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0],
)

AGENT_CONFLICT_SCORE = Histogram(
    "agent_conflict_score",
    "Disagreement score between agents",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)
