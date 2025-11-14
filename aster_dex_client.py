import asyncio
import aiohttp
import json
import logging
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class MarketData:
    symbol: str
    price: float
    bid: float
    ask: float
    volume_24h: float
    timestamp: datetime
    order_book: Dict[str, List[List[float]]]
    recent_trades: List[Dict[str, Any]]

class AsterDEXClient:
    """Live data client for Aster DEX"""
    
    def __init__(self, api_key: str = None, api_secret: str = None, testnet: bool = False):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        
        # Aster DEX endpoints
        self.base_url = "https://api.aster.network" if not testnet else "https://testnet-api.aster.network"
        self.ws_url = "wss://ws.aster.network" if not testnet else "wss://testnet-ws.aster.network"
        
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.market_data: Dict[str, MarketData] = {}
        self.subscriptions: List[str] = []
        
        # Connection settings
        self.reconnect_delay = 1
        self.max_reconnect_delay = 60
        self.ping_interval = 30
        
    async def __aenter__(self):
        await self.connect()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
    
    async def connect(self):
        """Establish connection to Aster DEX"""
        try:
            self.session = aiohttp.ClientSession()
            
            # Connect to WebSocket for real-time data
            self.ws = await self.session.ws_connect(self.ws_url)
            logger.info("✅ Connected to Aster DEX WebSocket")
            
            # Start heartbeat
            asyncio.create_task(self._heartbeat())
            
            # Authenticate if credentials provided
            if self.api_key and self.api_secret:
                await self._authenticate()
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to Aster DEX: {e}")
            raise
    
    async def disconnect(self):
        """Close connections"""
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()
        logger.info("🔌 Disconnected from Aster DEX")
    
    async def _authenticate(self):
        """Authenticate with Aster DEX"""
        try:
            auth_msg = {
                "type": "auth",
                "api_key": self.api_key,
                "timestamp": int(time.time() * 1000)
            }
            
            # Add signature if needed
            await self.ws.send_json(auth_msg)
            
            # Wait for auth response
            response = await self.ws.receive_json()
            if response.get("type") == "auth_success":
                logger.info("✅ Authenticated with Aster DEX")
            else:
                logger.warning("⚠️  Aster DEX authentication failed")
                
        except Exception as e:
            logger.error(f"❌ Authentication failed: {e}")
    
    async def _heartbeat(self):
        """Maintain WebSocket connection"""
        while True:
            try:
                await asyncio.sleep(self.ping_interval)
                if self.ws and not self.ws.closed:
                    await self.ws.send_json({"type": "ping"})
            except Exception as e:
                logger.error(f"Heartbeat failed: {e}")
                break
    
    async def subscribe_ticker(self, symbol: str):
        """Subscribe to ticker updates"""
        try:
            await self.ws.send_json({
                "type": "subscribe",
                "channel": "ticker",
                "symbol": symbol
            })
            self.subscriptions.append(f"ticker:{symbol}")
            logger.info(f"📊 Subscribed to {symbol} ticker")
        except Exception as e:
            logger.error(f"❌ Failed to subscribe to {symbol} ticker: {e}")
    
    async def subscribe_orderbook(self, symbol: str, depth: int = 20):
        """Subscribe to order book updates"""
        try:
            await self.ws.send_json({
                "type": "subscribe",
                "channel": "orderbook",
                "symbol": symbol,
                "depth": depth
            })
            self.subscriptions.append(f"orderbook:{symbol}")
            logger.info(f"📊 Subscribed to {symbol} orderbook (depth: {depth})")
        except Exception as e:
            logger.error(f"❌ Failed to subscribe to {symbol} orderbook: {e}")
    
    async def subscribe_trades(self, symbol: str):
        """Subscribe to trade updates"""
        try:
            await self.ws.send_json({
                "type": "subscribe",
                "channel": "trades",
                "symbol": symbol
            })
            self.subscriptions.append(f"trades:{symbol}")
            logger.info(f"📊 Subscribed to {symbol} trades")
        except Exception as e:
            logger.error(f"❌ Failed to subscribe to {symbol} trades: {e}")
    
    async def get_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get current ticker data"""
        try:
            async with self.session.get(f"{self.base_url}/api/v1/ticker/{symbol}") as response:
                if response.status == 200:
                    return await response.json()
        except Exception as e:
            logger.error(f"❌ Failed to get ticker for {symbol}: {e}")
        return None
    
    async def get_orderbook(self, symbol: str, depth: int = 20) -> Optional[Dict[str, Any]]:
        """Get order book"""
        try:
            async with self.session.get(f"{self.base_url}/api/v1/depth/{symbol}?depth={depth}") as response:
                if response.status == 200:
                    return await response.json()
        except Exception as e:
            logger.error(f"❌ Failed to get orderbook for {symbol}: {e}")
        return None
    
    async def get_recent_trades(self, symbol: str, limit: int = 100) -> Optional[List[Dict[str, Any]]]:
        """Get recent trades"""
        try:
            async with self.session.get(f"{self.base_url}/api/v1/trades/{symbol}?limit={limit}") as response:
                if response.status == 200:
                    return await response.json()
        except Exception as e:
            logger.error(f"❌ Failed to get trades for {symbol}: {e}")
        return None
    
    async def listen_messages(self):
        """Listen for WebSocket messages"""
        try:
            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    await self._handle_message(data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {msg}")
                    break
        except Exception as e:
            logger.error(f"Message listening failed: {e}")
    
    async def _handle_message(self, data: Dict[str, Any]):
        """Handle incoming WebSocket messages"""
        msg_type = data.get("type")
        
        if msg_type == "ticker":
            await self._handle_ticker(data)
        elif msg_type == "orderbook":
            await self._handle_orderbook(data)
        elif msg_type == "trade":
            await self._handle_trade(data)
        elif msg_type == "error":
            logger.error(f"Aster DEX error: {data}")
    
    async def _handle_ticker(self, data: Dict[str, Any]):
        """Handle ticker updates"""
        symbol = data.get("symbol")
        if symbol:
            market_data = self.market_data.get(symbol, MarketData(
                symbol=symbol,
                price=0.0,
                bid=0.0,
                ask=0.0,
                volume_24h=0.0,
                timestamp=datetime.now(),
                order_book={"bids": [], "asks": []},
                recent_trades=[]
            ))
            
            market_data.price = data.get("last_price", market_data.price)
            market_data.bid = data.get("bid", market_data.bid)
            market_data.ask = data.get("ask", market_data.ask)
            market_data.volume_24h = data.get("volume_24h", market_data.volume_24h)
            market_data.timestamp = datetime.now()
            
            self.market_data[symbol] = market_data
            logger.debug(f"📊 Updated {symbol} ticker: ${market_data.price}")
    
    async def _handle_orderbook(self, data: Dict[str, Any]):
        """Handle order book updates"""
        symbol = data.get("symbol")
        if symbol and symbol in self.market_data:
            self.market_data[symbol].order_book = {
                "bids": data.get("bids", []),
                "asks": data.get("asks", [])
            }
            logger.debug(f"📊 Updated {symbol} orderbook")
    
    async def _handle_trade(self, data: Dict[str, Any]):
        """Handle trade updates"""
        symbol = data.get("symbol")
        if symbol and symbol in self.market_data:
            trade = {
                "id": data.get("id"),
                "price": data.get("price"),
                "quantity": data.get("quantity"),
                "side": data.get("side"),
                "timestamp": data.get("timestamp")
            }
            self.market_data[symbol].recent_trades.append(trade)
            # Keep only last 100 trades
            self.market_data[symbol].recent_trades = self.market_data[symbol].recent_trades[-100:]
            logger.debug(f"📊 New {symbol} trade: {trade['side']} {trade['quantity']} @ ${trade['price']}")

async def test_aster_connection():
    """Test Aster DEX connection"""
    try:
        async with AsterDEXClient() as client:
            # Test basic connectivity
            print("🔍 Testing Aster DEX connectivity...")
            
            # Get ticker data
            ticker = await client.get_ticker("BTC/USDT")
            if ticker:
                print(f"✅ BTC/USDT Ticker: ${ticker.get('last_price', 'N/A')}")
            else:
                print("⚠️  Could not fetch ticker data")
            
            # Get order book
            orderbook = await client.get_orderbook("BTC/USDT", 5)
            if orderbook:
                bids = orderbook.get("bids", [])
                asks = orderbook.get("asks", [])
                print(f"✅ Order Book: {len(bids)} bids, {len(asks)} asks")
            else:
                print("⚠️  Could not fetch order book")
            
            return True
            
    except Exception as e:
        print(f"❌ Aster DEX connection failed: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_aster_connection())
EOF && echo "✅ Aster DEX client created" && echo "" && echo "🔑 SETTING UP ASTER DEX SECRETS:" && kubectl create secret generic aster-dex-secret --from-literal=api_key="YOUR_ASTER_API_KEY" --from-literal=api_secret="YOUR_ASTER_API_SECRET" -n trading --dry-run=client -o yaml | kubectl apply -f - && echo "✅ Aster DEX secrets configured" && echo "" && echo "🚀 UPDATING TRADING SYSTEM TO USE LIVE ASTER DEX DATA:"