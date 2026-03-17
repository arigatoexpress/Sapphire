#!/usr/bin/env python3
"""
Lighter Trader with API Index 2
Runs on rari1, accessible via ethernet from rari2
"""

import asyncio
import json
import logging
import os
import sys
from decimal import Decimal
from typing import Dict, Optional

# Add lighter SDK path
sys.path.insert(0, '/home/rari/.openclaw/workspace/sapphire-trading-env/lib/python3.13/site-packages')

from lighter.client import Client as LighterClient
from lighter.models import OrderSide, OrderType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('lighter_trader')

class LighterTrader:
    """
    Lighter Protocol trader using API index 2
    Routes through VPN for privacy
    """
    
    def __init__(self):
        # Load API keys for index 2
        self.api_key = os.getenv(
            'LIGHTER_API_KEY_2', 
            'a27b1f40e4a08bd14724684207a92f9848eb9770500ee3e6dc687ff765b759f4ec6f8fee37e6d07a'
        )
        self.api_public_key = os.getenv(
            'LIGHTER_API_PUBLIC_KEY_2',
            'c8deac305ba69160801ff18fb9a026824b555aaa0e169621c7b66012aa41a50b22180db62e330c48'
        )
        self.client: Optional[LighterClient] = None
        
    async def connect(self):
        """Initialize connection to Lighter"""
        try:
            # Initialize client with index 2 credentials
            self.client = LighterClient(
                api_key=self.api_key,
                public_key=self.api_public_key,
                network='mainnet'  # or 'testnet' for testing
            )
            
            # Load markets
            await self.client.load_markets()
            logger.info(f"✅ Lighter client connected (API index 2)")
            logger.info(f"   Available markets: {len(self.client.markets)}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to Lighter: {e}")
            return False
    
    async def get_balance(self) -> Dict:
        """Get account balance"""
        if not self.client:
            return {'error': 'Not connected'}
        
        try:
            balance = await self.client.get_balance()
            return {
                'success': True,
                'balance': str(balance),
                'api_index': 2
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def place_order(
        self,
        symbol: str,
        side: str,  # 'buy' or 'sell'
        amount: str,
        order_type: str = 'market',
        price: Optional[str] = None
    ) -> Dict:
        """Place an order on Lighter"""
        if not self.client:
            return {'error': 'Not connected'}
        
        try:
            # Normalize symbol
            symbol = symbol.upper().replace('-', '/')
            if '/' not in symbol:
                symbol = f"{symbol}/USDC"
            
            # Map side
            order_side = OrderSide.BUY if side.lower() == 'buy' else OrderSide.SELL
            
            # Map order type
            order_type_enum = OrderType.LIMIT if order_type.lower() == 'limit' else OrderType.MARKET
            
            logger.info(f"📤 Placing {order_type} {side} order: {amount} {symbol}")
            
            # Place order
            order = await self.client.create_order(
                symbol=symbol,
                side=order_side,
                order_type=order_type_enum,
                amount=Decimal(amount),
                price=Decimal(price) if price else None
            )
            
            return {
                'success': True,
                'order_id': order.id,
                'symbol': symbol,
                'side': side,
                'amount': amount,
                'price': str(order.price) if order.price else 'market',
                'status': order.status,
                'api_index': 2,
                'venue': 'lighter'
            }
            
        except Exception as e:
            logger.error(f"❌ Order failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'symbol': symbol,
                'side': side,
                'amount': amount
            }
    
    async def get_markets(self) -> Dict:
        """Get available markets"""
        if not self.client:
            return {'error': 'Not connected'}
        
        try:
            markets = []
            for symbol, market in self.client.markets.items():
                markets.append({
                    'symbol': symbol,
                    'base': market.base_asset,
                    'quote': market.quote_asset,
                    'min_order': str(market.min_order_size),
                    'maker_fee': str(market.maker_fee),
                    'taker_fee': str(market.taker_fee)
                })
            
            return {
                'success': True,
                'markets': markets,
                'count': len(markets)
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def close(self):
        """Close connection"""
        if self.client:
            await self.client.close()
            logger.info("Lighter client disconnected")


async def main():
    """CLI interface for testing"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Lighter Trader - API Index 2')
    parser.add_argument('action', choices=['balance', 'markets', 'trade'])
    parser.add_argument('--symbol', default='BTC/USDC')
    parser.add_argument('--side', choices=['buy', 'sell'], default='buy')
    parser.add_argument('--amount', default='0.01')
    parser.add_argument('--price', help='Limit price (omit for market)')
    
    args = parser.parse_args()
    
    trader = LighterTrader()
    
    if not await trader.connect():
        print(json.dumps({'error': 'Connection failed'}, indent=2))
        sys.exit(1)
    
    try:
        if args.action == 'balance':
            result = await trader.get_balance()
        elif args.action == 'markets':
            result = await trader.get_markets()
        elif args.action == 'trade':
            result = await trader.place_order(
                symbol=args.symbol,
                side=args.side,
                amount=args.amount,
                price=args.price
            )
        
        print(json.dumps(result, indent=2))
        
    finally:
        await trader.close()


if __name__ == '__main__':
    asyncio.run(main())
