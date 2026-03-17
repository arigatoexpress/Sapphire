#!/usr/bin/env python3
"""
Unified Trader - Aster + Lighter
Test allocation: $25 per platform
Runs on rari1 via VPN
"""

import asyncio
import json
import os
import sys
from decimal import Decimal

# Load environment
from dotenv import load_dotenv
load_dotenv('/home/rari/.sapphire/.env')

sys.path.insert(0, '/home/rari/.openclaw/workspace/sapphire-trading-env/lib/python3.13/site-packages')
sys.path.insert(0, '/home/rari/.sapphire/trading')

# Test allocation limits
TEST_ALLOCATION = {
    'lighter': 25.0,  # $25 USDC for testing
    'aster': 25.0     # $25 for testing
}

class UnifiedTrader:
    """Unified interface for Aster and Lighter trading"""
    
    def __init__(self):
        self.lighter_client = None
        self.aster_client = None
        self.balances = {}
        
    async def connect_lighter(self):
        """Connect to Lighter (API Index 0)"""
        try:
            import lighter
            
            api_key = os.getenv('LIGHTER_API_KEY')
            if not api_key:
                return False, 'LIGHTER_API_KEY not set'
            
            config = lighter.Configuration()
            config.api_key['ApiKeyAuth'] = api_key
            
            self.lighter_client = lighter.ApiClient(config)
            return True, 'Connected'
            
        except Exception as e:
            return False, str(e)
    
    async def connect_aster(self):
        """Connect to Aster"""
        try:
            # Import Aster client
            from aster_client import AsterClient
            
            api_key = os.getenv('ASTER_API_KEY')
            api_secret = os.getenv('ASTER_API_SECRET')
            
            if not api_key or not api_secret:
                return False, 'ASTER credentials not set'
            
            self.aster_client = AsterClient(api_key, api_secret)
            await self.aster_client.connect()
            return True, 'Connected'
            
        except Exception as e:
            return False, str(e)
    
    async def get_lighter_balance(self):
        """Get Lighter balance for account index 0"""
        try:
            import lighter
            
            account_api = lighter.AccountApi(self.lighter_client)
            account = await account_api.account(by='index', value='0')
            data = account.to_dict()
            
            if data.get('accounts'):
                acc = data['accounts'][0]
                return {
                    'success': True,
                    'platform': 'lighter',
                    'collateral': float(acc.get('collateral', 0)),
                    'available': float(acc.get('available_balance', 0)),
                    'test_allocation': TEST_ALLOCATION['lighter'],
                    'usable_for_test': min(float(acc.get('available_balance', 0)), TEST_ALLOCATION['lighter'])
                }
            return {'success': False, 'error': 'No account data'}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def get_aster_balance(self):
        """Get Aster balance"""
        try:
            if not self.aster_client:
                return {'success': False, 'error': 'Not connected'}
            
            balance = await self.aster_client.get_balance()
            
            return {
                'success': True,
                'platform': 'aster',
                'balance': balance,
                'test_allocation': TEST_ALLOCATION['aster'],
                'usable_for_test': min(float(balance.get('USDC', 0)), TEST_ALLOCATION['aster'])
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def place_lighter_order(self, symbol: str, side: str, amount: float, price: float = None):
        """Place order on Lighter with $25 limit"""
        try:
            # Check if within test allocation
            balance = await self.get_lighter_balance()
            if not balance['success']:
                return balance
            
            usable = balance['usable_for_test']
            if usable <= 0:
                return {'success': False, 'error': f'No test funds available. Allocation: ${TEST_ALLOCATION["lighter"]}'}
            
            # For now, simulate the order
            # Real implementation needs order signing
            return {
                'success': True,
                'simulated': True,
                'platform': 'lighter',
                'symbol': symbol,
                'side': side.upper(),
                'amount': amount,
                'price': price or 'market',
                'test_allocation': TEST_ALLOCATION['lighter'],
                'remaining_allocation': usable - (amount * (price or 30000)),
                'note': 'Real trading requires transaction signing'
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def place_aster_order(self, symbol: str, side: str, amount: float, price: float = None):
        """Place order on Aster with $25 limit"""
        try:
            # Check if within test allocation
            balance = await self.get_aster_balance()
            if not balance['success']:
                return balance
            
            usable = balance['usable_for_test']
            if usable <= 0:
                return {'success': False, 'error': f'No test funds available. Allocation: ${TEST_ALLOCATION["aster"]}'}
            
            # For now, simulate
            return {
                'success': True,
                'simulated': True,
                'platform': 'aster',
                'symbol': symbol,
                'side': side.upper(),
                'amount': amount,
                'price': price or 'market',
                'test_allocation': TEST_ALLOCATION['aster'],
                'remaining_allocation': usable - (amount * (price or 30000)),
                'note': 'Real trading requires order builder'
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def get_all_balances(self):
        """Get balances from both platforms"""
        results = {}
        
        # Connect and get Lighter balance
        ok, msg = await self.connect_lighter()
        if ok:
            results['lighter'] = await self.get_lighter_balance()
        else:
            results['lighter'] = {'success': False, 'error': msg}
        
        # Connect and get Aster balance
        ok, msg = await self.connect_aster()
        if ok:
            results['aster'] = await self.get_aster_balance()
        else:
            results['aster'] = {'success': False, 'error': msg}
        
        return results
    
    async def close(self):
        """Close connections"""
        if self.lighter_client:
            await self.lighter_client.close()
        if self.aster_client:
            await self.aster_client.close()


async def main():
    import argparse
    parser = argparse.ArgumentParser(description='Unified Trader - $25 per platform')
    parser.add_argument('action', choices=['balance', 'trade'])
    parser.add_argument('--platform', choices=['lighter', 'aster', 'both'], default='both')
    parser.add_argument('--symbol', default='BTC/USDC')
    parser.add_argument('--side', choices=['buy', 'sell'], default='buy')
    parser.add_argument('--amount', type=float, default=0.01)
    parser.add_argument('--price', type=float, help='Limit price')
    
    args = parser.parse_args()
    
    trader = UnifiedTrader()
    
    try:
        if args.action == 'balance':
            if args.platform == 'both':
                results = await trader.get_all_balances()
                print(json.dumps(results, indent=2, default=str))
            elif args.platform == 'lighter':
                ok, msg = await trader.connect_lighter()
                if ok:
                    result = await trader.get_lighter_balance()
                    print(json.dumps(result, indent=2, default=str))
                else:
                    print(json.dumps({'success': False, 'error': msg}, indent=2))
            else:
                ok, msg = await trader.connect_aster()
                if ok:
                    result = await trader.get_aster_balance()
                    print(json.dumps(result, indent=2, default=str))
                else:
                    print(json.dumps({'success': False, 'error': msg}, indent=2))
        
        elif args.action == 'trade':
            if args.platform == 'lighter':
                result = await trader.place_lighter_order(args.symbol, args.side, args.amount, args.price)
            elif args.platform == 'aster':
                result = await trader.place_aster_order(args.symbol, args.side, args.amount, args.price)
            else:
                result = {'success': False, 'error': 'Must specify --platform for trading'}
            
            print(json.dumps(result, indent=2, default=str))
    
    finally:
        await trader.close()


if __name__ == '__main__':
    asyncio.run(main())
