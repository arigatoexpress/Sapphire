#!/usr/bin/env python3
"""
Sapphire AI - Dedicated TradingView Controller
Uses SEPARATE browser instance that won't interfere with your main Chrome
"""

import asyncio
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright
except ImportError:
    logger.error("Playwright not installed. Run: pip3 install playwright")
    exit(1)


class DedicatedTVController:
    """
    TradingView controller using DEDICATED browser instance
    Opens in separate window - won't touch your main Chrome
    """
    
    def __init__(self):
        self.browser = None
        self.page = None
        self.playwright = None
        self.context = None
        self.tv_url = "https://www.tradingview.com/chart/"
        self.connected = False
        self.current_symbol = ""
        self.current_price = 0.0
        
    async def start(self, headless: bool = False):
        """Start SEPARATE browser instance for TradingView"""
        logger.info("🚀 Starting DEDICATED TradingView Browser")
        logger.info("   This is a SEPARATE instance - your main Chrome is safe!")
        
        self.playwright = await async_playwright().start()
        
        # Launch Chromium (separate from your Chrome)
        # This creates its own isolated browser instance
        self.browser = await self.playwright.chromium.launch(
            headless=headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--window-size=1920,1080',
                '--window-position=100,100',  # Position on screen
            ]
        )
        
        # Create isolated context (like a separate profile)
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            # Use persistent storage so you stay logged in
            storage_state=None,  # Fresh start, or load from file
        )
        
        # Open page
        self.page = await self.context.new_page()
        
        logger.info("📍 Opening TradingView in DEDICATED browser...")
        await self.page.goto(self.tv_url, wait_until='networkidle')
        
        # Wait for chart
        try:
            await self.page.wait_for_selector('[data-name="legend-series-item"]', timeout=30000)
            self.connected = True
            logger.info("✅ TradingView loaded in DEDICATED browser")
            logger.info("   You can now SAFELY use your main Chrome!")
        except:
            logger.warning("⚠️  Chart may need login - please login in this window")
            self.connected = True
            
        # Start monitoring
        asyncio.create_task(self._monitor_loop())
        
    async def change_symbol(self, symbol: str):
        """Change symbol in the dedicated browser"""
        if not self.page:
            return {"status": "error", "message": "Browser not started"}
            
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
            await asyncio.sleep(3)
            
            self.current_symbol = symbol
            logger.info(f"✅ Changed to {symbol}")
            return {"status": "ok", "symbol": symbol}
        except Exception as e:
            logger.error(f"Error: {e}")
            return {"status": "error", "message": str(e)}
            
    async def add_to_watchlist(self, symbol: str):
        """Add symbol to watchlist in dedicated browser"""
        if not self.page:
            return {"status": "error", "message": "Browser not started"}
            
        logger.info(f"⭐ Adding {symbol} to watchlist...")
        
        try:
            # Look for watchlist add button
            # TradingPro has watchlist on the left sidebar
            add_btn = await self.page.query_selector('[data-name="add-symbol-button"]')
            if add_btn:
                await add_btn.click()
                await asyncio.sleep(0.5)
                
                # Type symbol
                await self.page.keyboard.type(symbol)
                await asyncio.sleep(0.5)
                await self.page.keyboard.press('Enter')
                await asyncio.sleep(1)
                
                logger.info(f"✅ Added {symbol} to watchlist")
                return {"status": "ok", "symbol": symbol, "action": "added_to_watchlist"}
            else:
                # Alternative: use keyboard shortcut
                await self.page.keyboard.press('Alt+Insert')  # Common TV shortcut
                await asyncio.sleep(0.5)
                await self.page.keyboard.type(symbol)
                await asyncio.sleep(0.5)
                await self.page.keyboard.press('Enter')
                
                return {"status": "ok", "symbol": symbol, "action": "added_via_shortcut"}
        except Exception as e:
            logger.error(f"Watchlist error: {e}")
            return {"status": "error", "message": str(e)}
            
    async def get_chart_data(self) -> dict:
        """Extract chart data"""
        if not self.page:
            return {}
            
        try:
            # Get price
            price_elem = await self.page.query_selector('[data-name="legend-series-item"] .valueValue-G1h3ZX4F')
            price = 0
            if price_elem:
                price_text = await price_elem.inner_text()
                price = float(price_text.replace(',', '').replace('$', ''))
                
            # Get indicators
            indicators = {}
            items = await self.page.query_selector_all('[data-name="legend-source-item"]')
            for item in items:
                try:
                    name_el = await item.query_selector('[class*="title"]')
                    val_el = await item.query_selector('[class*="valueValue"]')
                    if name_el and val_el:
                        name = await name_el.inner_text()
                        val = await val_el.inner_text()
                        indicators[name] = val
                except:
                    pass
                    
            return {
                "symbol": self.current_symbol,
                "price": price,
                "indicators": indicators,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Data extraction error: {e}")
            return {"symbol": self.current_symbol, "price": 0, "indicators": {}}
            
    async def _monitor_loop(self):
        """Background price monitoring"""
        while self.connected:
            try:
                data = await self.get_chart_data()
                if data.get('price', 0) > 0:
                    self.current_price = data['price']
                    
                # Log every 60 seconds
                if int(datetime.now().timestamp()) % 60 == 0:
                    logger.info(f"📊 {self.current_symbol or 'Waiting...'} @ ${self.current_price:,.2f}")
                    
                await asyncio.sleep(2)
            except Exception:
                await asyncio.sleep(5)
                
    async def take_screenshot(self, path: str = "/tmp/tv_screenshot.png"):
        """Take screenshot"""
        if self.page:
            await self.page.screenshot(path=path)
            return {"status": "ok", "path": path}
        return {"status": "error", "message": "No page"}
        
    async def get_status(self) -> dict:
        return {
            "connected": self.connected,
            "browser": "Dedicated Chromium",
            "symbol": self.current_symbol,
            "price": self.current_price,
            "url": self.tv_url
        }
        
    async def stop(self):
        """Stop and close dedicated browser"""
        logger.info("🛑 Stopping dedicated browser")
        self.connected = False
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()


# HTTP API
from aiohttp import web


async def start_api(controller: DedicatedTVController, port: int = 8085):
    app = web.Application()
    
    async def status(request):
        return web.json_response(await controller.get_status())
        
    async def symbol(request):
        data = await request.json()
        sym = data.get('symbol', '')
        result = await controller.change_symbol(sym)
        return web.json_response(result)
        
    async def watchlist_add(request):
        """Add to watchlist - BONUS FEATURE"""
        data = await request.json()
        sym = data.get('symbol', '')
        result = await controller.add_to_watchlist(sym)
        return web.json_response(result)
        
    async def chart(request):
        data = await controller.get_chart_data()
        return web.json_response(data)
        
    async def screenshot(request):
        result = await controller.take_screenshot()
        return web.json_response(result)
    
    app.router.add_get('/status', status)
    app.router.add_post('/symbol', symbol)
    app.router.add_post('/watchlist/add', watchlist_add)  # BONUS!
    app.router.add_get('/chart', chart)
    app.router.add_get('/screenshot', screenshot)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    logger.info(f"🌐 Dedicated TV API on port {port}")
    logger.info("   POST /watchlist/add  - Add symbol to watchlist ⭐")
    return runner


async def main():
    controller = DedicatedTVController()
    
    try:
        # Start dedicated browser (not headless so you can login)
        await controller.start(headless=False)
        
        # Start API
        await start_api(controller, port=8085)
        
        logger.info("")
        logger.info("═══════════════════════════════════════════════════════════")
        logger.info("  ✅ DEDICATED TRADINGVIEW BROWSER - FULLY ISOLATED")
        logger.info("═══════════════════════════════════════════════════════════")
        logger.info("")
        logger.info("🌐 A SEPARATE browser window is now open with TradingView")
        logger.info("   Your main Chrome is FREE - work without disruption!")
        logger.info("")
        logger.info("📊 API: http://localhost:8085")
        logger.info("")
        logger.info("Endpoints:")
        logger.info("  POST /symbol         - Change symbol")
        logger.info("  POST /watchlist/add  - Add to watchlist ⭐ BONUS!")
        logger.info("  GET  /chart          - Get price & indicators")
        logger.info("  GET  /screenshot     - Take screenshot")
        logger.info("")
        logger.info("Press Ctrl+C to stop")
        logger.info("")
        
        # Keep running
        while controller.connected:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("\n👋 Shutting down...")
    finally:
        await controller.stop()


if __name__ == "__main__":
    asyncio.run(main())
