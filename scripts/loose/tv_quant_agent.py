#!/usr/bin/env python3
"""
Sapphire AI - TradingView Quantitative Agent
Full autonomous control of existing logged-in TV session
Uses AppleScript to control Chrome without restarting
"""

import asyncio
import json
import logging
import subprocess
import time
from datetime import datetime

from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)


class TVQuantAgent:
    """
    Advanced quantitative agent for TradingView
    Connects to existing Chrome session via AppleScript
    """
    
    def __init__(self):
        self.browser_type = "Chrome"
        self.tv_url = "https://www.tradingview.com/chart/"
        self.current_symbol = ""
        self.price_history = []
        self.indicator_data = {}
        self.news_cache = []
        self.strategy_results = {}
        self.active = True
        
    def run_applescript(self, script: str) -> str:
        """Execute AppleScript to control Chrome"""
        try:
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.stdout.strip()
        except Exception as e:
            logger.error(f"AppleScript error: {e}")
            return ""
            
    def get_active_url(self) -> str:
        """Get current URL from Chrome"""
        script = '''
        tell application "Google Chrome"
            get URL of active tab of front window
        end tell
        '''
        return self.run_applescript(script)
        
    def navigate_to(self, url: str):
        """Navigate to URL in existing Chrome"""
        script = f'''
        tell application "Google Chrome"
            set URL of active tab of front window to "{url}"
        end tell
        '''
        self.run_applescript(script)
        logger.info(f"🌐 Navigated to: {url}")
        time.sleep(3)  # Wait for load
        
    def execute_js(self, js_code: str) -> str:
        """Execute JavaScript in active tab"""
        # Escape quotes for AppleScript
        escaped_js = js_code.replace('"', '\\"').replace("'", "\\'")
        script = f'''
        tell application "Google Chrome"
            execute front window's active tab javascript "{escaped_js}"
        end tell
        '''
        return self.run_applescript(script)
        
    def click_at(self, x: int, y: int):
        """Click at screen coordinates"""
        script = f'''
        tell application "System Events"
            tell process "Google Chrome"
                click at {{{x}, {y}}}
            end tell
        end tell
        '''
        self.run_applescript(script)
        
    def type_text(self, text: str):
        """Type text"""
        script = f'''
        tell application "System Events"
            keystroke "{text}"
        end tell
        '''
        self.run_applescript(script)
        
    def press_key(self, key: str):
        """Press a key"""
        script = f'''
        tell application "System Events"
            key code {self._key_code(key)}
        end tell
        '''
        self.run_applescript(script)
        
    def _key_code(self, key: str) -> int:
        """Get Apple key code"""
        codes = {
            'return': 36, 'enter': 36, 'esc': 53,
            'up': 126, 'down': 125, 'left': 123, 'right': 124,
            'space': 49, 'tab': 48
        }
        return codes.get(key.lower(), 0)
        
    # ═══════════════════════════════════════════════════════════════
    # TECHNICAL ANALYSIS
    # ═══════════════════════════════════════════════════════════════
    
    async def get_chart_data(self) -> dict:
        """Extract comprehensive chart data via JavaScript"""
        js = """
        (function() {
            const data = {
                symbol: '',
                price: 0,
                change: 0,
                changePercent: 0,
                timeframe: '',
                indicators: {}
            };
            
            // Try to get symbol from URL or page
            const match = window.location.pathname.match(/chart\/[^/]+\/([^/]+)/);
            if (match) data.symbol = match[1];
            
            // Look for price in DOM
            const priceElems = document.querySelectorAll('[class*="priceValue"], [class*="valueValue"]');
            priceElems.forEach(el => {
                const text = el.textContent.replace(/[$,]/g, '');
                const val = parseFloat(text);
                if (val > 0 && !data.price) data.price = val;
            });
            
            // Get indicator values from legend
            const legendItems = document.querySelectorAll('[data-name="legend-source-item"]');
            legendItems.forEach(item => {
                const nameEl = item.querySelector('[class*="title"]');
                const valEl = item.querySelector('[class*="value"]');
                if (nameEl && valEl) {
                    data.indicators[nameEl.textContent.trim()] = valEl.textContent.trim();
                }
            });
            
            return JSON.stringify(data);
        })();
        """
        
        try:
            result = self.execute_js(js)
            if result and result.startswith('{'):
                return json.loads(result)
        except Exception as e:
            logger.error(f"Chart data error: {e}")
            
        return {"symbol": "", "price": 0, "indicators": {}}
        
    async def add_indicator(self, indicator_name: str, params: dict = None):
        """Add technical indicator to chart"""
        logger.info(f"📊 Adding indicator: {indicator_name}")
        
        # Open indicator search
        self.execute_js('document.querySelector(\'[data-name="indicator-search-button"]\')?.click()')
        await asyncio.sleep(1)
        
        # Type indicator name
        self.type_text(indicator_name)
        await asyncio.sleep(0.5)
        
        # Press enter to select
        self.press_key('return')
        await asyncio.sleep(2)
        
        logger.info(f"✅ Added {indicator_name}")
        
    async def change_symbol(self, symbol: str):
        """Change chart symbol"""
        logger.info(f"📈 Changing symbol to: {symbol}")
        
        # Click symbol button
        self.execute_js('document.querySelector(\'[data-name="symbol-search-button"]\')?.click()')
        await asyncio.sleep(0.5)
        
        # Clear and type new symbol
        self.execute_js('document.querySelector(\'[data-name="symbol-search-input"] input\')?.select()')
        self.type_text(symbol)
        await asyncio.sleep(0.5)
        
        # Press enter
        self.press_key('return')
        await asyncio.sleep(3)
        
        self.current_symbol = symbol
        logger.info(f"✅ Symbol changed to {symbol}")
        
    async def change_timeframe(self, tf: str):
        """Change timeframe (1m, 5m, 15m, 1H, 4H, 1D, 1W, 1M)"""
        logger.info(f"⏱️  Changing timeframe to: {tf}")
        
        # Click timeframe
        self.execute_js('document.querySelector(\'[data-name="interval-dialog-button"]\')?.click()')
        await asyncio.sleep(0.5)
        
        # Click specific timeframe
        js = f"document.querySelector('button:contains(\"{tf}\")')?.click() || document.evaluate(\"//button[contains(text(), '{tf}')]\", document).iterateNext()?.click()"
        self.execute_js(js)
        await asyncio.sleep(1)
        
        logger.info(f"✅ Timeframe changed to {tf}")
        
    # ═══════════════════════════════════════════════════════════════
    # NEWS & SENTIMENT
    # ═══════════════════════════════════════════════════════════════
    
    async def fetch_news(self, symbol: str = None) -> list[dict]:
        """Fetch news for symbol"""
        if symbol:
            await self.change_symbol(symbol)
            
        logger.info("📰 Fetching news...")
        
        # Open news panel
        self.execute_js('document.querySelector(\'[data-name="news-button"]\')?.click()')
        await asyncio.sleep(2)
        
        # Extract news via JS
        js = """
        (function() {
            const news = [];
            const items = document.querySelectorAll('[data-name="news-item"], .news-item, [class*="news"]');
            items.forEach((item, i) => {
                if (i < 10) {
                    const title = item.querySelector('h1, h2, h3, [class*="title"]')?.textContent?.trim() || '';
                    const source = item.querySelector('[class*="source"]')?.textContent?.trim() || '';
                    const time = item.querySelector('[class*="time"]')?.textContent?.trim() || '';
                    if (title) news.push({title, source, time});
                }
            });
            return JSON.stringify(news);
        })();
        """
        
        try:
            result = self.execute_js(js)
            news = json.loads(result) if result else []
            self.news_cache = news
            logger.info(f"✅ Fetched {len(news)} news items")
            return news
        except Exception as e:
            logger.error(f"News fetch error: {e}")
            return []
            
    async def analyze_sentiment(self, symbol: str = None) -> dict:
        """Analyze sentiment from news and technicals"""
        news = await self.fetch_news(symbol) if symbol else self.news_cache
        chart = await self.get_chart_data()
        
        # Simple sentiment analysis
        bullish_keywords = ['bull', 'rally', 'surge', 'gain', 'up', 'breakout', 'moon']
        bearish_keywords = ['bear', 'crash', 'dump', 'fall', 'down', 'breakdown', 'tank']
        
        bullish_count = 0
        bearish_count = 0
        
        for item in news:
            title = item.get('title', '').lower()
            for word in bullish_keywords:
                if word in title:
                    bullish_count += 1
            for word in bearish_keywords:
                if word in title:
                    bearish_count += 1
                    
        sentiment = "neutral"
        if bullish_count > bearish_count * 1.5:
            sentiment = "bullish"
        elif bearish_count > bullish_count * 1.5:
            sentiment = "bearish"
            
        return {
            "symbol": symbol or self.current_symbol,
            "sentiment": sentiment,
            "bullish_mentions": bullish_count,
            "bearish_mentions": bearish_count,
            "news_count": len(news),
            "technical_bias": self._calculate_technical_bias(chart),
            "timestamp": datetime.now().isoformat()
        }
        
    def _calculate_technical_bias(self, chart: dict) -> str:
        """Calculate technical bias from indicator data"""
        indicators = chart.get('indicators', {})
        
        # Check RSI if available
        for name, value in indicators.items():
            if 'rsi' in name.lower():
                try:
                    rsi = float(value)
                    if rsi > 70:
                        return "overbought"
                    elif rsi < 30:
                        return "oversold"
                except:
                    pass
                    
        return "neutral"
        
    # ═══════════════════════════════════════════════════════════════
    # STRATEGY TESTING & BENCHMARKING
    # ═══════════════════════════════════════════════════════════════
    
    async def test_strategy(self, strategy_config: dict) -> dict:
        """Test a strategy configuration"""
        name = strategy_config.get('name', 'Unnamed')
        logger.info(f"🧪 Testing strategy: {name}")
        
        # Navigate to strategy tester
        tester_url = f"https://www.tradingview.com/chart/?strategy={name}"
        self.navigate_to(tester_url)
        await asyncio.sleep(5)
        
        # Extract backtest results
        js = """
        (function() {
            const results = {
                netProfit: 0,
                profitFactor: 0,
                percentProfitable: 0,
                totalTrades: 0,
                maxDrawdown: 0
            };
            
            // Look for performance metrics in DOM
            const metrics = document.querySelectorAll('[class*="metric"], [class*="performance"]');
            metrics.forEach(el => {
                const text = el.textContent;
                if (text.includes('Net Profit')) {
                    const match = text.match(/[-+]?[\\d,.]+/);
                    if (match) results.netProfit = parseFloat(match[0].replace(/,/g, ''));
                }
                if (text.includes('Profit Factor')) {
                    const match = text.match(/[\\d.]+/);
                    if (match) results.profitFactor = parseFloat(match[0]);
                }
            });
            
            return JSON.stringify(results);
        })();
        """
        
        try:
            result = self.execute_js(js)
            results = json.loads(result) if result else {}
            
            self.strategy_results[name] = {
                "config": strategy_config,
                "results": results,
                "tested_at": datetime.now().isoformat()
            }
            
            logger.info(f"✅ Strategy tested: {results}")
            return results
        except Exception as e:
            logger.error(f"Strategy test error: {e}")
            return {}
            
    async def load_community_script(self, script_url: str) -> bool:
        """Load a community Pine Script"""
        logger.info(f"📜 Loading community script: {script_url}")
        
        # Navigate to script page
        self.navigate_to(script_url)
        await asyncio.sleep(3)
        
        # Click "Make a copy" or similar
        js = """
        (function() {
            const buttons = document.querySelectorAll('button');
            for (let btn of buttons) {
                if (btn.textContent.includes('Copy') || btn.textContent.includes('Add')) {
                    btn.click();
                    return 'clicked';
                }
            }
            return 'not found';
        })();
        """
        
        result = self.execute_js(js)
        await asyncio.sleep(2)
        
        logger.info(f"✅ Script loaded: {result}")
        return result == 'clicked'
        
    async def run_quantitative_benchmark(self, symbols: list[str], strategies: list[str]) -> dict:
        """Run comprehensive benchmark across symbols and strategies"""
        logger.info(f"📊 Running benchmark on {len(symbols)} symbols, {len(strategies)} strategies")
        
        benchmark_results = {
            "timestamp": datetime.now().isoformat(),
            "symbols_tested": [],
            "strategy_results": {},
            "best_performers": []
        }
        
        for symbol in symbols:
            await self.change_symbol(symbol)
            await asyncio.sleep(2)
            
            chart_data = await self.get_chart_data()
            sentiment = await self.analyze_sentiment()
            
            benchmark_results["symbols_tested"].append({
                "symbol": symbol,
                "price": chart_data.get('price'),
                "sentiment": sentiment.get('sentiment'),
                "indicators": list(chart_data.get('indicators', {}).keys())
            })
            
        for strategy in strategies:
            results = await self.test_strategy({"name": strategy})
            benchmark_results["strategy_results"][strategy] = results
            
        # Find best performers
        sorted_strategies = sorted(
            benchmark_results["strategy_results"].items(),
            key=lambda x: x[1].get('netProfit', 0),
            reverse=True
        )
        benchmark_results["best_performers"] = [
            {"name": name, "profit": data.get('netProfit')}
            for name, data in sorted_strategies[:3]
        ]
        
        self.strategy_results['benchmark'] = benchmark_results
        logger.info(f"✅ Benchmark complete. Best: {benchmark_results['best_performers']}")
        
        return benchmark_results
        
    async def get_status(self) -> dict:
        """Get agent status"""
        current_url = self.get_active_url()
        chart_data = await self.get_chart_data()
        
        return {
            "active": self.active,
            "browser": self.browser_type,
            "current_url": current_url,
            "symbol": chart_data.get('symbol', self.current_symbol),
            "price": chart_data.get('price', 0),
            "indicators": chart_data.get('indicators', {}),
            "strategies_tested": len(self.strategy_results),
            "news_cached": len(self.news_cache)
        }
        
    async def stop(self):
        """Stop the agent"""
        self.active = False
        logger.info("🛑 Quant agent stopped")


# ═══════════════════════════════════════════════════════════════
# HTTP API SERVER
# ═══════════════════════════════════════════════════════════════

async def start_quant_api(agent: TVQuantAgent, port: int = 8084):
    """Start API server for quant agent"""
    
    app = web.Application()
    
    async def status(request):
        return web.json_response(await agent.get_status())
        
    async def chart_data(request):
        data = await agent.get_chart_data()
        return web.json_response(data)
        
    async def change_symbol(request):
        data = await request.json()
        symbol = data.get('symbol', '')
        if symbol:
            await agent.change_symbol(symbol)
            return web.json_response({"status": "ok", "symbol": symbol})
        return web.json_response({"error": "No symbol"}, status=400)
        
    async def add_indicator_endpoint(request):
        data = await request.json()
        indicator = data.get('indicator', 'EMA')
        await agent.add_indicator(indicator)
        return web.json_response({"status": "ok", "indicator": indicator})
        
    async def news(request):
        symbol = request.query.get('symbol')
        news_data = await agent.fetch_news(symbol)
        return web.json_response({"news": news_data, "count": len(news_data)})
        
    async def sentiment(request):
        symbol = request.query.get('symbol')
        sentiment_data = await agent.analyze_sentiment(symbol)
        return web.json_response(sentiment_data)
        
    async def test_strategy_endpoint(request):
        data = await request.json()
        results = await agent.test_strategy(data)
        return web.json_response(results)
        
    async def benchmark(request):
        data = await request.json()
        symbols = data.get('symbols', ['BTCUSDT', 'ETHUSDT'])
        strategies = data.get('strategies', ['EMA Cross', 'RSI Strategy'])
        results = await agent.run_quantitative_benchmark(symbols, strategies)
        return web.json_response(results)
        
    async def strategies(request):
        return web.json_response({
            "tested": list(agent.strategy_results.keys()),
            "count": len(agent.strategy_results)
        })
    
    # Routes
    app.router.add_get('/status', status)
    app.router.add_get('/chart', chart_data)
    app.router.add_post('/symbol', change_symbol)
    app.router.add_post('/indicator', add_indicator_endpoint)
    app.router.add_get('/news', news)
    app.router.add_get('/sentiment', sentiment)
    app.router.add_post('/strategy/test', test_strategy_endpoint)
    app.router.add_post('/benchmark', benchmark)
    app.router.add_get('/strategies', strategies)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    logger.info(f"🌐 Quant API server started on port {port}")
    return runner


async def main():
    """Main entry"""
    agent = TVQuantAgent()
    
    try:
        # Check if we're on TradingView
        current_url = agent.get_active_url()
        logger.info(f"📍 Current URL: {current_url}")
        
        if 'tradingview.com' not in current_url:
            logger.info("Navigating to TradingView...")
            agent.navigate_to(agent.tv_url)
            await asyncio.sleep(5)
        else:
            logger.info("✅ Already on TradingView")
            
        # Start API
        api = await start_quant_api(agent, port=8084)
        
        logger.info("")
        logger.info("═══════════════════════════════════════════════════════════")
        logger.info("  🚀 SAPPHIRE AI QUANT AGENT - FULLY OPERATIONAL")
        logger.info("═══════════════════════════════════════════════════════════")
        logger.info("")
        logger.info("Using existing Chrome session (you stay logged in)")
        logger.info("")
        logger.info("📊 Quantitative Analysis API: http://localhost:8084")
        logger.info("")
        logger.info("Endpoints:")
        logger.info("  GET  /status           - Agent status")
        logger.info("  GET  /chart            - Current chart data")
        logger.info("  POST /symbol           - Change symbol {symbol: 'BTCUSDT'}")
        logger.info("  POST /indicator        - Add indicator {indicator: 'RSI'}")
        logger.info("  GET  /news?symbol=XXX  - Fetch news")
        logger.info("  GET  /sentiment        - Sentiment analysis")
        logger.info("  POST /strategy/test    - Test strategy")
        logger.info("  POST /benchmark        - Run benchmark")
        logger.info("  GET  /strategies       - List tested strategies")
        logger.info("")
        logger.info("Press Ctrl+C to stop")
        logger.info("")
        
        # Keep running
        while agent.active:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("\n👋 Shutting down...")
    finally:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
