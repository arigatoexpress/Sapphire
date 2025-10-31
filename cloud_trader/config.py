"""Configuration management for the lean cloud trader."""

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration derived from environment variables or .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_file_encoding="utf-8")

    # API credentials
    aster_api_key: str | None = Field(default=None, validation_alias="ASTER_API_KEY")
    aster_api_secret: str | None = Field(default=None, validation_alias="ASTER_SECRET_KEY")

    # API endpoints
    rest_base_url: str = Field(default="https://fapi.asterdex.com", validation_alias="ASTER_REST_URL")
    ws_base_url: str = Field(default="wss://fstream.asterdex.com", validation_alias="ASTER_WS_URL")

    # Trading configuration
    symbols: List[str] = Field(default_factory=lambda: ["BTCUSDT", "ETHUSDT", "SOLUSDT", "SUIUSDT"])
    decision_interval_seconds: int = Field(default=30, ge=5, le=300)
    max_concurrent_positions: int = Field(default=3, ge=1, le=10)
    max_position_risk: float = Field(default=0.10, gt=0, le=0.5)
    max_drawdown: float = Field(default=0.20, gt=0, le=0.8)
    volatility_delever_threshold: float = Field(default=4.0, ge=0)
    auto_delever_factor: float = Field(default=0.5, gt=0, le=1)
    bandit_epsilon: float = Field(default=0.1, ge=0, le=1)
    trailing_stop_buffer: float = Field(default=0.01, gt=0, le=0.1)
    trailing_step: float = Field(default=0.002, gt=0, le=0.05)
    momentum_threshold: float = Field(default=2.5, gt=0, le=10)
    notional_fraction: float = Field(default=0.05, gt=0, le=0.5)

    # Deployment / observability
    log_level: str = Field(default="INFO")
    health_check_path: str = Field(default="/healthz")
    model_endpoint: str = Field(default="http://localhost:8000", validation_alias="MODEL_ENDPOINT")
    bot_id: str = Field(default="cloud_trader", validation_alias="BOT_ID")
    redis_url: str | None = Field(default="redis://localhost:6379", validation_alias="REDIS_URL")
    orchestrator_url: str | None = Field(default=None, validation_alias="ORCHESTRATOR_URL")
    decisions_stream: str = Field(default="trader:decisions")
    positions_stream: str = Field(default="trader:positions")
    reasoning_stream: str = Field(default="trader:reasoning")
    redis_stream_maxlen: int = Field(default=2000, ge=100)
    pending_order_set: str = Field(default="trader:pending_orders")
    portfolio_poll_interval_seconds: int = Field(default=2, ge=1, le=60)
    kelly_fraction_cap: float = Field(default=0.5, gt=0, le=1)
    max_portfolio_leverage: float = Field(default=2.0, gt=0)
    expected_win_rate: float = Field(default=0.55, ge=0, le=1)
    reward_to_risk: float = Field(default=2.0, gt=0)

    # LLM Configuration
    enable_llm_trading: bool = Field(default=False, validation_alias="ENABLE_LLM_TRADING")
    min_llm_confidence: float = Field(default=0.7, ge=0, le=1, description="Minimum confidence threshold for LLM decisions")
    llm_endpoint: str = Field(default="https://deepseek-trader-880429861698.us-central1.run.app", validation_alias="LLM_ENDPOINT")
    llm_timeout_seconds: int = Field(default=30, ge=5, le=120)
    max_position_pct: float = Field(default=0.02, gt=0, le=0.1, description="Maximum position size as % of portfolio")
    min_position_size: float = Field(default=0.001, gt=0, description="Minimum viable position size")

    # Feature flags
    enable_paper_trading: bool = Field(default=True, validation_alias="ENABLE_PAPER_TRADING")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
