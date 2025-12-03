"""
Historical Data Backfill Service.
Fetches historical klines and stores them in the database.
"""
import asyncio
import os
from datetime import datetime, timedelta
import pandas as pd
import logging

# Assuming exchange client can be instantiated
from ..exchange import create_exchange_clients
from ..config import get_settings
from ..credentials import CredentialManager
from ..database import MarketCandle # If I had set up the DB session properly...
# Since DB setup is complex in this minimal env, we will focus on FETCHING 
# and validating, and maybe storing to CSV as a robust fallback/MVP.

class BackfillService:
    def __init__(self):
        settings = get_settings()
        creds = CredentialManager().get_credentials()
        self.client, _ = create_exchange_clients(settings, creds)
        self.symbols = [
            "BTCUSDT", "ETHUSDT", "SOLUSDT", "ZECUSDT", 
            "PENGUUSDT", "HYPEUSDT", "MONUSDT"
        ]
        
    async def backfill_history(self, days: int = 30):
        """Backfill historical data for key symbols."""
        print(f"⏳ Starting backfill for {len(self.symbols)} symbols ({days} days)...")
        
        for symbol in self.symbols:
            try:
                print(f"   Fetching {symbol}...")
                # Fetch 1h candles
                # API limit is usually 1000 candles per call.
                # 30 days * 24h = 720 candles. One call is enough.
                # If > 1000, we'd need pagination.
                
                klines = await self.client.get_historical_klines(symbol, "1h", limit=720)
                
                if not klines:
                    print(f"   ⚠️ No data for {symbol}")
                    continue
                    
                # Convert to DataFrame
                df = pd.DataFrame(klines, columns=[
                    "timestamp", "open", "high", "low", "close", "volume", 
                    "close_time", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"
                ])
                
                # Clean
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                numeric_cols = ["open", "high", "low", "close", "volume"]
                df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric)
                
                # Save to CSV (Persistence Layer MVP)
                os.makedirs("data/history", exist_ok=True)
                file_path = f"data/history/{symbol}_1h.csv"
                df.to_csv(file_path, index=False)
                
                print(f"   ✅ Saved {len(df)} candles to {file_path}")
                
                # Rate limit ease
                await asyncio.sleep(0.5)
                
            except Exception as e:
                print(f"   ❌ Error fetching {symbol}: {e}")
                
        print("✨ Backfill Complete.")

if __name__ == "__main__":
    service = BackfillService()
    asyncio.run(service.backfill_history())

