from __future__ import annotations
import asyncio
from typing import List, Dict, Any
from datetime import datetime, timedelta

try:
    import pandas as pd
except ImportError:
    pd = None
    print("⚠️ Pandas not found. FeaturePipeline will be disabled.")

# Mocking Aster Client dependency to avoid circular imports if possible, 
# but in real app we inject it.

class FeaturePipeline:
    def __init__(self, exchange_client):
        self.client = exchange_client
        
    async def fetch_candles(self, symbol: str, interval: str = "1h", limit: int = 100) -> Any:
        """Fetch OHLCV data and return as DataFrame."""
        if pd is None:
            return []
            
        try:
            klines = await self.client.get_historical_klines(symbol, interval, limit)
            if not klines:
                return pd.DataFrame()
                
            # Parse binance-like kline format: [time, open, high, low, close, volume, ...]
            df = pd.DataFrame(klines, columns=[
                "timestamp", "open", "high", "low", "close", "volume", 
                "close_time", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"
            ])
            
            # Convert types
            numeric_cols = ["open", "high", "low", "close", "volume"]
            df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric)
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            
            return df
        except Exception as e:
            print(f"⚠️ Failed to fetch candles for {symbol}: {e}")
            return pd.DataFrame()

    def calculate_indicators(self, df: Any) -> Any:
        """Calculate comprehensive technical indicators."""
        if pd is None or not isinstance(df, pd.DataFrame) or df.empty:
            return df
            
        # Trend (Manual Calculation to bypass pandas-ta issue)
        df["EMA_20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["EMA_50"] = df["close"].ewm(span=50, adjust=False).mean()
        
        # RSI 14
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df["RSI_14"] = 100 - (100 / (1 + rs))
        
        # ATR 14
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        df["ATRr_14"] = true_range.rolling(window=14).mean()
        
        return df

    async def get_market_analysis(self, symbol: str) -> Dict[str, Any]:
        """Get full analysis snapshot for an agent."""
        df = await self.fetch_candles(symbol, interval="1h", limit=100)
        if pd is None or not isinstance(df, pd.DataFrame) or df.empty:
            return {}
            
        df = self.calculate_indicators(df)
        latest = df.iloc[-1]
        
        return {
            "symbol": symbol,
            "price": latest["close"],
            "rsi": latest.get("RSI_14"),
            # "macd": latest.get("MACD_12_26_9"), # Skipped for now
            "atr": latest.get("ATRr_14"),
            "ema_20": latest.get("EMA_20"),
            "ema_50": latest.get("EMA_50"),
            "trend": "BULLISH" if latest["close"] > latest.get("EMA_50", 0) else "BEARISH",
            "volatility_state": "HIGH" if latest.get("ATRr_14", 0) > (latest["close"] * 0.02) else "LOW"
        }
