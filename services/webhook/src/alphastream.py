#!/usr/bin/env python3
"""
AlphaStream Integration
Connects to Alpha Vantage and other alpha-generating data sources
"""

import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import aiohttp

logger = logging.getLogger('alphastream')


@dataclass
class MarketData:
    """Market data snapshot"""
    symbol: str
    price: float
    change_24h: float
    volume_24h: float
    timestamp: str
    source: str = ""
    
    # Technical indicators
    rsi: float | None = None
    ema_20: float | None = None
    ema_50: float | None = None
    macd: float | None = None
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AlphaSignal:
    """Alpha trading signal"""
    symbol: str
    signal: str  # 'long', 'short', 'neutral'
    confidence: float  # 0.0 - 1.0
    source: str
    timestamp: str
    
    # Signal metadata
    expected_return: float | None = None
    timeframe: str = "1d"  # '1h', '4h', '1d', '1w'
    
    def to_dict(self) -> dict:
        return asdict(self)


class AlphaVantageClient:
    """Alpha Vantage API client"""
    
    BASE_URL = "https://www.alphavantage.co/query"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session: aiohttp.ClientSession | None = None
        self.rate_limit_delay = 12  # Free tier: 5 calls per minute
        
    async def connect(self):
        """Initialize session"""
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(timeout=timeout)
        
    async def disconnect(self):
        """Close session"""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def _call_api(self, params: dict) -> dict:
        """Make API call with rate limiting"""
        if not self.session:
            return {'error': 'Not connected'}
        
        params['apikey'] = self.api_key
        
        try:
            async with self.session.get(self.BASE_URL, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Check for error messages
                    if 'Error Message' in data:
                        return {'error': data['Error Message']}
                    if 'Note' in data:  # Rate limit message
                        return {'error': data['Note']}
                    return data
                else:
                    return {'error': f'HTTP {resp.status}'}
        except Exception as e:
            logger.error(f"API error: {e}")
            return {'error': str(e)}
        finally:
            # Rate limiting
            await asyncio.sleep(self.rate_limit_delay)
    
    async def get_quote(self, symbol: str) -> dict:
        """Get global quote for symbol"""
        params = {
            'function': 'GLOBAL_QUOTE',
            'symbol': symbol
        }
        return await self._call_api(params)
    
    async def get_daily(self, symbol: str) -> dict:
        """Get daily time series"""
        params = {
            'function': 'TIME_SERIES_DAILY',
            'symbol': symbol,
            'outputsize': 'compact'
        }
        return await self._call_api(params)
    
    async def get_crypto_quote(self, symbol: str, market: str = 'USD') -> dict:
        """Get cryptocurrency quote"""
        params = {
            'function': 'CURRENCY_EXCHANGE_RATE',
            'from_currency': symbol,
            'to_currency': market
        }
        return await self._call_api(params)


class AlphaStreamAggregator:
    """Aggregate alpha from multiple sources"""
    
    def __init__(self):
        self.sources: dict[str, Any] = {}
        self.signals: list[AlphaSignal] = []
        self.market_data: dict[str, MarketData] = {}
        self.favorite_symbols = [
            'ETH', 'BTC', 'SOL', 'ZEC', 'HYPE',
            'ETHBTC', 'SOLBTC', 'ZECBTC', 'BTCUSDT', 'ETHUSDT', 'HYPEUSDT'
        ]
        
    def add_source(self, name: str, client: Any):
        """Add an alpha source"""
        self.sources[name] = client
        logger.info(f"Added alpha source: {name}")
    
    async def fetch_all_market_data(self) -> dict[str, MarketData]:
        """Fetch market data from all sources"""
        tasks = []
        
        for source_name, client in self.sources.items():
            if hasattr(client, 'get_crypto_quote'):
                for symbol in ['BTC', 'ETH']:
                    tasks.append(self._fetch_crypto_quote(client, symbol, source_name))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Fetch error: {result}")
            elif isinstance(result, MarketData):
                self.market_data[result.symbol] = result
        
        return self.market_data
    
    async def _fetch_crypto_quote(self, client: Any, symbol: str, source: str) -> MarketData:
        """Fetch crypto quote and convert to MarketData"""
        try:
            data = await client.get_crypto_quote(symbol)
            
            if 'error' in data:
                raise Exception(data['error'])
            
            exchange_rate = data.get('Realtime Currency Exchange Rate', {})
            
            return MarketData(
                symbol=symbol,
                price=float(exchange_rate.get('5. Exchange Rate', 0)),
                change_24h=0.0,  # Not provided in basic endpoint
                volume_24h=0.0,
                timestamp=exchange_rate.get('6. Last Refreshed', datetime.utcnow().isoformat()),
                source=source
            )
        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")
            raise
    
    def generate_signals(self) -> list[AlphaSignal]:
        """Generate trading signals from aggregated data"""
        signals = []
        
        # Simple momentum signals
        for symbol, data in self.market_data.items():
            # Skip if no price
            if not data.price:
                continue
            
            # Generate dummy signals for demonstration
            # In production, this would use actual alpha calculations
            signal = AlphaSignal(
                symbol=symbol,
                signal='neutral',
                confidence=0.5,
                source='alphastream',
                timestamp=datetime.utcnow().isoformat(),
                timeframe='1d'
            )
            
            signals.append(signal)
        
        self.signals = signals
        return signals
    
    def get_signal_summary(self) -> dict:
        """Get summary of current signals"""
        if not self.signals:
            return {'status': 'no_signals', 'count': 0}
        
        long_count = sum(1 for s in self.signals if s.signal == 'long')
        short_count = sum(1 for s in self.signals if s.signal == 'short')
        neutral_count = sum(1 for s in self.signals if s.signal == 'neutral')
        
        avg_confidence = sum(s.confidence for s in self.signals) / len(self.signals)
        
        return {
            'status': 'active',
            'count': len(self.signals),
            'long': long_count,
            'short': short_count,
            'neutral': neutral_count,
            'avg_confidence': round(avg_confidence, 2),
            'symbols': [s.symbol for s in self.signals]
        }


class MockAlphaSource:
    """Mock alpha source for testing without API keys"""
    
    async def get_crypto_quote(self, symbol: str) -> dict:
        """Return mock crypto data"""
        mock_prices = {
            'BTC': 65000.0,
            'ETH': 3500.0,
            'SOL': 145.0,
            'ZEC': 45.0,
            'HYPE': 12.5
        }
        
        return {
            'Realtime Currency Exchange Rate': {
                '1. From_Currency Code': symbol,
                '2. From_Currency Name': symbol,
                '3. To_Currency Code': 'USD',
                '4. To_Currency Name': 'US Dollar',
                '5. Exchange Rate': str(mock_prices.get(symbol, 100.0)),
                '6. Last Refreshed': datetime.utcnow().isoformat(),
                '7. Time Zone': 'UTC',
                '8. Bid Price': str(mock_prices.get(symbol, 100.0) * 0.999),
                '9. Ask Price': str(mock_prices.get(symbol, 100.0) * 1.001),
            }
        }
    
    async def connect(self):
        pass
    
    async def disconnect(self):
        pass


# Configuration
ALPHAVANTAGE_CONFIG = {
    'api_key': '',  # Set via environment variable
    'rate_limit': 5,  # Calls per minute (free tier)
}


# Favorite symbols with metadata
FAVORITE_SYMBOLS_CONFIG = {
    'ETHBTC': {
        'name': 'Ethereum/Bitcoin',
        'category': 'pair_trade',
        'description': 'ETH vs BTC pair trading',
        'tradingview_symbol': 'BINANCE:ETHBTC',
        'min_confidence': 0.75,
    },
    'SOLBTC': {
        'name': 'Solana/Bitcoin',
        'category': 'pair_trade',
        'description': 'SOL vs BTC pair trading',
        'tradingview_symbol': 'BINANCE:SOLBTC',
        'min_confidence': 0.75,
    },
    'ZECBTC': {
        'name': 'Zcash/Bitcoin',
        'category': 'pair_trade',
        'description': 'ZEC vs BTC pair trading',
        'tradingview_symbol': 'BINANCE:ZECBTC',
        'min_confidence': 0.70,
    },
    'BTCUSDT': {
        'name': 'Bitcoin',
        'category': 'spot',
        'description': 'BTC spot trading',
        'tradingview_symbol': 'BINANCE:BTCUSDT',
        'min_confidence': 0.65,
    },
    'ETHUSDT': {
        'name': 'Ethereum',
        'category': 'spot',
        'description': 'ETH spot trading',
        'tradingview_symbol': 'BINANCE:ETHUSDT',
        'min_confidence': 0.65,
    },
    'HYPEUSDT': {
        'name': 'Hyperliquid',
        'category': 'spot',
        'description': 'HYPE spot trading',
        'tradingview_symbol': 'BINANCE:HYPEUSDT',
        'min_confidence': 0.70,
    },
}


def get_favorite_symbols() -> list[str]:
    """Get list of favorite trading symbols"""
    return list(FAVORITE_SYMBOLS_CONFIG.keys())


def get_symbol_config(symbol: str) -> dict:
    """Get configuration for a specific symbol"""
    return FAVORITE_SYMBOLS_CONFIG.get(symbol.upper(), {})


if __name__ == '__main__':
    print("AlphaStream Integration Test:")
    print("=" * 50)
    print("\nFavorite Symbols:")
    for sym, config in FAVORITE_SYMBOLS_CONFIG.items():
        print(f"  {sym}: {config['name']} ({config['category']})")
    
    print("\nExample usage:")
    print("  aggregator = AlphaStreamAggregator()")
    print("  aggregator.add_source('alphavantage', AlphaVantageClient(api_key))")
    print("  data = await aggregator.fetch_all_market_data()")
