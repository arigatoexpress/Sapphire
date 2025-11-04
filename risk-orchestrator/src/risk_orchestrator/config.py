from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    ASTER_API_KEY: str = Field(validation_alias=AliasChoices("ASTER_API_KEY"))
    ASTER_API_SECRET: str = Field(validation_alias=AliasChoices("ASTER_API_SECRET", "ASTER_SECRET_KEY"))
    REDIS_URL: str | None = Field(default=None, validation_alias=AliasChoices("REDIS_URL"))
    ENVIRONMENT: Literal["dev", "prod"] = "dev"
    MAX_DRAWDOWN_PCT: float = 10.0
    MAX_PER_TRADE_PCT: float = 4.0
    MIN_MARGIN_BUFFER_USDT: float = 100.0
    VOLATILITY_CAP_MULTIPLIER: float = 2.0
    PORTFOLIO_REFRESH_SECONDS: float = 300.0

settings = Settings()
