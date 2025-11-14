"""Configuration management for the lean cloud trader."""

from functools import lru_cache
from typing import List
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration derived from environment variables or .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_file_encoding="utf-8",
        populate_by_name=True,
    )

    # API credentials
    aster_api_key: str | None = Field(default=None, validation_alias="ASTER_API_KEY")
    aster_api_secret: str | None = Field(default=None, validation_alias="ASTER_SECRET_KEY")

    # Telegram notifications
    telegram_bot_token: str | None = Field(default=None, validation_alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str | None = Field(default=None, validation_alias="TELEGRAM_CHAT_ID")
    telegram_enable_market_observer: bool = Field(
        default=False,
        validation_alias="TELEGRAM_ENABLE_MARKET_OBSERVER",
        description="Enable periodic portfolio summaries via Telegram",
    )
    telegram_summary_interval_seconds: int = Field(
        default=14_400,
        ge=0,
        validation_alias="TELEGRAM_SUMMARY_INTERVAL_SECONDS",
        description="Minimum seconds between periodic Telegram summaries (0 disables)",
    )
    telegram_trade_cooldown_seconds: int = Field(
        default=180,
        ge=0,
        validation_alias="TELEGRAM_TRADE_COOLDOWN_SECONDS",
        description="Minimum seconds between trade notifications per symbol (0 disables throttling)",
    )

    # Administrative API security
    admin_api_token: str | None = Field(default=None, validation_alias="ADMIN_API_TOKEN")

    # API endpoints
    rest_base_url: str = Field(default="https://fapi.asterdex.com", validation_alias="ASTER_REST_URL")
    ws_base_url: str = Field(default="wss://fstream.asterdex.com", validation_alias="ASTER_WS_URL")

    @field_validator('rest_base_url', 'ws_base_url', 'model_endpoint', 'llm_endpoint')
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            parsed = urlparse(v)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError(f"Invalid URL format: {v}")
            return v
        except Exception:
            raise ValueError(f"Invalid URL: {v}")

    # Trading configuration
    symbols: List[str] = Field(
        default_factory=list  # Load all available symbols from exchange by default
    )
    decision_interval_seconds: int = Field(default=10, ge=5, le=300)  # Faster decisions for PvP trading
    max_position_risk: float = Field(default=0.15, gt=0, le=0.5)  # Higher risk per position for PvP
    max_drawdown: float = Field(default=0.25, gt=0, le=0.8)     # Higher drawdown tolerance for aggressive trading
    volatility_delever_threshold: float = Field(default=4.0, ge=0)
    auto_delever_factor: float = Field(default=0.5, gt=0, le=1)
    bandit_epsilon: float = Field(default=0.1, ge=0, le=1)
    trailing_stop_buffer: float = Field(default=0.01, gt=0, le=0.1)
    trailing_step: float = Field(default=0.002, gt=0, le=0.05)
    momentum_threshold: float = Field(default=0.35, gt=0, le=10, validation_alias="MOMENTUM_THRESHOLD")
    notional_fraction: float = Field(default=0.05, gt=0, le=0.5, validation_alias="NOTIONAL_FRACTION")

    # Deployment / observability
    log_level: str = Field(default="INFO")
    health_check_path: str = Field(default="/healthz")
    model_endpoint: str = Field(default="http://localhost:8000", validation_alias="MODEL_ENDPOINT")
    bot_id: str = Field(default="cloud_trader", validation_alias="BOT_ID")
    gcp_project_id: str | None = Field(default=None, validation_alias="GCP_PROJECT_ID")
    orchestrator_url: str | None = Field(default=None, validation_alias="ORCHESTRATOR_URL")
    mcp_url: str | None = Field(default=None, validation_alias="MCP_URL")
    mcp_session_id: str | None = Field(default=None, validation_alias="MCP_SESSION_ID")
    decisions_topic: str = Field(default="decisions")
    positions_topic: str = Field(default="positions")
    reasoning_topic: str = Field(default="reasoning")
    portfolio_poll_interval_seconds: int = Field(default=2, ge=1, le=60)
    kelly_fraction_cap: float = Field(default=0.5, gt=0, le=1)
    max_portfolio_leverage: float = Field(default=2.0, gt=0)
    expected_win_rate: float = Field(default=0.55, ge=0, le=1)
    reward_to_risk: float = Field(default=2.0, gt=0)
    max_slippage_bps: float = Field(
        default=25.0,
        ge=0,
        le=2000,
        description="Maximum tolerated slippage in basis points before skipping an order",
        validation_alias="MAX_SLIPPAGE_BPS",
    )

    # Agent configuration
    enabled_agents: List[str] = Field(
        default_factory=lambda: ["trend-momentum-agent", "strategy-optimization-agent", "financial-sentiment-agent", "market-prediction-agent", "volume-microstructure-agent", "vpin-hft"],
        validation_alias="ENABLED_AGENTS",
        description="List of 6 advanced AI agents for autonomous trading"
    )
    max_symbols_per_agent: int = Field(default=10, ge=1, le=50)
    agent_parallel_execution: bool = Field(default=True, validation_alias="AGENT_PARALLEL_EXECUTION")
    enable_profit_maximization: bool = Field(default=True, validation_alias="ENABLE_PROFIT_MAXIMIZATION")

    # Vertex AI Configuration
    enable_vertex_ai: bool = Field(default=True, validation_alias="ENABLE_VERTEX_AI")
    vertex_ai_region: str = Field(default="us-central1", validation_alias="VERTEX_AI_REGION")
    vertex_ai_project: str | None = Field(default=None, validation_alias="VERTEX_AI_PROJECT")

    # Agent-specific Vertex AI endpoints removed - now using unified Google Cloud AI

    # LLM Configuration (fallback)
    enable_llm_trading: bool = Field(default=False, validation_alias="ENABLE_LLM_TRADING")
    min_llm_confidence: float = Field(default=0.7, ge=0, le=1, description="Minimum confidence threshold for LLM decisions")
    llm_endpoint: str = Field(default="https://api.sapphiretrade.xyz", validation_alias="LLM_ENDPOINT")
    llm_timeout_seconds: int = Field(default=30, ge=5, le=120)

    # Open-source analyst endpoints removed - now using Google Cloud AI
    max_position_pct: float = Field(default=0.02, gt=0, le=0.1, description="Maximum position size as % of portfolio")
    min_position_size: float = Field(default=0.001, gt=0, description="Minimum viable position size")

    # Grok 4 Heavy orchestration
    grok4_api_key: str | None = Field(default=None, validation_alias="GROK4_API_KEY")
    grok4_endpoint: str | None = Field(
        default="https://api.x.ai/v1/chat/completions",
        validation_alias="GROK4_ENDPOINT",
        description="Grok 4 Heavy API endpoint (defaults to xAI API)",
    )

    # Gemini AI configuration
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")

    # Sui integrations
    sui_walrus_endpoint: str | None = Field(default=None, validation_alias="SUI_WALRUS_ENDPOINT")
    sui_walrus_key: str | None = Field(default=None, validation_alias="SUI_WALRUS_KEY")
    sui_seal_endpoint: str | None = Field(default=None, validation_alias="SUI_SEAL_ENDPOINT")
    sui_nautilus_endpoint: str | None = Field(default=None, validation_alias="SUI_NAUTILUS_ENDPOINT")

    # Enhanced risk controls
    risk_threshold: float = Field(default=0.3, ge=0, le=1, validation_alias="RISK_THRESHOLD", description="Minimum risk score threshold for thesis acceptance")
    atr_multiplier: float = Field(default=1.5, ge=0.5, le=3.0, validation_alias="ATR_MULTIPLIER", description="ATR multiplier for dynamic stop loss")
    trailing_stop_activation: float = Field(default=0.01, ge=0, le=0.05, validation_alias="TRAILING_STOP_ACTIVATION", description="Profit threshold to activate trailing stop")
    partial_close_targets: str = Field(default="0.01,0.02", validation_alias="PARTIAL_CLOSE_TARGETS", description="Comma-separated profit targets for partial closes")
    max_concurrent_positions: int = Field(default=40, ge=1, le=50, validation_alias="MAX_CONCURRENT_POSITIONS", description="Maximum concurrent positions allowed")

    # Compute optimization
    max_parallel_agents: int = Field(default=4, ge=1, le=10, validation_alias="MAX_PARALLEL_AGENTS", description="Maximum number of agents to query in parallel")
    agent_retry_attempts: int = Field(default=3, ge=0, le=5, validation_alias="AGENT_RETRY_ATTEMPTS", description="Number of retry attempts for agent queries")
    agent_cache_ttl_seconds: float = Field(default=10.0, ge=0, validation_alias="AGENT_CACHE_TTL_SECONDS", description="Cache TTL for agent responses in seconds")
    max_symbols_per_agent: int = Field(default=50, ge=1, le=200, validation_alias="MAX_SYMBOLS_PER_AGENT", description="Maximum symbols each agent can monitor")

    # Feature flags
    enable_paper_trading: bool = Field(default=True, validation_alias="ENABLE_PAPER_TRADING")
    enable_arbitrage: bool = Field(default=True, validation_alias="ENABLE_ARBITRAGE", description="Enable arbitrage scanning and execution")
    enable_rl_strategies: bool = Field(default=True, validation_alias="ENABLE_RL_STRATEGIES", description="Enable reinforcement learning strategies")
    
    # Redis cache
    redis_url: str | None = Field(default=None, validation_alias="REDIS_URL", description="Redis connection URL")
    cache_backend: str = Field(
        default="memory",
        validation_alias="CACHE_BACKEND",
        description="Cache backend to use ('memory' or 'redis')",
    )
    database_url: str | None = Field(default=None, validation_alias="DATABASE_URL", description="PostgreSQL/TimescaleDB connection URL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
