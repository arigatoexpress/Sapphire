#!/usr/bin/env python3
"""
TradingView Webhook Integration
Receives alerts from TradingView and routes to trading engine
"""

import json
import logging
import hmac
import hashlib
from datetime import datetime
from typing import Dict, Optional, Any
from dataclasses import dataclass, asdict
from aiohttp import web

logger = logging.getLogger('tradingview')


@dataclass
class TradingViewAlert:
    """TradingView alert payload"""
    symbol: str
    action: str  # 'buy', 'sell', 'entry_long', 'entry_short', 'exit'
    price: float
    timestamp: str
    message: str = ""
    exchange: str = ""
    interval: str = ""
    
    # Optional fields from Pine Script
    z_score: Optional[float] = None
    confidence: Optional[float] = None
    regime_score: Optional[float] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_webhook(cls, data: Dict) -> 'TradingViewAlert':
        """Create from TradingView webhook JSON"""
        return cls(
            symbol=data.get('symbol', '').upper(),
            action=data.get('action', '').lower(),
            price=float(data.get('price', 0)),
            timestamp=data.get('time', datetime.utcnow().isoformat()),
            message=data.get('message', ''),
            exchange=data.get('exchange', ''),
            interval=data.get('interval', ''),
            z_score=float(data.get('z_score')) if 'z_score' in data else None,
            confidence=float(data.get('confidence')) if 'confidence' in data else None,
            regime_score=float(data.get('regime_score')) if 'regime_score' in data else None,
        )


class TradingViewHandler:
    """Handle TradingView webhook alerts"""
    
    # Webhook secret for validation
    WEBHOOK_SECRET = "sapphire_trading_2024"
    
    # Supported actions from TradingView
    VALID_ACTIONS = [
        'buy', 'sell', 'long', 'short', 'exit', 'close',
        'entry_long', 'entry_short', 'exit_long', 'exit_short'
    ]
    
    # Favorite symbols with TradingView format mapping
    SYMBOL_MAPPING = {
        'BINANCE:ETHBTC': 'ETHBTC',
        'BINANCE:SOLBTC': 'SOLBTC',
        'BINANCE:ZECBTC': 'ZECBTC',
        'BINANCE:BTCUSDT': 'BTCUSDT',
        'BINANCE:ETHUSDT': 'ETHUSDT',
        'BINANCE:HYPEUSDT': 'HYPEUSDT',
        'COINBASE:ETHBTC': 'ETHBTC',
        'COINBASE:BTCUSD': 'BTCUSDT',
        'BYBIT:ETHUSDT': 'ETHUSDT',
        'BYBIT:BTCUSDT': 'BTCUSDT',
    }
    
    def __init__(self, trade_callback=None):
        self.trade_callback = trade_callback
        self.alert_history: list = []
        self.max_history = 100
        
    async def handle_webhook(self, request: web.Request) -> web.Response:
        """Handle incoming TradingView webhook"""
        try:
            # Get raw body for signature verification
            body = await request.text()
            
            # Parse JSON
            data = json.loads(body)
            logger.info(f"Received TradingView alert: {json.dumps(data)[:200]}...")
            
            # Validate
            if not self._validate_payload(data):
                return web.json_response(
                    {'status': 'error', 'message': 'Invalid payload'},
                    status=400
                )
            
            # Parse alert
            alert = TradingViewAlert.from_webhook(data)
            
            # Normalize symbol
            alert.symbol = self._normalize_symbol(alert.symbol)
            
            # Store in history
            self.alert_history.append({
                'timestamp': datetime.utcnow().isoformat(),
                'alert': alert.to_dict()
            })
            if len(self.alert_history) > self.max_history:
                self.alert_history.pop(0)
            
            # Process alert
            result = await self._process_alert(alert)
            
            return web.json_response({
                'status': 'success',
                'processed': result,
                'alert_id': len(self.alert_history)
            })
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            return web.json_response(
                {'status': 'error', 'message': 'Invalid JSON'},
                status=400
            )
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return web.json_response(
                {'status': 'error', 'message': str(e)},
                status=500
            )
    
    def _validate_payload(self, data: Dict) -> bool:
        """Validate webhook payload"""
        # Check required fields
        if 'symbol' not in data or 'action' not in data:
            return False
        
        # Validate action
        action = data.get('action', '').lower()
        if action not in self.VALID_ACTIONS:
            logger.warning(f"Unknown action: {action}")
            return False
        
        return True
    
    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize TradingView symbol to internal format"""
        # Remove prefix (BINANCE:, COINBASE:, etc.)
        if ':' in symbol:
            symbol = symbol.split(':')[1]
        
        # Check mapping
        full_symbol = f"{symbol.split(':')[0] if ':' in symbol else 'UNKNOWN'}:{symbol}"
        if full_symbol in self.SYMBOL_MAPPING:
            return self.SYMBOL_MAPPING[full_symbol]
        
        # Default: return uppercase, remove special chars
        return symbol.upper().replace('/', '').replace('-', '')
    
    async def _process_alert(self, alert: TradingViewAlert) -> Dict:
        """Process the alert and potentially execute trade"""
        logger.info(f"Processing {alert.action} alert for {alert.symbol} @ ${alert.price}")
        
        # Map action to trade side
        side = self._map_action_to_side(alert.action)
        if not side:
            return {'executed': False, 'reason': 'Action not mappable to trade'}
        
        # Build trade request
        trade_request = {
            'symbol': alert.symbol,
            'side': side,
            'amount_usd': 5.0,  # Default from safety limits
            'source': 'tradingview',
            'alert_price': alert.price,
            'alert_confidence': alert.confidence,
            'z_score': alert.z_score,
        }
        
        # Add metadata
        if alert.confidence and alert.confidence < 0.7:
            trade_request['dry_run'] = True
            trade_request['reason'] = f"Low confidence: {alert.confidence}"
        
        # Execute via callback if provided
        if self.trade_callback:
            result = await self.trade_callback(trade_request)
            return {
                'executed': result.get('success', False),
                'trade_id': result.get('request_id'),
                'details': result
            }
        
        return {
            'executed': False,
            'request': trade_request,
            'reason': 'No trade callback configured'
        }
    
    def _map_action_to_side(self, action: str) -> Optional[str]:
        """Map TradingView action to trade side"""
        buy_actions = ['buy', 'long', 'entry_long']
        sell_actions = ['sell', 'short', 'entry_short']
        
        if action in buy_actions:
            return 'buy'
        elif action in sell_actions:
            return 'sell'
        elif action in ['exit', 'close', 'exit_long', 'exit_short']:
            return 'exit'  # Special handling needed
        return None
    
    async def get_alerts(self, request: web.Request) -> web.Response:
        """Get recent alert history"""
        limit = int(request.query.get('limit', 10))
        return web.json_response({
            'alerts': self.alert_history[-limit:],
            'total': len(self.alert_history)
        })
    
    async def get_status(self, request: web.Request) -> web.Response:
        """Get TradingView integration status"""
        return web.json_response({
            'status': 'active',
            'total_alerts': len(self.alert_history),
            'supported_actions': self.VALID_ACTIONS,
            'symbol_mapping': self.SYMBOL_MAPPING
        })


# Pine Script template for TradingView alerts
def get_pine_script_template() -> str:
    """Get Pine Script template for sending alerts"""
    return '''
// TradingView Alert Template for Sapphire Bot
// Add this to your Pine Script strategy

// Alert message format
alertMessage = '{' +
    '"symbol": "' + syminfo.tickerid + '",' +
    '"action": "' + (strategy.position_size > 0 ? "buy" : "sell") + '",' +
    '"price": ' + str.tostring(close) + ',' +
    '"time": "' + str.tostring(timestamp) + '",' +
    '"exchange": "' + syminfo.exchange + '",' +
    '"interval": "' + timeframe.period + '"' +
    (nz(z_score) != 0 ? ',"z_score": ' + str.tostring(z_score) : '') +
    (nz(confidence) != 0 ? ',"confidence": ' + str.tostring(confidence) : '') +
    '}'

// Send alert on strategy events
if (strategy.opentrades > 0 and strategy.opentrades[1] == 0)
    alert(alertMessage, alert.freq_once_per_bar_close)
'''


# Webhook URL configuration
WEBHOOK_CONFIG = {
    'url': 'https://your-webhook-url.com/webhook/tradingview',
    'method': 'POST',
    'headers': {
        'Content-Type': 'application/json',
    }
}


# Example alert format
EXAMPLE_ALERT = {
    "symbol": "BINANCE:ETHBTC",
    "action": "buy",
    "price": 0.05234,
    "time": "2024-01-15T10:30:00Z",
    "exchange": "BINANCE",
    "interval": "1H",
    "message": "Long entry - Z-Score exceeded 2.0",
    "z_score": 2.15,
    "confidence": 0.82,
    "regime_score": 0.75
}


if __name__ == '__main__':
    # Test
    handler = TradingViewHandler()
    
    print("TradingView Integration Test:")
    print("=" * 50)
    print("\nExample alert format:")
    print(json.dumps(EXAMPLE_ALERT, indent=2))
    print("\nSupported actions:", handler.VALID_ACTIONS)
    print("\nPine Script template available via get_pine_script_template()")
