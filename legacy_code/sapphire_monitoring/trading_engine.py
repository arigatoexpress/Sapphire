#!/usr/bin/env python3
"""
Sapphire Trading Engine - rari2
Dedicated trading execution node with VPN
"""

import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path

import aiohttp
from aiohttp import web

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/opt/sapphire/logs/trading/engine.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('trading_engine')

# Configuration
MAX_TRADE_USD = 5.0
MAX_DAILY_TRADES = 10
TRADING_HOURS_START = 9   # 9 AM ET
TRADING_HOURS_END = 16    # 4 PM ET
SAFETY_TIMEOUT = 30       # Seconds

# Lighter Exchange IPs (for VPN routing)
LIGHTER_IPS = [
    '35.160.101.28',
    '44.230.219.105',
    '35.85.130.102',
    '52.32.59.140'
]


@dataclass
class TradeRequest:
    symbol: str
    side: str  # 'buy' or 'sell'
    amount_usd: float
    order_type: str = 'market'
    account_index: int = 1
    dry_run: bool = False
    request_id: str = ""
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()


@dataclass
class TradeResult:
    success: bool
    request_id: str
    symbol: str
    side: str
    amount_usd: float
    executed_price: float = 0.0
    executed_amount: float = 0.0
    tx_hash: str = ""
    error_message: str = ""
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()
    
    def to_dict(self) -> Dict:
        return asdict(self)


class SafetyGuardian:
    """Enforces trading safety limits"""
    
    def __init__(self, state_file: str = '/opt/sapphire/data/trading_state.json'):
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.daily_trades: List[Dict] = []
        self.load_state()
        
    def load_state(self):
        """Load daily trading state"""
        try:
            if self.state_file.exists():
                with open(self.state_file) as f:
                    data = json.load(f)
                    self.daily_trades = data.get('trades', [])
                    # Filter to today's trades only
                    today = datetime.utcnow().date().isoformat()
                    self.daily_trades = [
                        t for t in self.daily_trades 
                        if t.get('timestamp', '').startswith(today)
                    ]
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            self.daily_trades = []
    
    def save_state(self):
        """Save daily trading state"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump({'trades': self.daily_trades}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
    
    def validate_trade(self, request: TradeRequest) -> tuple[bool, str]:
        """Validate trade against safety limits"""
        
        # Check amount limit
        if request.amount_usd > MAX_TRADE_USD:
            return False, f"Amount ${request.amount_usd} exceeds max ${MAX_TRADE_USD}"
        
        # Check daily trade count
        if len(self.daily_trades) >= MAX_DAILY_TRADES:
            return False, f"Daily trade limit ({MAX_DAILY_TRADES}) reached"
        
        # Check trading hours (ET)
        now = datetime.utcnow()
        hour_et = (now.hour - 5) % 24  # Convert UTC to ET (approx)
        if not (TRADING_HOURS_START <= hour_et < TRADING_HOURS_END):
            return False, f"Outside trading hours ({TRADING_HOURS_START}:00-{TRADING_HOURS_END}:00 ET)"
        
        # Check minimum amount
        if request.amount_usd < 1.0:
            return False, "Minimum trade amount is $1.00"
        
        return True, "OK"
    
    def record_trade(self, result: TradeResult):
        """Record a completed trade"""
        self.daily_trades.append({
            'request_id': result.request_id,
            'symbol': result.symbol,
            'side': result.side,
            'amount_usd': result.amount_usd,
            'success': result.success,
            'timestamp': result.timestamp
        })
        self.save_state()
    
    def get_stats(self) -> Dict:
        """Get trading statistics"""
        return {
            'daily_trades_count': len(self.daily_trades),
            'daily_trades_limit': MAX_DAILY_TRADES,
            'daily_trades_remaining': MAX_DAILY_TRADES - len(self.daily_trades),
            'max_trade_usd': MAX_TRADE_USD
        }


class LighterClient:
    """Lighter Protocol SDK wrapper"""
    
    def __init__(self):
        self.api_url = "https://testnet.zklighter.aleohq.pro"
        self.session: Optional[aiohttp.ClientSession] = None
        self.connected = False
        
    async def connect(self):
        """Initialize connection"""
        import ssl
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)
        timeout = aiohttp.ClientTimeout(total=SAFETY_TIMEOUT)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={'Host': 'testnet.zklighter.aleohq.pro'}
        )
        self.connected = True
        logger.info("Lighter client initialized")
        
    async def disconnect(self):
        """Close connection"""
        if self.session:
            await self.session.close()
            self.session = None
        self.connected = False
        
    async def get_markets(self) -> List[Dict]:
        """Get available markets"""
        if not self.session:
            return []
            
        try:
            # Use IP directly to bypass DNS
            url = f"https://{LIGHTER_IPS[0]}/v1/markets"
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    text = await resp.text()
                    logger.error(f"Markets error: {resp.status} - {text[:200]}")
                    return []
        except Exception as e:
            logger.error(f"Failed to get markets: {e}")
            return []
    
    async def get_balance(self, account_index: int = 1) -> Dict:
        """Get account balance"""
        if not self.session:
            return {'error': 'Not connected'}
            
        try:
            url = f"https://{LIGHTER_IPS[0]}/v1/account/{account_index}"
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    text = await resp.text()
                    return {'error': f'HTTP {resp.status}: {text[:200]}'}
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return {'error': str(e)}
    
    async def execute_trade(self, request: TradeRequest) -> TradeResult:
        """Execute a trade (simplified - full implementation would use SDK)"""
        if request.dry_run:
            logger.info(f"[DRY RUN] Would execute: {request.side} {request.symbol} ${request.amount_usd}")
            return TradeResult(
                success=True,
                request_id=request.request_id,
                symbol=request.symbol,
                side=request.side,
                amount_usd=request.amount_usd,
                executed_price=0.0,
                executed_amount=request.amount_usd
            )
        
        # Real execution would use lighter SDK
        # For now, simulate success
        logger.info(f"Executing: {request.side} {request.symbol} ${request.amount_usd}")
        
        # TODO: Implement actual SDK execution
        return TradeResult(
            success=True,
            request_id=request.request_id,
            symbol=request.symbol,
            side=request.side,
            amount_usd=request.amount_usd,
            executed_price=100.0,  # Placeholder
            executed_amount=request.amount_usd / 100.0,
            tx_hash=f"0x{request.request_id}"
        )


class TradingEngine:
    """Main trading engine"""
    
    def __init__(self):
        self.guardian = SafetyGuardian()
        self.lighter = LighterClient()
        self.app = web.Application()
        self.setup_routes()
        self.running = False
        
    def setup_routes(self):
        """Setup REST API routes"""
        self.app.router.add_post('/trade', self.handle_trade)
        self.app.router.add_get('/balance', self.handle_balance)
        self.app.router.add_get('/positions', self.handle_positions)
        self.app.router.add_get('/status', self.handle_status)
        self.app.router.add_get('/stats', self.handle_stats)
        self.app.router.add_post('/cancel', self.handle_cancel)
        
    async def start(self):
        """Start the engine"""
        await self.lighter.connect()
        self.running = True
        logger.info("Trading engine started")
        
        # Start web server
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 18888)
        await site.start()
        logger.info("Internal API server started on port 18888")
        
    async def stop(self):
        """Stop the engine"""
        self.running = False
        await self.lighter.disconnect()
        logger.info("Trading engine stopped")
        
    async def handle_trade(self, request: web.Request) -> web.Response:
        """Handle trade execution request"""
        try:
            data = await request.json()
            trade_request = TradeRequest(**data)
            
            # Validate
            valid, message = self.guardian.validate_trade(trade_request)
            if not valid:
                return web.json_response({
                    'success': False,
                    'error': message
                }, status=400)
            
            # Execute
            result = await self.lighter.execute_trade(trade_request)
            
            # Record if successful
            if result.success:
                self.guardian.record_trade(result)
            
            return web.json_response(result.to_dict())
            
        except Exception as e:
            logger.error(f"Trade error: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    async def handle_balance(self, request: web.Request) -> web.Response:
        """Get account balance"""
        balance = await self.lighter.get_balance()
        return web.json_response(balance)
    
    async def handle_positions(self, request: web.Request) -> web.Response:
        """Get current positions"""
        # TODO: Implement position tracking
        return web.json_response({
            'positions': [],
            'message': 'Position tracking not yet implemented'
        })
    
    async def handle_status(self, request: web.Request) -> web.Response:
        """Get engine status"""
        return web.json_response({
            'running': self.running,
            'lighter_connected': self.lighter.connected,
            'vpn_status': self._check_vpn()
        })
    
    async def handle_stats(self, request: web.Request) -> web.Response:
        """Get trading statistics"""
        return web.json_response(self.guardian.get_stats())
    
    async def handle_cancel(self, request: web.Request) -> web.Response:
        """Cancel an order"""
        # TODO: Implement cancel
        return web.json_response({
            'success': False,
            'message': 'Cancel not yet implemented'
        })
    
    def _check_vpn(self) -> Dict:
        """Check VPN connection status"""
        try:
            import subprocess
            result = subprocess.run(
                ['curl', '-s', '--max-time', '5', 'http://httpbin.org/ip'],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                ip = data.get('origin', 'unknown')
                is_vpn = ip.startswith('79.127.')  # ProtonVPN Switzerland range
                return {
                    'connected': is_vpn,
                    'ip': ip,
                    'location': 'Switzerland' if is_vpn else 'Unknown'
                }
        except Exception as e:
            pass
        return {'connected': False, 'ip': 'unknown', 'location': 'unknown'}


async def main():
    """Main entry point"""
    engine = TradingEngine()
    
    # Setup signal handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(engine.stop()))
    
    try:
        await engine.start()
        
        # Keep running
        while engine.running:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Engine error: {e}")
        await engine.stop()
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
