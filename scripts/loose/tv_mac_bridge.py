#!/usr/bin/env python3
"""
Sapphire AI - Mac TradingView Strategy Bridge
Receives Pine Script alerts and forwards to execution
"""

import asyncio
import json
import logging
import re
import sys
from datetime import datetime
from typing import Dict, Optional

import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

# Forward to Windows webhook
WINDOWS_WEBHOOK = "http://100.71.10.48:9090/webhook/tradingview"


class MacStrategyBridge:
    """Bridge between TradingView alerts and execution bots"""
    
    def __init__(self):
        self.running = False
        self.alert_history = []
        self.webhook_url = WINDOWS_WEBHOOK
        
    def parse_alert(self, message: str) -> Optional[Dict]:
        """Parse TradingView alert"""
        try:
            # JSON format
            if message.startswith('{'):
                return json.loads(message)
                
            # Text patterns
            patterns = [
                r'(?P<symbol>\w+)\s+(?P<action>entry|exit)\s+(?P<side>long|short)',
                r'(?P<action>buy|sell)\s+(?P<symbol>\w+)',
                r'Strategy.*?(?P<symbol>\w+).*?(?P<action>long|short|buy|sell)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, message, re.IGNORECASE)
                if match:
                    groups = match.groupdict()
                    return {
                        "symbol": groups.get('symbol', 'UNKNOWN').upper(),
                        "action": self._normalize_action(
                            groups.get('action', ''),
                            groups.get('side', '')
                        ),
                        "price": 0,
                        "alert_message": message,
                        "timestamp": datetime.now().isoformat()
                    }
        except Exception as e:
            logger.error(f"Parse error: {e}")
        return None
        
    def _normalize_action(self, action: str, side: str = "") -> str:
        action = action.lower()
        side = side.lower()
        
        if action == "buy" or (action == "entry" and side == "long"):
            return "entry_long"
        elif action == "sell" or (action == "entry" and side == "short"):
            return "entry_short"
        elif action == "exit" and side == "long":
            return "exit_long"
        elif action == "exit" and side == "short":
            return "exit_short"
        return action
        
    async def forward_to_webhook(self, alert: Dict) -> bool:
        """Forward alert to Windows webhook"""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "symbol": alert.get("symbol", "BTCUSDT"),
                    "action": alert.get("action", "buy"),
                    "price": alert.get("price", 0),
                    "size": alert.get("size", 0.01),
                    "source": "mac_bridge",
                    "strategy": alert.get("strategy", "PineScript"),
                    "timestamp": datetime.now().isoformat()
                }
                
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        logger.info(f"✅ Forwarded: {payload['symbol']} {payload['action']}")
                        return True
                    else:
                        logger.error(f"❌ Webhook error: {resp.status}")
                        return False
        except Exception as e:
            logger.error(f"❌ Forward error: {e}")
            return False
            
    async def start_http_server(self, port: int = 8083):
        """Start HTTP server to receive webhooks"""
        from aiohttp import web
        
        app = web.Application()
        
        async def webhook_handler(request):
            try:
                data = await request.json()
                logger.info(f"📨 Alert received: {json.dumps(data)[:80]}")
                
                # Parse and forward
                if isinstance(data, dict):
                    success = await self.forward_to_webhook(data)
                    self.alert_history.append(data)
                    return web.json_response({
                        "status": "ok" if success else "error",
                        "alerts": len(self.alert_history)
                    })
                else:
                    return web.json_response({"status": "error", "message": "Invalid format"}, status=400)
                    
            except Exception as e:
                logger.error(f"Webhook error: {e}")
                return web.json_response({"status": "error", "message": str(e)}, status=500)
                
        async def status_handler(request):
            return web.json_response({
                "running": self.running,
                "alerts_processed": len(self.alert_history),
                "webhook_target": self.webhook_url,
                "last_alert": self.alert_history[-1] if self.alert_history else None
            })
            
        async def test_handler(request):
            """Test endpoint"""
            test_alert = {
                "symbol": "BTCUSDT",
                "action": "entry_long",
                "price": 87500.5,
                "size": 0.001,
                "test": True
            }
            success = await self.forward_to_webhook(test_alert)
            return web.json_response({
                "test": True,
                "forwarded": success,
                "target": self.webhook_url
            })
        
        app.router.add_post('/webhook', webhook_handler)
        app.router.add_get('/status', status_handler)
        app.router.add_get('/test', test_handler)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        
        logger.info(f"🌐 Strategy Bridge running on port {port}")
        logger.info("   POST /webhook - Receive TV alerts")
        logger.info("   GET  /status  - Bridge status")
        logger.info("   GET  /test    - Test pipeline")
        return runner
        
    async def run(self):
        self.running = True
        logger.info("🚀 Mac Strategy Bridge started")
        logger.info(f"   Forwarding to: {self.webhook_url}")
        
        runner = await self.start_http_server(port=8083)
        
        try:
            while self.running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("\n👋 Stopping bridge...")
        finally:
            await runner.cleanup()


async def test_mode():
    """Test the bridge"""
    bridge = MacStrategyBridge()
    
    test_alerts = [
        '{"symbol": "BTCUSDT", "action": "entry_long", "price": 85000}',
        '{"symbol": "ETHUSDT", "action": "entry_short", "price": 3500}',
        'Strategy Alert: SOLUSDT Entry Long @ 150'
    ]
    
    logger.info("🧪 Testing bridge with sample alerts")
    
    for alert_text in test_alerts:
        logger.info(f"Input: {alert_text[:50]}")
        parsed = bridge.parse_alert(alert_text)
        if parsed:
            logger.info(f"Parsed: {parsed}")
            await bridge.forward_to_webhook(parsed)
        logger.info("")
        await asyncio.sleep(1)


async def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        await test_mode()
    else:
        bridge = MacStrategyBridge()
        await bridge.run()


if __name__ == "__main__":
    asyncio.run(main())
