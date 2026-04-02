#!/usr/bin/env python3
"""
Sapphire AI - Mac TradingView Controller
Full autonomous control of TradingView Web
"""

import asyncio
import logging
import sys
from datetime import datetime
from typing import Dict, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from playwright.async_api import Browser, Page, async_playwright
except ImportError:
    logger.error("Playwright not installed. Run: pip3 install playwright")
    sys.exit(1)


class TradingViewMacController:
    """Full autonomous controller for TradingView Web on Mac"""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.playwright = None
        self.tv_url = "https://www.tradingview.com/chart/"
        self.connected = False
        self.current_symbol = ""
        self.current_price = 0.0
        self.indicator_values = {}
        self.last_update = None
        
    async def start(self, headless: bool = False):
        """Start browser and connect to TradingView"""
        logger.info("🚀 Starting TradingView Mac Controller")
        
        self.playwright = await async_playwright().start()
        
        # Launch browser with macOS settings
        self.browser = await self.playwright.chromium.launch(
            headless=headless,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        
        self.page = await context.new_page()
        
        logger.info("📍 Navigating to TradingView...")
        await self.page.goto(self.tv_url, wait_until='networkidle')
        
        # Wait for chart
        try:
            await self.page.wait_for_selector('[data-name="legend-series-item"]', timeout=30000)
            self.connected = True
            logger.info("✅ Connected to TradingView Web")
        except:
            logger.warning("⚠️  Chart not detected - may need login or page load")
            self.connected = True  # Still mark as connected
            
        # Start monitoring
        asyncio.create_task(self._monitor_loop())
        
    async def login(self, username: str = None, password: str = None):
        """Login if credentials provided, otherwise manual"""
        if not self.page:
            return
            
        logger.info("🔐 Checking login status...")
        
        # Look for sign in button
        sign_in = await self.page.query_selector('button:has-text("Sign in")')
        if sign_in:
            logger.info("   Sign in button found - please login manually in browser")
            logger.info("   Waiting 60 seconds for manual login...")
            await asyncio.sleep(60)
        else:
            logger.info("   Already logged in or no sign in required")
            
    async def change_symbol(self, symbol: str):
        """Change chart symbol"""
        if not self.page:
            return
            
        logger.info(f"📊 Changing symbol to: {symbol}")
        
        try:
            # Click symbol search
            await self.page.click('[data-name="symbol-search-button"]', timeout=5000)
            await asyncio.sleep(0.5)
            
            # Type symbol
            await self.page.fill('[data-name="symbol-search-input"] input', symbol)
            await asyncio.sleep(0.5)
            
            # Press Enter
            await self.page.press('[data-name="symbol-search-input"] input', 'Enter')
            await asyncio.sleep(2)
            
            self.current_symbol = symbol
            logger.info(f"✅ Symbol changed to {symbol}")
        except Exception as e:
            logger.error(f"Error changing symbol: {e}")
            
    async def get_price(self) -> float:
        """Get current price"""
        if not self.page:
            return 0.0
            
        try:
            # Try multiple selectors
            selectors = [
                '[data-name="legend-series-item"] .valueValue-G1h3ZX4F',
                '.chart-gui-wrapper .priceValue',
                '[class*="priceValue"]',
                '[class*="valueValue"]'
            ]
            
            for selector in selectors:
                try:
                    elem = await self.page.query_selector(selector)
                    if elem:
                        text = await elem.inner_text()
                        price = float(text.replace(',', '').replace('$', ''))
                        if price > 0:
                            return price
                except:
                    continue
        except Exception as e:
            logger.debug(f"Price fetch error: {e}")
            
        return 0.0
        
    async def get_indicators(self) -> Dict[str, str]:
        """Get indicator values"""
        values = {}
        if not self.page:
            return values
            
        try:
            # Get all legend items
            items = await self.page.query_selector_all('[data-name="legend-source-item"]')
            for item in items:
                try:
                    name_elem = await item.query_selector('[class*="title"]')
                    value_elem = await item.query_selector('[class*="valueValue"], [class*="value"]')
                    
                    if name_elem and value_elem:
                        name = await name_elem.inner_text()
                        value = await value_elem.inner_text()
                        values[name] = value
                except:
                    continue
        except Exception as e:
            logger.debug(f"Indicator fetch error: {e}")
            
        return values
        
    async def take_screenshot(self, path: str = "/tmp/tv_screenshot.png"):
        """Take screenshot"""
        if self.page:
            await self.page.screenshot(path=path, full_page=False)
            logger.info(f"📸 Screenshot saved: {path}")
            return path
        return None
        
    async def _monitor_loop(self):
        """Background monitoring"""
        while self.connected:
            try:
                price = await self.get_price()
                if price > 0:
                    self.current_price = price
                    self.last_update = datetime.now()
                    
                self.indicator_values = await self.get_indicators()
                
                # Log every 30 seconds
                if int(datetime.now().timestamp()) % 30 == 0:
                    logger.info(f"📊 {self.current_symbol or 'Unknown'} @ ${self.current_price:,.2f} | Indicators: {len(self.indicator_values)}")
                    
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(5)
                
    async def get_status(self) -> Dict:
        return {
            "connected": self.connected,
            "symbol": self.current_symbol,
            "price": self.current_price,
            "indicators": self.indicator_values,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "url": self.tv_url
        }
        
    async def stop(self):
        logger.info("🛑 Stopping controller")
        self.connected = False
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()


# HTTP API
from aiohttp import web


async def start_api(controller: TradingViewMacController, port: int = 8082):
    app = web.Application()
    
    async def status(request):
        return web.json_response(await controller.get_status())
        
    async def symbol(request):
        data = await request.json()
        sym = data.get('symbol', '')
        if sym:
            await controller.change_symbol(sym)
            return web.json_response({"status": "ok", "symbol": sym})
        return web.json_response({"error": "No symbol"}, status=400)
        
    async def data(request):
        return web.json_response({
            "symbol": controller.current_symbol,
            "price": controller.current_price,
            "indicators": controller.indicator_values,
            "timestamp": datetime.now().isoformat()
        })
        
    async def screenshot(request):
        path = await controller.take_screenshot()
        return web.json_response({"status": "ok", "path": path})
    
    app.router.add_get('/status', status)
    app.router.add_post('/symbol', symbol)
    app.router.add_get('/data', data)
    app.router.add_get('/screenshot', screenshot)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"🌐 API server started on port {port}")
    return runner


async def main():
    controller = TradingViewMacController()
    
    try:
        # Start browser (visible so user can login if needed)
        await controller.start(headless=False)
        
        # Check/login
        await controller.login()
        
        # Start API
        api = await start_api(controller, port=8082)
        
        logger.info("")
        logger.info("✅ TradingView Mac Controller is RUNNING")
        logger.info("")
        logger.info("📍 TradingView Web: https://www.tradingview.com/chart/")
        logger.info("🌐 API: http://localhost:8082")
        logger.info("")
        logger.info("Endpoints:")
        logger.info("  GET  /status     - Controller status")
        logger.info("  GET  /data       - Live price & indicators")
        logger.info("  POST /symbol     - Change symbol {\"symbol\": \"BTCUSDT\"}")
        logger.info("  GET  /screenshot - Take screenshot")
        logger.info("")
        logger.info("Press Ctrl+C to stop")
        logger.info("")
        
        # Keep running
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("\n👋 Shutting down...")
    finally:
        await controller.stop()


if __name__ == "__main__":
    asyncio.run(main())
