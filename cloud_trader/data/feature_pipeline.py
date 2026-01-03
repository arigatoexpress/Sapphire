from __future__ import annotations

import asyncio
import random
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

import numpy as np

try:
    import pandas as pd
except ImportError:
    pd = None
    print("⚠️ Pandas not found. FeaturePipeline will be disabled.")

from ..definitions import SYMPHONY_SYMBOLS
from ..logger import get_logger

logger = get_logger(__name__)


# Mocking Aster Client dependency to avoid circular imports if possible,
# but in real app we inject it.


class FeaturePipeline:
    def __init__(self, exchange_client):
        self.client = exchange_client
        self._analysis_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 60  # Cache analysis for 60 seconds

    async def fetch_candles(self, symbol: str, interval: str = "1h", limit: int = 100) -> Any:
        """Fetch OHLCV data and return as DataFrame."""
        if pd is None:
            return []

        try:
            klines = await self.client.get_historical_klines(symbol, interval, limit)
            if not klines:
                return pd.DataFrame()

            # Parse binance-like kline format: [time, open, high, low, close, volume, ...]
            df = pd.DataFrame(
                klines,
                columns=[
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "close_time",
                    "quote_volume",
                    "trades",
                    "taker_buy_base",
                    "taker_buy_quote",
                    "ignore",
                ],
            )

            # Convert types
            numeric_cols = ["open", "high", "low", "close", "volume"]
            df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric)
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

            return df
            return df
        except Exception as e:
            # Fallback for Symphony Symbols or missing data
            if symbol in SYMPHONY_SYMBOLS:
                # print(f"⚠️ Using synthetic data for {symbol}")
                return self._generate_synthetic_candles(symbol, limit)

            print(f"⚠️ Failed to fetch candles for {symbol}: {e}")
            return pd.DataFrame()

    def _generate_synthetic_candles(self, symbol: str, limit: int = 100) -> Any:
        """Generate realistic synthetic market data for testing/mocking."""
        if pd is None:
            return []

        # Seed based on time + symbol to make it deterministic but moving
        base_seed = int(time.time() / 60)  # Changes every minute
        np.random.seed(base_seed + hash(symbol) % 10000)

        # Base price (Monad/Memeish levels)
        base_price = 100.0
        if "MON" in symbol:
            base_price = 15.0
        elif "CHOG" in symbol:
            base_price = 0.420
        elif "DAC" in symbol:
            base_price = 0.05
        elif "BTC" in symbol:
            base_price = 95000.0
        elif "ETH" in symbol:
            base_price = 3500.0
        elif "SOL" in symbol:
            base_price = 180.0

        # Generate random walk
        prices = [base_price]
        volatility = 0.02  # 2% volatility

        data = []
        end_time = datetime.now()

        for i in range(limit):
            prev_close = prices[-1]
            change = np.random.normal(0, volatility)
            new_close = prev_close * (1 + change)
            prices.append(new_close)

            # Synthesize OHLC
            high = new_close * (1 + abs(np.random.normal(0, 0.005)))
            low = new_close * (1 - abs(np.random.normal(0, 0.005)))
            open_p = prev_close

            data.append(
                {
                    "timestamp": end_time - timedelta(hours=limit - i),
                    "open": open_p,
                    "high": max(high, open_p, new_close),
                    "low": min(low, open_p, new_close),
                    "close": new_close,
                    "volume": abs(np.random.normal(100000, 50000)),
                    "quote_volume": abs(np.random.normal(100000, 50000)) * new_close,
                }
            )

        df = pd.DataFrame(data)
        return df

    def calculate_indicators(self, df: Any, symbol: str = "Unknown") -> Any:
        """Calculate comprehensive technical indicators."""
        if pd is None or not isinstance(df, pd.DataFrame) or df.empty:
            return df
            
        print(f"📊 [TA] Starting {symbol} indicators...")
        import sys
        sys.stdout.flush()

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

        # MACD (12, 26, 9)
        exp12 = df["close"].ewm(span=12, adjust=False).mean()
        exp26 = df["close"].ewm(span=26, adjust=False).mean()
        df["MACD"] = exp12 - exp26
        df["MACD_signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
        df["MACD_hist"] = df["MACD"] - df["MACD_signal"]

        # Bollinger Bands (20, 2)
        df["BB_mid"] = df["close"].rolling(window=20).mean()
        df["BB_std"] = df["close"].rolling(window=20).std()
        df["BB_upper"] = df["BB_mid"] + (df["BB_std"] * 2)
        df["BB_lower"] = df["BB_mid"] - (df["BB_std"] * 2)

        # Stochastic Oscillator (14, 3, 3)
        # Low14 = lowest low in last 14 periods
        # High14 = highest high in last 14 periods
        low14 = df["low"].rolling(window=14).min()
        high14 = df["high"].rolling(window=14).max()
        df["STOCH_K"] = 100 * ((df["close"] - low14) / (high14 - low14))
        df["STOCH_D"] = df["STOCH_K"].rolling(window=3).mean()

        # CCI (20)
        # TP = (High + Low + Close) / 3
        tp = (df["high"] + df["low"] + df["close"]) / 3
        sma_tp = tp.rolling(window=20).mean()
        mean_dev = (tp - sma_tp).abs().rolling(window=20).mean()
        df["CCI"] = (tp - sma_tp) / (0.015 * mean_dev)

        # OBV
        # If Close > Prev Close: OBV = Prev OBV + Volume
        # If Close < Prev Close: OBV = Prev OBV - Volume
        # If Close = Prev Close: OBV = Prev OBV
        direction = np.where(df['close'] > df['close'].shift(1), 1, 
                             np.where(df['close'] < df['close'].shift(1), -1, 0))
        df['OBV'] = (direction * df['volume']).cumsum()

        # ADX (14) - Simplified Calculation
        # True Range is already calculated in ATR logic (ATRr_14 is SMA of TR)
        # Need Smoothed +DM and -DM
        plus_dm = df["high"] - df["high"].shift(1)
        minus_dm = df["low"].shift(1) - df["low"]
        
        # Determine if +DM or -DM
        plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0.0)
        minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0.0)
        
        # Smooth them (Wilder's smoothing) - using EWM as close approximation
        df["plus_dm_smooth"] = pd.Series(plus_dm).ewm(alpha=1/14, adjust=False).mean()
        df["minus_dm_smooth"] = pd.Series(minus_dm).ewm(alpha=1/14, adjust=False).mean()
        df["tr_smooth"] = true_range.ewm(alpha=1/14, adjust=False).mean() # Utilizing true_range from ATR block
        
        df["plus_di"] = 100 * (df["plus_dm_smooth"] / df["tr_smooth"])
        df["minus_di"] = 100 * (df["minus_dm_smooth"] / df["tr_smooth"])
        
        dx = 100 * abs(df["plus_di"] - df["minus_di"]) / (df["plus_di"] + df["minus_di"])
        df["ADX"] = dx.ewm(alpha=1/14, adjust=False).mean()

        # --- ADVANCED INDICATORS (User Request) ---

        # 1. Fibonacci Retracements (Lookback 100)
        # Dynamic calculation based on recent swing high/low
        window_size = min(len(df), 100)
        recent_data = df.iloc[-window_size:]
        swing_high = recent_data["high"].max()
        swing_low = recent_data["low"].min()
        diff = swing_high - swing_low
        
        # Calculate distance to nearest level for the latest candle
        if diff > 0:
            df["FIB_HIGH"] = swing_high
            df["FIB_LOW"] = swing_low
            # Levels relative to low
            df["FIB_0.236"] = swing_low + 0.236 * diff
            df["FIB_0.382"] = swing_low + 0.382 * diff
            df["FIB_0.5"] = swing_low + 0.5 * diff
            df["FIB_0.618"] = swing_low + 0.618 * diff
            df["FIB_0.786"] = swing_low + 0.786 * diff
        else:
             df["FIB_0.5"] = df["close"] # Fallback

        # 2. Wyckoff Phase Estimator (Heuristic)
        # Accumulation: Low volatility, Low-to-Med Volume, Price < EMA50 (or crossing), RSI low
        # Markup: Price > EMA50, RSI > 50, MACD > Signal
        # Distribution: High volatility, High Volume, Price > EMA50 but stalling
        # Markdown: Price < EMA50, RSI < 50, MACD < Signal
        
        # Calculate Volatility (ATR / Close)
        volatility = df["ATRr_14"] / df["close"]
        avg_volatility = volatility.rolling(window=50).mean()
        
        conditions = [
            (df["close"] > df["EMA_50"]) & (df["RSI_14"] > 50), # Markup
            (df["close"] < df["EMA_50"]) & (df["RSI_14"] < 50), # Markdown
            (df["close"] < df["EMA_50"]) & (df["RSI_14"] > 30) & (volatility < avg_volatility), # Accumulation
            (df["close"] > df["EMA_50"]) & (df["RSI_14"] > 70) & (volatility > avg_volatility)  # Distribution
        ]
        choices = ["MARKUP", "MARKDOWN", "ACCUMULATION", "DISTRIBUTION"]
        df["WYCKOFF_PHASE"] = np.select(conditions, choices, default="NEUTRAL")

        # 3. VSOP (Volume Sentiment Order Pressure) Index
        # Composite of Volume Trend (OBV slope), Price Trend (EMA) and basic Momentum
        # Normalized 0-100
        
        # OBV Slope (5 period)
        obv_slope = df["OBV"].diff(5)
        # Normalize OBV slope roughly (using stdev over 20 period)
        obv_norm = (obv_slope - obv_slope.rolling(20).mean()) / (obv_slope.rolling(20).std() + 1e-6)
        # Cap at -2/+2 and map to 0-100
        volume_score = 50 + (np.clip(obv_norm, -2, 2) * 25)
        
        # Trend Score (Price vs EMA20)
        trend_score = np.where(df["close"] > df["EMA_20"], 75, 25)
        
        # Combined VSOP
        df["VSOP"] = (volume_score + trend_score + df["RSI_14"]) / 3

        return df

    async def get_market_analysis(self, symbol: str) -> Dict[str, Any]:
        """Get full analysis snapshot for an agent (with caching)."""
        
        # Check cache
        now = time.time()
        if symbol in self._analysis_cache:
            cached_data, timestamp = self._analysis_cache[symbol]
            if now - timestamp < self._cache_ttl:
                print(f"💾 [PIPELINE] Cache HIT for {symbol}")
                import sys
                sys.stdout.flush()
                return cached_data
                
        # Cache miss - Parallel fetch for speed
        candles_task = self.fetch_candles(symbol, interval="1h", limit=100)
        orderbook_task = self.client.get_order_book(symbol, limit=20)
        
        print(f"🕯️ [PIPELINE] Gathering data for {symbol}...")
        results = await asyncio.gather(candles_task, orderbook_task, return_exceptions=True)
        print(f"📊 [PIPELINE] Gathered data for {symbol}")
        
        df, orderbook = results[0], results[1] # orderbook might be an exception? No, return_exceptions=True
        if isinstance(orderbook, Exception): orderbook = {} 

        # 1. Technical Analysis
        ta_data = {}
        if pd is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df = self.calculate_indicators(df, symbol)
            print(f"✅ [PIPELINE] Complete for {symbol}")
            import sys
            sys.stdout.flush()
            latest = df.iloc[-1]
            ta_data = {
                "price": float(latest["close"]),
                "rsi": float(latest.get("RSI_14", 50)),
                "atr": float(latest.get("ATRr_14", 0)),
                "ema_20": float(latest.get("EMA_20", 0)),
                "ema_50": float(latest.get("EMA_50", 0)),
                "trend": "BULLISH" if latest["close"] > latest.get("EMA_50", 0) else "BEARISH",
                "volatility_state": (
                    "HIGH" if latest.get("ATRr_14", 0) > (latest["close"] * 0.02) else "LOW"
                ),
                # New Indicators
                "macd_val": float(latest.get("MACD", 0)),
                "macd_signal": float(latest.get("MACD_signal", 0)),
                "macd_hist": float(latest.get("MACD_hist", 0)),
                "bb_upper": float(latest.get("BB_upper", 0)),
                "bb_mid": float(latest.get("BB_mid", 0)),
                "bb_lower": float(latest.get("BB_lower", 0)),
                "stoch_k": float(latest.get("STOCH_K", 50)),
                "stoch_d": float(latest.get("STOCH_D", 50)),
                "cci": float(latest.get("CCI", 0)),
                "adx": float(latest.get("ADX", 0)),
                "obv": float(latest.get("OBV", 0)),
                # Advanced
                "fib_0_5": float(latest.get("FIB_0.5", 0)),
                "fib_0_618": float(latest.get("FIB_0.618", 0)),
                "wyckoff_phase": str(latest.get("WYCKOFF_PHASE", "NEUTRAL")),
                "vsop": float(latest.get("VSOP", 50))
            }

        # 2. Order Book Analysis (Depth & Pressure)
        ob_data = {"bid_pressure": 0.0, "spread_pct": 0.0}
        if isinstance(orderbook, dict) and "bids" in orderbook:
            try:
                bids = [float(x[1]) for x in orderbook["bids"]]
                asks = [float(x[1]) for x in orderbook["asks"]]
                bid_vol = sum(bids)
                ask_vol = sum(asks)
                total_vol = bid_vol + ask_vol

                if total_vol > 0:
                    ob_data["bid_pressure"] = bid_vol / total_vol  # >0.5 means buying pressure

                best_bid = float(orderbook["bids"][0][0])
                best_ask = float(orderbook["asks"][0][0])
                if best_ask > 0:
                    ob_data["spread_pct"] = (best_ask - best_bid) / best_ask
            except Exception:
                pass

        result = {
            "symbol": symbol,
            "price": ta_data.get("close", 0) if ta_data else 0,  # Fallback
            **ta_data,
            **ob_data,
        }

        # Save to cache
        self._analysis_cache[symbol] = (result, time.time())
        logger.debug(f"💾 [PIPELINE] Cached TA result for {symbol}")
        
        return result
