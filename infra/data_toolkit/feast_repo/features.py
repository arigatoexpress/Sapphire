from __future__ import annotations

from datetime import timedelta

import pandas as pd
from feast import FeatureView, Field
from feast.data_source import FileSource, PushSource
from feast.types import Float32, Int64, String

from .entities import market, agent_entity

# Market features
raw_market = FileSource(
    path="data/raw/market.parquet",
    timestamp_field="event_time",
)

market_features_view = FeatureView(
    name="market_features",
    entities=[market],
    ttl=timedelta(hours=24),
    schema=[
        Field(name="price", dtype=Float32),
        Field(name="volume_24h", dtype=Float32),
        Field(name="change_24h", dtype=Float32),
        Field(name="rolling_volatility", dtype=Float32),
        Field(name="funding_rate", dtype=Float32),
        Field(name="open_interest", dtype=Float32),
        Field(name="high_24h", dtype=Float32),
        Field(name="low_24h", dtype=Float32),
    ],
    online=True,
    source=raw_market,
    tags={"owner": "quant-team"},
)

# Agent performance features
agent_performance_source = FileSource(
    path="data/raw/agent_performance.parquet",
    timestamp_field="event_time",
)

agent_features_view = FeatureView(
    name="agent_features",
    entities=[agent_entity],
    ttl=timedelta(hours=48),
    schema=[
        Field(name="total_trades", dtype=Int64),
        Field(name="total_pnl", dtype=Float32),
        Field(name="exposure", dtype=Float32),
        Field(name="equity", dtype=Float32),
        Field(name="win_rate", dtype=Float32),
        Field(name="sharpe_ratio", dtype=Float32),
        Field(name="max_drawdown", dtype=Float32),
        Field(name="active_positions", dtype=Int64),
    ],
    online=True,
    source=agent_performance_source,
    tags={"owner": "quant-team"},
)

# Trading signal features
trading_signals_source = FileSource(
    path="data/raw/trading_signals.parquet",
    timestamp_field="event_time",
)

trading_signals_view = FeatureView(
    name="trading_signals",
    entities=[market],
    ttl=timedelta(hours=12),
    schema=[
        Field(name="strategy", dtype=String),
        Field(name="signal_direction", dtype=String),  # BUY, SELL, HOLD
        Field(name="confidence", dtype=Float32),
        Field(name="position_size", dtype=Float32),
        Field(name="kelly_fraction", dtype=Float32),
        Field(name="atr_stop_loss", dtype=Float32),
        Field(name="take_profit_target", dtype=Float32),
    ],
    online=True,
    source=trading_signals_source,
    tags={"owner": "quant-team"},
)


def load_demo_dataframe() -> pd.DataFrame:
    # Placeholder frame for local testing / `feast materialize`
    now = pd.Timestamp.utcnow().floor("s")
    return pd.DataFrame(
        {
            "symbol": ["BTCUSDT", "ETHUSDT"],
            "event_time": [now, now],
            "price": [50000.0, 3000.0],
            "volume_24h": [1000000.0, 500000.0],
            "change_24h": [2.5, -1.2],
            "rolling_volatility": [0.42, 0.37],
            "funding_rate": [0.0008, -0.0004],
            "open_interest": [10000000.0, 5000000.0],
            "high_24h": [51000.0, 3100.0],
            "low_24h": [49000.0, 2900.0],
        }
    )


__all__ = ["market_features_view", "agent_features_view", "trading_signals_view", "load_demo_dataframe"]

