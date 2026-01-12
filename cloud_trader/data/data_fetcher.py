"""
Data Fetcher Module
Handles interactions with external exchanges via CCXT and WebSockets.
"""

import asyncio
import logging
import json
import threading
import time
from typing import Dict, List, Optional, Callable, Any
import os

import ccxt.async_support as ccxt  # Async CCXT
import websocket

logger = logging.getLogger(__name__)

class DataFetcher:
    """
    Fetches market data using CCXT (REST) and WebSocket connections.
    """

    def __init__(self, exchange_id: str = "binance", api_key: str = None, api_secret: str = None):
        self.exchange_id = exchange_id
        self.api_key = api_key or os.getenv("EXCHANGE_API_KEY")
        self.api_secret = api_secret or os.getenv("EXCHANGE_SECRET")
        
        # Initialize CCXT exchange
        self.exchange_class = getattr(ccxt, exchange_id)
        self.exchange = self.exchange_class({
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'enableRateLimit': True,
        })
        
        self.ws_thread: Optional[threading.Thread] = None
        self.ws_app: Optional[websocket.WebSocketApp] = None
        self.latest_prices: Dict[str, float] = {}
        self.price_callbacks: List[Callable[[str, float], None]] = []
        self.is_running = False

    async def close(self):
        """Close CCXT connection."""
        await self.exchange.close()
        if self.ws_app:
            self.ws_app.close()
        self.is_running = False

    async def fetch_historical_volume(self, symbol: str, days: int = 30) -> List[float]:
        """
        Fetch historical volume data to build a volume profile.
        Returns a list of hourly volumes for the last 'days'.
        """
        since = self.exchange.milliseconds() - (days * 24 * 60 * 60 * 1000)
        all_ohlcv = []
        
        try:
            # Fetch in chunks if needed, but for 30 days of hourly data (720 candles), one call usually suffices (limit usually 500-1000)
            # We'll fetch 1h candles
            limit = 1000
            current_since = since
            
            while True:
                ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe='1h', since=current_since, limit=limit)
                if not ohlcv:
                    break
                all_ohlcv.extend(ohlcv)
                current_since = ohlcv[-1][0] + (60 * 60 * 1000) # Next hour
                
                if current_since >= self.exchange.milliseconds():
                    break
                if len(ohlcv) < limit:
                    break
                    
            # Extract volume (index 5)
            # Provide a normalized 24-hour profile averaged over the days
            # Create buckets for 0-23 hours
            hourly_volumes = [0.0] * 24
            hourly_counts = [0] * 24
            
            for candle in all_ohlcv:
                timestamp = candle[0] / 1000
                hour = int(time.strftime('%H', time.gmtime(timestamp)))
                volume = candle[5]
                hourly_volumes[hour] += volume
                hourly_counts[hour] += 1
                
            # Average
            avg_hourly_volume = []
            for vol, count in zip(hourly_volumes, hourly_counts):
                avg_hourly_volume.append(vol / count if count > 0 else 0)
                
            # Normalize to sum to 1.0
            total = sum(avg_hourly_volume)
            if total > 0:
                return [v / total for v in avg_hourly_volume]
            return [1.0 / 24] * 24 # Fallback uniform

        except Exception as e:
            logger.error(f"Error fetching historical volume for {symbol}: {e}")
            # Fallback profile
            return [0.04] * 24

    async def fetch_current_price(self, symbol: str) -> float:
        """Fetch current price via REST (fallback)."""
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            return ticker['last']
        except Exception as e:
            logger.error(f"Error fetching price for {symbol}: {e}")
            return 0.0

    async def fetch_atr(self, symbol: str, period: int = 14) -> float:
        """Calculate ATR for volatility-based slippage."""
        try:
            # Fetch last N+1 candles for ATR
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe='1h', limit=period + 5)
            if not ohlcv:
                return 0.0
                
            # Simple TR calculation
            # TR = max(high-low, abs(high-prev_close), abs(low-prev_close))
            trs = []
            for i in range(1, len(ohlcv)):
                curr_high = ohlcv[i][2]
                curr_low = ohlcv[i][3]
                prev_close = ohlcv[i-1][4]
                
                tr = max(curr_high - curr_low, abs(curr_high - prev_close), abs(curr_low - prev_close))
                trs.append(tr)
                
            # SMA of TR
            if len(trs) >= period:
                atr = sum(trs[-period:]) / period
                # Return ATR as percentage of price
                current_price = ohlcv[-1][4]
                return (atr / current_price) if current_price > 0 else 0.0
            return 0.005 # Default 0.5%
            
        except Exception as e:
            logger.error(f"Error calculating ATR for {symbol}: {e}")
            return 0.005

    # --- WebSocket Handling ---

    def start_price_stream(self, symbols: List[str], callback: Callable[[str, float], None]):
        """
        Start WebSocket stream for live prices.
        Note: This implementation splits async context. 
        It uses a background thread for the blocking websocket-client run_forever.
        """
        self.price_callbacks.append(callback)
        if self.is_running:
            return

        self.is_running = True
        
        # Binance stream URL construction
        # stream name: <symbol>@trade
        streams = "/".join([f"{s.replace('/', '').lower()}@trade" for s in symbols])
        url = f"wss://stream.binance.com:9443/stream?streams={streams}"
        
        def on_message(ws, message):
            try:
                data = json.loads(message)
                # Format: {"stream": "btcusdt@trade", "data": {"s": "BTCUSDT", "p": "12345.67", ...}}
                if 'data' in data:
                    payload = data['data']
                    symbol = payload['s']
                    price = float(payload['p'])
                    self.latest_prices[symbol] = price
                    
                    # Notify callbacks
                    for cb in self.price_callbacks:
                        try:
                            cb(symbol, price)
                        except Exception as e:
                            logger.error(f"Callback error: {e}")
            except Exception as e:
                logger.error(f"WS Message Error: {e}")

        def on_error(ws, error):
            logger.error(f"WS Error: {error}")

        def on_close(ws, close_status_code, close_msg):
            logger.info("WS Closed")
            if self.is_running:
                logger.info("Reconnecting...")
                time.sleep(1)
                self.run_ws(url, on_message, on_error, on_close)

        self.run_ws(url, on_message, on_error, on_close)

    def run_ws(self, url, on_message, on_error, on_close):
        self.ws_app = websocket.WebSocketApp(
            url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        self.ws_thread = threading.Thread(target=self.ws_app.run_forever)
        self.ws_thread.daemon = True
        self.ws_thread.start()

    def get_latest_price(self, symbol: str) -> float:
        # Normalize symbol if needed (remote '/' for lookup)
        clean_symbol = symbol.replace('/', '').upper()
        return self.latest_prices.get(clean_symbol, 0.0)
