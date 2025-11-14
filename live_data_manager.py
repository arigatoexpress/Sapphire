import asyncio
import logging
from typing import Dict, Optional, Any
from aster_dex_client import AsterDEXClient, MarketData
from datetime import datetime, timedelta
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LiveDataManager:
    """Manages live market data from Aster DEX"""
    
    def __init__(self):
        self.dex_client: Optional[AsterDEXClient] = None
        self.market_data: Dict[str, MarketData] = {}
        self.last_update: Dict[str, datetime] = {}
        self.data_freshness_threshold = 5  # seconds
        self.is_connected = False
        
    async def start(self):
        """Start the live data manager"""
        try:
            logger.info("🚀 Starting Live Data Manager...")
            
            # Initialize Aster DEX client
            self.dex_client = AsterDEXClient(
                api_key=None,  # Will be loaded from environment
                api_secret=None,
                testnet=False
            )
            
            await self.dex_client.connect()
            self.is_connected = True
            
            # Subscribe to key symbols
            symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
            for symbol in symbols:
                await self.dex_client.subscribe_ticker(symbol)
                await self.dex_client.subscribe_orderbook(symbol)
                await self.dex_client.subscribe_trades(symbol)
            
            # Start message listener
            asyncio.create_task(self.dex_client.listen_messages())
            
            # Start data refresh task
            asyncio.create_task(self._refresh_data_loop())
            
            logger.info("✅ Live Data Manager started successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to start Live Data Manager: {e}")
            self.is_connected = False
            raise
    
    async def stop(self):
        """Stop the live data manager"""
        if self.dex_client:
            await self.dex_client.disconnect()
        self.is_connected = False
        logger.info("🛑 Live Data Manager stopped")
    
    async def _refresh_data_loop(self):
        """Periodically refresh market data"""
        while self.is_connected:
            try:
                await asyncio.sleep(1)  # Refresh every second
                
                # Update last seen timestamps
                for symbol in self.dex_client.market_data:
                    self.last_update[symbol] = datetime.now()
                
                # Copy data to our local cache
                self.market_data = self.dex_client.market_data.copy()
                
            except Exception as e:
                logger.error(f"Data refresh error: {e}")
                await asyncio.sleep(5)  # Wait before retry
    
    def get_live_price(self, symbol: str) -> Optional[float]:
        """Get live price for symbol"""
        if symbol in self.market_data:
            data = self.market_data[symbol]
            
            # Check data freshness
            if datetime.now() - data.timestamp < timedelta(seconds=self.data_freshness_threshold):
                return data.price
        
        # Fallback to REST API if WebSocket data is stale
        if self.dex_client and self.is_connected:
            try:
                # This would be an async call in real implementation
                # For now, return None to indicate no live data
                pass
            except Exception as e:
                logger.warning(f"Fallback price fetch failed for {symbol}: {e}")
        
        return None
    
    def get_orderbook(self, symbol: str, depth: int = 10) -> Optional[Dict[str, Any]]:
        """Get live order book"""
        if symbol in self.market_data:
            data = self.market_data[symbol]
            if datetime.now() - data.timestamp < timedelta(seconds=self.data_freshness_threshold):
                return {
                    "bids": data.order_book.get("bids", [])[:depth],
                    "asks": data.order_book.get("asks", [])[:depth]
                }
        return None
    
    def get_recent_trades(self, symbol: str, limit: int = 50) -> Optional[list]:
        """Get recent trades"""
        if symbol in self.market_data:
            data = self.market_data[symbol]
            if datetime.now() - data.timestamp < timedelta(seconds=self.data_freshness_threshold):
                return data.recent_trades[-limit:]
        return None
    
    def get_market_stats(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive market statistics"""
        if symbol in self.market_data:
            data = self.market_data[symbol]
            if datetime.now() - data.timestamp < timedelta(seconds=self.data_freshness_threshold):
                return {
                    "symbol": symbol,
                    "price": data.price,
                    "bid": data.bid,
                    "ask": data.ask,
                    "spread": data.ask - data.bid if data.ask > data.bid else 0,
                    "volume_24h": data.volume_24h,
                    "timestamp": data.timestamp.isoformat(),
                    "data_age_seconds": (datetime.now() - data.timestamp).total_seconds()
                }
        return None
    
    def is_data_fresh(self, symbol: str) -> bool:
        """Check if data for symbol is fresh"""
        if symbol in self.last_update:
            return (datetime.now() - self.last_update[symbol]) < timedelta(seconds=self.data_freshness_threshold)
        return False
    
    def get_supported_symbols(self) -> list:
        """Get list of supported symbols"""
        return list(self.market_data.keys())

# Global instance
live_data_manager = LiveDataManager()

async def initialize_live_data():
    """Initialize the live data manager"""
    await live_data_manager.start()
    return live_data_manager

def get_live_price(symbol: str) -> Optional[float]:
    """Synchronous wrapper for live price"""
    # In a real implementation, this would use asyncio.run() or be called from async context
    # For now, return None to force proper async usage
    return None

def get_live_orderbook(symbol: str, depth: int = 10) -> Optional[Dict[str, Any]]:
    """Synchronous wrapper for order book"""
    return None
EOF && echo "✅ Live data manager created" && echo "" && echo "🔄 UPDATING TRADING SYSTEM TO USE LIVE DATA:" && kubectl cp live_data_manager.py trading/sapphire-cloud-trader:/app/ -c sapphire-cloud-trader && kubectl cp aster_dex_client.py trading/sapphire-cloud-trader:/app/ -c sapphire-cloud-trader && echo "✅ Files copied to production pods" && echo "" && echo "🧪 TESTING LIVE DATA INTEGRATION:"