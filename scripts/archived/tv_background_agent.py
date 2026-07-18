#!/usr/bin/env python3
"""
Sapphire AI - Background TradingView Agent
Controls TV WITHOUT bringing Chrome to foreground or interrupting your work
Uses background tab manipulation via AppleScript (no activate/foreground)
"""

import asyncio
import json
import logging
import subprocess

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


class BackgroundTVAgent:
    """
    Controls TradingView WITHOUT interrupting your work
    - No window activation
    - No foreground stealing
    - Background tab manipulation only
    """

    def __init__(self):
        self.tv_url = "https://www.tradingview.com/chart/"
        self.current_symbol = ""

    def run_applescript_silent(self, script: str) -> str:
        """Run AppleScript WITHOUT activating/bringing to front"""
        try:
            result = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True, timeout=30
            )
            return result.stdout.strip()
        except Exception as e:
            logger.error(f"AppleScript error: {e}")
            return ""

    def find_tv_tab(self) -> int | None:
        """Find TradingView tab index WITHOUT activating"""
        script = """
        tell application "Google Chrome"
            set tabList to {}
            set windowList to every window
            repeat with win in windowList
                set tabIndex to 1
                repeat with t in (tabs of win)
                    set tabURL to URL of t
                    if tabURL contains "tradingview.com" then
                        return (id of win as string) & "," & tabIndex
                    end if
                    set tabIndex to tabIndex + 1
                end repeat
            end repeat
            return ""
        end tell
        """
        result = self.run_applescript_silent(script)
        if result and "," in result:
            parts = result.split(",")
            return {"window_id": parts[0], "tab_index": int(parts[1])}
        return None

    def execute_js_in_background(self, js_code: str) -> str:
        """Execute JS in TV tab WITHOUT bringing Chrome to front"""
        # Escape the JS for AppleScript
        escaped_js = js_code.replace('"', '\\"').replace("'", "\\'")

        script = f'''
        tell application "Google Chrome"
            -- Find TV tab without activating
            set tvTab to missing value
            repeat with win in windows
                repeat with t in (tabs of win)
                    if URL of t contains "tradingview.com" then
                        set tvTab to t
                        exit repeat
                    end if
                end repeat
                if tvTab is not missing value then exit repeat
            end repeat
            
            if tvTab is not missing value then
                tell tvTab
                    set result to execute javascript "{escaped_js}"
                    return result
                end tell
            else
                return "TV tab not found"
            end if
        end tell
        '''

        return self.run_applescript_silent(script)

    async def change_symbol_background(self, symbol: str) -> dict:
        """Change symbol WITHOUT interrupting your work"""
        logger.info(f"📊 [BACKGROUND] Changing symbol to: {symbol}")

        # Use JS to click elements without window activation
        js = f'''
        (function() {{
            // Find and click symbol button
            var btn = document.querySelector('[data-name="symbol-search-button"]');
            if (btn) {{
                btn.click();
                setTimeout(function() {{
                    var input = document.querySelector('[data-name="symbol-search-input"] input');
                    if (input) {{
                        input.value = "{symbol}";
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        setTimeout(function() {{
                            // Press enter
                            var event = new KeyboardEvent('keydown', {{
                                key: 'Enter',
                                keyCode: 13,
                                bubbles: true
                            }});
                            input.dispatchEvent(event);
                        }}, 500);
                    }}
                }}, 500);
                return 'clicked';
            }}
            return 'button_not_found';
        }})();
        '''

        result = self.execute_js_in_background(js)
        self.current_symbol = symbol

        await asyncio.sleep(3)  # Wait for load

        return {"status": "ok", "symbol": symbol, "method": "background_js", "result": result}

    async def add_to_watchlist_background(self, symbol: str) -> dict:
        """Add to watchlist WITHOUT interrupting work"""
        logger.info(f"⭐ [BACKGROUND] Adding {symbol} to watchlist")

        # Use keyboard shortcut approach via JS
        js = f'''
        (function() {{
            // Try Alt+Insert shortcut for add symbol
            var event = new KeyboardEvent('keydown', {{
                altKey: true,
                key: 'Insert',
                keyCode: 45,
                bubbles: true
            }});
            document.dispatchEvent(event);
            
            setTimeout(function() {{
                // Type symbol
                var inputs = document.querySelectorAll('input');
                for (var i = 0; i < inputs.length; i++) {{
                    if (inputs[i].offsetParent !== null) {{
                        inputs[i].value = "{symbol}";
                        inputs[i].dispatchEvent(new Event('input', {{ bubbles: true }}));
                        
                        setTimeout(function() {{
                            var enterEvent = new KeyboardEvent('keydown', {{
                                key: 'Enter',
                                keyCode: 13,
                                bubbles: true
                            }});
                            inputs[i].dispatchEvent(enterEvent);
                        }}, 500);
                        break;
                    }}
                }}
            }}, 500);
            
            return 'shortcut_sent';
        }})();
        '''

        result = self.execute_js_in_background(js)
        await asyncio.sleep(2)

        return {"status": "ok", "symbol": symbol, "action": "add_to_watchlist", "result": result}

    async def get_price_background(self) -> dict:
        """Get price WITHOUT activating window"""
        js = """
        (function() {
            var data = {price: 0, symbol: ''};
            
            // Try to get price from various selectors
            var selectors = [
                '[data-name="legend-series-item"] .valueValue-G1h3ZX4F',
                '.chart-gui-wrapper .priceValue',
                '[class*="priceValue"]',
                '[class*="valueValue"]'
            ];
            
            for (var i = 0; i < selectors.length; i++) {
                var el = document.querySelector(selectors[i]);
                if (el) {
                    var text = el.textContent.replace(/[$,]/g, '');
                    var val = parseFloat(text);
                    if (val > 0) {
                        data.price = val;
                        break;
                    }
                }
            }
            
            // Get symbol from URL or page
            var match = window.location.pathname.match(/chart\/[^/]+\/([^/]+)/);
            if (match) data.symbol = match[1];
            
            return JSON.stringify(data);
        })();
        """

        result = self.execute_js_in_background(js)
        try:
            if result and result.startswith("{"):
                return json.loads(result)
        except:
            pass
        return {"price": 0, "symbol": ""}

    async def get_status(self) -> dict:
        tv_tab = self.find_tv_tab()
        price_data = await self.get_price_background()

        return {
            "active": True,
            "mode": "background",
            "tv_tab_found": tv_tab is not None,
            "current_symbol": price_data.get("symbol", self.current_symbol),
            "price": price_data.get("price", 0),
            "note": "Running silently without interrupting your work",
        }

    async def start_monitoring(self):
        """Background monitoring loop"""
        logger.info("👻 [BACKGROUND AGENT] Started - won't interrupt your work!")

        while True:
            try:
                # Silently get price every 30 seconds
                data = await self.get_price_background()
                if data.get("price", 0) > 0:
                    logger.debug(f"Price update: ${data['price']}")
                await asyncio.sleep(30)
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(60)


# HTTP API
from aiohttp import web


async def start_api(agent: BackgroundTVAgent, port: int = 8086):
    app = web.Application()

    async def status(request):
        return web.json_response(await agent.get_status())

    async def symbol(request):
        data = await request.json()
        sym = data.get("symbol", "")
        result = await agent.change_symbol_background(sym)
        return web.json_response(result)

    async def watchlist_add(request):
        """BONUS: Add to watchlist"""
        data = await request.json()
        sym = data.get("symbol", "")
        result = await agent.add_to_watchlist_background(sym)
        return web.json_response(result)

    async def price(request):
        data = await agent.get_price_background()
        return web.json_response(data)

    app.router.add_get("/status", status)
    app.router.add_post("/symbol", symbol)
    app.router.add_post("/watchlist/add", watchlist_add)  # BONUS!
    app.router.add_get("/price", price)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logger.info(f"🌐 Background Agent API on port {port}")
    logger.info("   This agent works SILENTLY - won't steal focus!")
    return runner


async def main():
    agent = BackgroundTVAgent()

    try:
        # Check if TV tab exists
        tv_tab = agent.find_tv_tab()
        if tv_tab:
            logger.info("✅ Found TradingView tab in background")
        else:
            logger.warning("⚠️  TradingView tab not found - please open tradingview.com/chart")

        # Start API
        await start_api(agent, port=8086)

        # Start background monitoring
        monitor_task = asyncio.create_task(agent.start_monitoring())

        logger.info("")
        logger.info("═══════════════════════════════════════════════════════════")
        logger.info("  👻 BACKGROUND TRADINGVIEW AGENT - ZERO INTERRUPTION")
        logger.info("═══════════════════════════════════════════════════════════")
        logger.info("")
        logger.info("✅ This agent controls TV WITHOUT:")
        logger.info("   • Bringing Chrome to front")
        logger.info("   • Stealing window focus")
        logger.info("   • Interrupting your work")
        logger.info("")
        logger.info("📊 API: http://localhost:8086")
        logger.info("")
        logger.info("Endpoints:")
        logger.info("  POST /symbol         - Change symbol (silently)")
        logger.info("  POST /watchlist/add  - Add to watchlist ⭐ BONUS!")
        logger.info("  GET  /price          - Get current price")
        logger.info("  GET  /status         - Agent status")
        logger.info("")
        logger.info("Keep working - the agent runs in background!")
        logger.info("")

        # Keep running
        await asyncio.gather(monitor_task)

    except KeyboardInterrupt:
        logger.info("\n👋 Shutting down background agent...")


if __name__ == "__main__":
    asyncio.run(main())
