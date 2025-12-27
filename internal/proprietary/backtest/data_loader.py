"""Data loader for pulling historical market data from BigQuery for backtesting."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
from google.cloud import bigquery

from ..config import Settings, get_settings

logger = logging.getLogger(__name__)


class BacktestDataLoader:
    """Loads historical market data from BigQuery for backtesting."""

    def __init__(self, settings: Optional[Settings] = None):
        self._settings = settings or get_settings()
        self._bq_client: Optional[bigquery.Client] = None

        if self._settings.gcp_project_id:
            try:
                self._bq_client = bigquery.Client(project=self._settings.gcp_project_id)
                logger.info("BigQuery client initialized for backtest data loading")
            except Exception as e:
                logger.error(f"Failed to initialize BigQuery client: {e}")

    async def load_historical_trades(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """Load historical trades from BigQuery trades_stream table."""
        if not self._bq_client:
            logger.warning("BigQuery client not available, returning empty DataFrame")
            return pd.DataFrame()

        try:
            query = f"""
            SELECT
                TIMESTAMP(timestamp) as timestamp,
                symbol,
                side,
                price,
                quantity,
                notional,
                agent_id,
                agent_model,
                strategy,
                mode
            FROM `{self._settings.gcp_project_id}.trading_analytics.trades_stream`
            WHERE symbol = '{symbol.upper()}'
              AND TIMESTAMP(timestamp) >= TIMESTAMP('{start_date.isoformat()}')
              AND TIMESTAMP(timestamp) <= TIMESTAMP('{end_date.isoformat()}')
            ORDER BY timestamp ASC
            """

            query_job = self._bq_client.query(query)
            results = query_job.result()

            rows = []
            for row in results:
                rows.append(
                    {
                        "timestamp": row.timestamp,
                        "symbol": row.symbol,
                        "side": row.side,
                        "price": row.price,
                        "quantity": row.quantity,
                        "notional": row.notional,
                        "agent_id": row.agent_id,
                        "agent_model": row.agent_model,
                        "strategy": row.strategy,
                        "mode": row.mode,
                    }
                )

            if not rows:
                logger.warning(f"No historical trades found for {symbol} in date range")
                return pd.DataFrame()

            df = pd.DataFrame(rows)
            df.set_index("timestamp", inplace=True)
            logger.info(f"Loaded {len(df)} historical trades for {symbol}")
            return df

        except Exception as e:
            logger.error(f"Failed to load historical trades for {symbol}: {e}")
            return pd.DataFrame()

    async def load_market_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        interval: str = "1h",
    ) -> pd.DataFrame:
        """Load historical market data (OHLCV) from BigQuery or exchange API.

        Note: This is a placeholder - in production, you would:
        1. Query BigQuery market_data_stream table if available
        2. Fall back to exchange API historical candles
        3. Or use cached data from Redis
        """
        if not self._bq_client:
            logger.warning("BigQuery client not available, generating synthetic data")
            return self._generate_synthetic_data(symbol, start_date, end_date, interval)

        try:
            # Try to load from BigQuery market_data_stream table
            query = f"""
            SELECT
                TIMESTAMP(timestamp) as timestamp,
                symbol,
                open,
                high,
                low,
                close,
                volume
            FROM `{self._settings.gcp_project_id}.trading_analytics.market_data_stream`
            WHERE symbol = '{symbol.upper()}'
              AND TIMESTAMP(timestamp) >= TIMESTAMP('{start_date.isoformat()}')
              AND TIMESTAMP(timestamp) <= TIMESTAMP('{end_date.isoformat()}')
            ORDER BY timestamp ASC
            """

            query_job = self._bq_client.query(query)
            results = query_job.result()

            rows = []
            for row in results:
                rows.append(
                    {
                        "timestamp": row.timestamp,
                        "symbol": row.symbol,
                        "open": row.open,
                        "high": row.high,
                        "low": row.low,
                        "close": row.close,
                        "volume": row.volume,
                    }
                )

            if rows:
                df = pd.DataFrame(rows)
                df.set_index("timestamp", inplace=True)
                logger.info(f"Loaded {len(df)} market data points for {symbol}")
                return df
            else:
                # Fall back to synthetic data if no data in BigQuery
                logger.warning(f"No market data in BigQuery for {symbol}, generating synthetic")
                return self._generate_synthetic_data(symbol, start_date, end_date, interval)

        except Exception as e:
            logger.warning(
                f"Failed to load market data from BigQuery for {symbol}: {e}, generating synthetic"
            )
            return self._generate_synthetic_data(symbol, start_date, end_date, interval)

    def _generate_synthetic_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        interval: str,
    ) -> pd.DataFrame:
        """Generate synthetic OHLCV data for testing when real data unavailable."""
        import numpy as np

        periods = {
            "1h": timedelta(hours=1),
            "4h": timedelta(hours=4),
            "1d": timedelta(days=1),
        }

        period = periods.get(interval, timedelta(hours=1))

        timestamps = []
        current = start_date
        while current <= end_date:
            timestamps.append(current)
            current += period

        # Generate synthetic OHLCV data with realistic patterns
        np.random.seed(hash(symbol) % 1000)  # Consistent per symbol
        base_price = 100.0 * (1 + hash(symbol) % 10)

        data = []
        for i, ts in enumerate(timestamps):
            trend = 0.0001 * i  # Slight upward trend
            noise = np.random.normal(0, 0.02)  # 2% volatility

            close = base_price * (1 + trend + noise)
            open_price = close * (1 + np.random.normal(0, 0.005))
            high = max(open_price, close) * (1 + abs(np.random.normal(0, 0.003)))
            low = min(open_price, close) * (1 - abs(np.random.normal(0, 0.003)))
            volume = 1000000 * (1 + np.random.normal(0, 0.3))

            data.append(
                {
                    "timestamp": ts,
                    "symbol": symbol,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": max(volume, 0),
                }
            )

            base_price = close

        df = pd.DataFrame(data)
        df.set_index("timestamp", inplace=True)
        logger.info(f"Generated {len(df)} synthetic market data points for {symbol}")
        return df
