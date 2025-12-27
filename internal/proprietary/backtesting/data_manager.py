"""
Historical Data Management for Backtesting.
Fetches, cleans, and stores OHLCV data.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
import pandas as pd

from ..logger import get_logger

logger = get_logger(__name__)


class BacktestDataManager:
    def __init__(self, data_dir: str = "data/historical"):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)

    async def fetch_ohlcv(
        self, symbol: str, interval: str = "1h", limit: int = 1000
    ) -> pd.DataFrame:
        """
        Fetch historical data from CoinGecko (Public, No Auth, US Friendly).
        Limit is approximated by days.
        """
        # Symbol mapping (SOL/USD -> solana)
        # This is a simple mapping for the demo. Real system needs a proper map.
        cg_id = "solana" if "SOL" in symbol else "bitcoin"

        # CoinGecko granularity:
        # 1 day from current time = 5 minute interval data
        # 1 - 90 days from current time = hourly data
        # above 90 days from current time = daily data (00:00 UTC)

        days = "90"  # For hourly

        url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart"
        params = {"vs_currency": "usd", "days": days}

        logger.info(f"Fetching history for {cg_id} from CoinGecko...")

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, params=params, timeout=30.0)
                if resp.status_code == 429:
                    logger.warning("CoinGecko Rate Limit! Waiting...")
                    await asyncio.sleep(65)  # Free tier has 1 min limit
                    resp = await client.get(url, params=params)

                resp.raise_for_status()
                data = resp.json()

                prices = data.get("prices", [])
                total_volumes = data.get("total_volumes", [])

                # Prices is list of [timestamp, price]
                # Volumes is list of [timestamp, volume]

                df_price = pd.DataFrame(prices, columns=["timestamp", "close"])
                df_vol = pd.DataFrame(total_volumes, columns=["timestamp", "volume"])

                df = pd.merge(df_price, df_vol, on="timestamp")

                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                df.set_index("timestamp", inplace=True)

                # CoinGecko doesn't give High/Low/Open for hourly in this endpoint easily
                # We can approximate or use OHLC endpoint (limited days)
                # OHLC endpoint: /coins/{id}/ohlc?vs_currency=usd&days={1,7,14,30,90,180,365,max}

                # Let's try OHLC endpoint for better accuracy
                ohlc_url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/ohlc"
                ohlc_data = await client.get(
                    ohlc_url, params={"vs_currency": "usd", "days": "30"}
                )  # 30 days = hourly
                ohlc_data.raise_for_status()

                ohlc_list = ohlc_data.json()
                # [time, open, high, low, close]
                df_ohlc = pd.DataFrame(
                    ohlc_list, columns=["timestamp", "open", "high", "low", "close"]
                )
                df_ohlc["timestamp"] = pd.to_datetime(df_ohlc["timestamp"], unit="ms")
                df_ohlc.set_index("timestamp", inplace=True)

                # OHLC doesn't have volume, merge close volume approximation?
                # For strategy we need volume.
                # Let's reindex volume to ohlc

                # Resample volume to match OHLC index
                # This is tricky due to slight timestamp mismatches.
                # Simplification: Use OHLC, ignore volume for now or mock it if strategy needs it.
                # Strategies: Momentum (RSI MACD - no vol), MeanRev (BB - no vol), Trend (EMA - no vol).
                # We can skip volume for Phase 2 MVP.

                df_ohlc["volume"] = 1000000.0  # Mock volume to prevent NaN errors

                # Save to cache
                clean_symbol = symbol.replace("/", "_")
                cache_path = os.path.join(self.data_dir, f"{clean_symbol}_{interval}_cg.csv")
                df_ohlc.to_csv(cache_path)

                return df_ohlc

            except Exception as e:
                logger.error(f"Failed to fetch data for {symbol}: {e}")
                return self._load_from_cache(symbol, interval)

    def _load_from_cache(self, symbol: str, interval: str) -> Optional[pd.DataFrame]:
        cache_path = os.path.join(self.data_dir, f"{symbol}_{interval}.csv")
        if os.path.exists(cache_path):
            logger.info(f"Loading {symbol} from cache...")
            df = pd.read_csv(cache_path, index_col="timestamp", parse_dates=True)
            return df[["open", "high", "low", "close", "volume"]]
        return None

    def prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add technical indicators for strategy usage.
        """
        df = df.copy()

        # Trend
        df["sma_20"] = df["close"].rolling(20).mean()
        df["sma_50"] = df["close"].rolling(50).mean()
        df["ema_12"] = df["close"].ewm(span=12).mean()
        df["ema_26"] = df["close"].ewm(span=26).mean()

        # Momentum
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df["rsi"] = 100 - (100 / (1 + rs))

        df["macd"] = df["ema_12"] - df["ema_26"]
        df["macd_signal"] = df["macd"].ewm(span=9).mean()

        # Volatility
        df["std_20"] = df["close"].rolling(20).std()
        df["bb_upper"] = df["sma_20"] + (df["std_20"] * 2)
        df["bb_lower"] = df["sma_20"] - (df["std_20"] * 2)

        # Volume
        df["volume_sma"] = df["volume"].rolling(20).mean()

        # --- Advanced Features (Wyckoff / Liquidation Proxies) ---
        # Swing Lows (Potential Long Liquidation Levels / Wyckoff Springs)
        # Minimum of last 50 candles
        df["swing_low"] = df["low"].rolling(50).min()
        df["swing_high"] = df["high"].rolling(50).max()

        # Distances to swings
        df["dist_to_liq_low"] = (df["close"] - df["swing_low"]) / df["close"]
        df["dist_to_liq_high"] = (df["swing_high"] - df["close"]) / df["close"]

        # --- Fibonacci Retracements ---
        # Calculate Fib levels based on the Swing Range
        df["swing_range"] = df["swing_high"] - df["swing_low"]

        # Fib 0.618 (Golden Pocket from Bottom)
        df["fib_618_level"] = df["swing_low"] + (df["swing_range"] * 0.618)
        # Fib 0.5 (Midpoint)
        df["fib_050_level"] = df["swing_low"] + (df["swing_range"] * 0.5)
        # Fib 0.382
        df["fib_382_level"] = df["swing_low"] + (df["swing_range"] * 0.382)

        # Distance to Golden Pocket (0.618) - useful for "Dip Buying"
        df["dist_to_fib_618"] = (df["close"] - df["fib_618_level"]) / df["close"]

        return df.dropna()

    async def fetch_market_context(self) -> Dict[str, Any]:
        """
        Fetch Global Market Context (BTC Dominance, Total Market Cap).
        """
        try:
            # Using CoinGecko Global API
            url = "https://api.coingecko.com/api/v3/global"
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=10.0)
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    btc_d = data.get("market_cap_percentage", {}).get("btc", 0.0)
                    total_vol = data.get("total_volume", {}).get("usd", 0.0)

                    return {
                        "btc_dominance": btc_d,
                        "global_volume": total_vol,
                        "regime": (
                            "ALT_SEASON"
                            if btc_d < 40
                            else "BTC_SEASON" if btc_d > 60 else "NEUTRAL"
                        ),
                    }
        except Exception as e:
            logger.error(f"Failed to fetch market context: {e}")

        return {"btc_dominance": 50.0, "regime": "NEUTRAL"}  # Fallback

    async def fetch_higher_timeframe_trend(self, symbol: str) -> str:
        """
        Fetch 4h Trend for Context.
        Returns: BULLISH, BEARISH, NEUTRAL
        """
        try:
            # Fetch 4h candles approx (using 1h and resampling or just fetching)
            # CoinGecko granularity is limited. Let's fetch 1h and resample to 4h
            df_1h = await self.fetch_ohlcv(symbol, interval="1h", limit=100)
            if df_1h.empty:
                return "NEUTRAL"

            # Resample
            df_4h = df_1h.resample("4H").agg(
                {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
            )

            # Calculate SMA 50 on 4H
            df_4h["sma_50"] = df_4h["close"].rolling(50).mean()
            current = df_4h.iloc[-1]

            if current["close"] > current["sma_50"]:
                return "BULLISH"
            elif current["close"] < current["sma_50"]:
                return "BEARISH"

        except Exception as e:
            logger.error(f"HTF Trend Error: {e}")

        return "NEUTRAL"
