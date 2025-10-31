from __future__ import annotations

from datetime import timedelta

import pandas as pd
from feast import FeatureView, Field
from feast.data_source import FileSource
from feast.types import Float32

from .entities import market

raw_market = FileSource(
    path="data/raw/market.parquet",
    timestamp_field="event_time",
)

market_features_view = FeatureView(
    name="market_features",
    entities=[market],
    ttl=timedelta(hours=24),
    schema=[
        Field(name="rolling_volatility", dtype=Float32),
        Field(name="funding_rate", dtype=Float32),
        Field(name="sentiment_score", dtype=Float32),
    ],
    online=True,
    source=raw_market,
    tags={"owner": "quant-team"},
)


def load_demo_dataframe() -> pd.DataFrame:
    # Placeholder frame for local testing / `feast materialize`
    now = pd.Timestamp.utcnow().floor("s")
    return pd.DataFrame(
        {
            "symbol": ["BTCUSDT", "ETHUSDT"],
            "event_time": [now, now],
            "rolling_volatility": [0.42, 0.37],
            "funding_rate": [0.0008, -0.0004],
            "sentiment_score": [0.12, -0.08],
        }
    )


__all__ = ["market_features_view", "load_demo_dataframe"]

