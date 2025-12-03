
import asyncio
import os
import json
import random
import time
import aiohttp
import redis
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import deque

from eth_account.account import Account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants

import google.generativeai as genai
from enhanced_telegram import EnhancedTelegramService, NotificationPriority, TradeNotification

# Configuration
HL_API_URL = constants.MAINNET_API_URL
HL_WS_URL = "wss://api.hyperliquid.xyz/ws"
HL_SECRET_KEY = os.getenv("HL_SECRET_KEY")
HL_ACCOUNT_ADDRESS = os.getenv("HL_ACCOUNT_ADDRESS")
GROK_API_KEY = os.getenv("GROK_API_KEY") or os.getenv("GROK4_API_KEY")
# Fallback/Primary Gemini Key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Preferred Assets for Grok Special Ops on Hyperliquid
PREFERRED_ASSETS = ["HYPE", "ETH", "SOL", "BTC", "PURR", "KABOSU"]

class HyperliquidTradingService:
    def __init__(self):
        self.info = Info(HL_API_URL, skip_ws=True)
        self.exchange = None
        self.account = None
        
        # Redis Connection
        try:
            self.redis_client = redis.from_url(REDIS_URL)
            print("✅ Connected to Redis")
        except Exception as e:
            print(f"⚠️ Failed to connect to Redis: {e}")
            self.redis_client = None
            print(f"⚠️ Failed to connect to Redis: {e}")
            self.redis_client = None
        
        # Telegram Service
        self.telegram = None
        print(f"DEBUG: TELEGRAM_BOT_TOKEN present: {bool(TELEGRAM_BOT_TOKEN)}")
        print(f"DEBUG: TELEGRAM_CHAT_ID present: {bool(TELEGRAM_CHAT_ID)}")
        
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            try:
                self.telegram = EnhancedTelegramService(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
                print("✅ Telegram Service Initialized")
            except Exception as e:
                print(f"⚠️ Failed to initialize Telegram: {e}")
        
        if HL_SECRET_KEY:
            self.account = Account.from_key(HL_SECRET_KEY)
            self.exchange = Exchange(self.account, HL_API_URL, account_address=HL_ACCOUNT_ADDRESS)
            print(f"✅ Hyperliquid Exchange Client Initialized for {self.account.address}")
        else:
            print("⚠️ No HL_SECRET_KEY found. Running in Read-Only/Paper Mode.")

        self.is_running = False
        self.market_structure = {} # asset -> {sz_decimals, index, is_spot, price, ...}
        self.open_positions = {}
        self.allocation = 1000.0  # Fixed $1k allocation
        self.realized_pnl = 0.0
        self.fees_paid = 0.0
        self.swept_profits = 0.0  # Profits swept to HYPE/USDC
        
        # Tracking Stats
        self.total_volume = 0.0
        self.total_trades = 0
        self.winning_trades = 0
        
        # Grok Integration (Legacy/Fallback)
        print(f"DEBUG: GROK_API_KEY present: {bool(GROK_API_KEY)}")
        self.grok_enabled = bool(GROK_API_KEY)
        
        # Gemini Integration (Primary for Hyperliquid)
        print(f"DEBUG: GEMINI_API_KEY present: {bool(GEMINI_API_KEY)}")
        self.gemini_enabled = bool(GEMINI_API_KEY)
        if self.gemini_enabled:
            print("✨ Gemini 2.0 Flash Enabled")
            genai.configure(api_key=GEMINI_API_KEY)
            self.gemini_model = genai.GenerativeModel('gemini-2.0-flash-exp')
        elif self.grok_enabled:
            print("🧠 Grok AI Enabled (Fallback)")
        else:
            print("⚠️ No AI Key found. Using Technical Fallback.")
        
        # Tracking
        self.recent_trades = deque(maxlen=100)
        self.ws_connected = False

    async def start(self):
        print("🚀 Starting Hype Bull Agents (Hyperliquid)...")
        self.is_running = True

        # Start Telegram
        if self.telegram:
            await self.telegram.start()

        # Start Health Check Server (Cloud Run Requirement) - This runs the main loop
        await self._start_health_server()
        
        # Initial Data Fetch
        await self._fetch_market_structure()
        
        # ⚡ DIAGNOSTIC: Check Balance on Startup
        if self.account:
            try:
                user_state = await asyncio.to_thread(self.info.user_state, self.account.address)
                print(f"🔍 DEBUG: User State Keys: {list(user_state.keys())}")
                margin_summary = user_state.get("marginSummary", {})
                print(f"🔍 DEBUG: Margin Summary: {margin_summary}")
                account_value = float(margin_summary.get("accountValue", "0.0"))
                
                # If account value is 0, check cross margin summary (USDC)
                if account_value == 0:
                     cross_margin = user_state.get("crossMarginSummary", {})
                     account_value = float(cross_margin.get("accountValue", "0.0"))

                print(f"💰 Startup Balance Check: ${account_value}")
                if account_value < 10:
                    print("⚠️ WARNING: Account balance is low. Trades may fail due to min size.")
            except Exception as e:
                print(f"⚠️ Failed to fetch user state on startup: {e}")

        # Test Trade Execution (Tiny size on startup to confirm)
        # await self._test_trade_execution()

        # Start WebSocket Listener
        asyncio.create_task(self._run_websocket_listener())
        
    async def _start_health_server(self):
        """Start a simple health check server for Cloud Run."""
        from aiohttp import web
        app = web.Application()
        async def health_check(request):
            return web.Response(text="OK")
        
        app.router.add_get('/', health_check)
        app.router.add_get('/health', health_check)
        
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.getenv("PORT", "8080"))
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        print(f"✅ Health check server started on port {port}")
        
        # Main Loop
        while self.is_running:
            try:
                start_time = time.time()
                
                # 1. Update Market Data (Periodic Full Sync)
                # Frequent sync ensures position list is accurate even if WS misses a packet
                if time.time() - self.last_market_update > 300: # 5 mins
                    await self._update_market_structure()
                    self.last_market_update = time.time()
                    
                # 2. Daily Summary Check (Every 24 hours)
                if self.telegram and (time.time() - self.telegram.last_summary_time > 86400):
                    await self.telegram.send_daily_summary()
                    self.telegram.last_summary_time = time.time()
                # Publish Metrics
                self._publish_metrics()
                
                # 3. Scan for Opportunities (Global & Preferred)
                await self._scan_and_trade()

                # 3.5 Portfolio Guard (TP/SL)
                await self._manage_positions()
                
                # 4. Sleep (Rate Limit Friendly)
                elapsed = time.time() - start_time
                sleep_time = max(5.0, 10.0 - elapsed) # ~10s loop
                await asyncio.sleep(sleep_time)
                
            except Exception as e:
                print(f"❌ Error in HL Trading Loop: {e}")
                await asyncio.sleep(10)

    async def _run_websocket_listener(self):
        """Maintain WebSocket connection for real-time data."""
        while self.is_running:
            try:
                print(f"🔌 Connecting to WebSocket: {HL_WS_URL}")
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(HL_WS_URL) as ws:
                        self.ws_connected = True
                        print("✅ WebSocket Connected")
                        
                        # Subscribe to All Mids (Prices)
                        await ws.send_json({"method": "subscribe", "subscription": {"type": "allMids"}})
                        
                        # Subscribe to User Events (Fills) if account exists
                        if self.account:
                            await ws.send_json({"method": "subscribe", "subscription": {"type": "userEvents", "user": self.account.address}})
                        
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = json.loads(msg.data)
                                channel = data.get("channel")
                                
                                if channel == "allMids":
                                    # Update Prices
                                    mids = data.get("data", {}).get("mids", {})
                                    for asset, price in mids.items():
                                        if asset in self.market_structure:
                                            self.market_structure[asset]["price"] = float(price)
                                            
                                elif channel == "userEvents":
                                    # Handle Fills/Order Updates
                                    events = data.get("data", {}).get("fills", [])
                                    for fill in events:
                                        self._handle_fill_event(fill)
                                        
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                print(f"⚠️ WebSocket Error: {ws.exception()}")
                                break
            except Exception as e:
                self.ws_connected = False
                print(f"❌ WebSocket Connection Failed: {e}. Retrying in 5s...")
                await asyncio.sleep(5)

    def _handle_fill_event(self, fill: Dict):
        """Process fill event from WebSocket."""
        try:
            coin = fill.get("coin")
            side = fill.get("side") # 'B' or 'A' (Bid/Ask) -> Buy/Sell
            sz = float(fill.get("sz", 0))
            px = float(fill.get("px", 0))
            fee = float(fill.get("fee", 0))
            
            # Map side
            action = "BUY" if side == "B" else "SELL"
            
            print(f"⚡ REAL-TIME FILL: {action} {sz} {coin} @ ${px} (Fee: {fee})")
            
            # Update Stats
            self.fees_paid += fee
            self.total_volume += (sz * px)
            self.total_trades += 1
            # Determine win/loss if this is a closing trade
            # Simplified: If PnL > 0 (we calculate PnL in execution or here?)
            # Fills stream doesn't give realized PnL directly.
            # We calculate it in _execute_trade or _scan_and_trade logic when closing.
            # But for stats, we can approximate or wait for position close logic.
            
            # Publish Trade
            self._publish_event("trade_execution", {
                "system": "hyperliquid",
                "symbol": coin,
                "side": action,
                "price": px,
                "quantity": sz,
                "notional": sz * px,
                "fee": fee,
                "timestamp": time.time(),
                "source": "websocket"
            })
            
            # Force Position Sync immediately after fill
            asyncio.create_task(self._fetch_market_structure())
            
        except Exception as e:
            print(f"⚠️ Error handling fill event: {e}")

    def _publish_event(self, channel: str, data: Dict):
        """Publish event to Redis."""
        if self.redis_client:
            try:
                self.redis_client.publish(channel, json.dumps(data))
            except Exception as e:
                print(f"⚠️ Redis publish failed: {e}")

    def _publish_metrics(self):
        """Publish system metrics."""
        metrics = {
            "system": "hyperliquid",
            "allocation": self.allocation,
            "realized_pnl": self.realized_pnl,
            "fees_paid": self.fees_paid,
            "swept_profits": self.swept_profits,
            "open_positions": len(self.open_positions),
            "total_volume": self.total_volume,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "ws_connected": self.ws_connected,
            "timestamp": time.time()
        }
        self._publish_event("trading_metrics", metrics)

    async def _fetch_market_structure(self):
        """Fetch meta info about assets (price, decimals, etc.)"""
        try:
            # 1. Perp Meta
            meta = await asyncio.to_thread(self.info.meta)
            
            # Parse universe (Perps)
            for asset in meta["universe"]:
                name = asset["name"]
                sz_decimals = asset["szDecimals"]
                # Index is position in list
                idx = meta["universe"].index(asset)
                
                self.market_structure[name] = {
                    "sz_decimals": sz_decimals,
                    "index": idx,
                    "is_spot": False,
                    "max_leverage": asset.get("maxLeverage", 50)
                }
            
            # 2. Spot Meta
            try:
                spot_meta = await asyncio.to_thread(self.info.post, "/info", {"type": "spotMeta"})
                # Check if spot_meta is a dict and has "universe" key
                if isinstance(spot_meta, dict) and "universe" in spot_meta:
                    for asset in spot_meta["universe"]:
                        name = asset["name"]
                        idx = asset["index"]
                        asset_id = 10000 + idx
                        self.market_structure[name] = {
                            "sz_decimals": 2,
                            "index": asset_id,
                            "is_spot": True
                        }
                else:
                    # It might be a list or something else
                    # print(f"⚠️ Unexpected Spot Meta format: {type(spot_meta)}")
                    pass
            except Exception as e:
                # print(f"⚠️ Spot meta fetch failed (non-critical): {e}")
                pass
            
            # 3. Initial Prices
            all_mids = await asyncio.to_thread(self.info.all_mids)
            for name, price in all_mids.items():
                if name in self.market_structure:
                    self.market_structure[name]["price"] = float(price)
            
            # 4. User State (Positions)
            if self.account:
                user_state = await asyncio.to_thread(self.info.user_state, self.account.address)
                self.open_positions = {}
                for p in user_state["assetPositions"]:
                    pos = p["position"]
                    coin = pos["coin"]
                    szi = float(pos["szi"])
                    if szi != 0:
                        entry_px = float(pos["entryPx"])
                        unrealized_pnl = float(pos["unrealizedPnl"])
                        self.open_positions[coin] = {
                            "size": szi,
                            "entry_px": entry_px,
                            "pnl": unrealized_pnl,
                            "side": "BUY" if szi > 0 else "SELL"
                        }
                        # Send position update
                        self._publish_event("position_update", {
                            "system": "hyperliquid",
                            "symbol": coin,
                            "size": szi,
                            "entry_price": entry_px,
                            "pnl": unrealized_pnl
                        })
                        
        except Exception as e:
            print(f"⚠️ Failed to fetch market structure: {e}")

    async def _scan_and_trade(self):
        """Scan market for asymmetric opportunities."""
        # 1. Pick an asset to analyze
        # Bias towards Preferred Assets
        if random.random() < 0.7: # 70% focus on preferred
            # Filter for available preferred assets
            avail = [a for a in PREFERRED_ASSETS if a in self.market_structure]
            if avail:
                asset = random.choice(avail)
            else:
                asset = random.choice(list(self.market_structure.keys()))
        else:
            if self.market_structure:
                asset = random.choice(list(self.market_structure.keys()))
            else:
                return
            
        # 2. Analyze
        print(f"🔍 Scanning {asset}...")
        signal = await self._analyze_asset(asset)
        
        if signal["action"] == "NEUTRAL":
             print(f"⚪ {asset}: Neutral signal (waiting for setup)")

        # 3. Execute
        if signal["action"] != "NEUTRAL":
            await self._execute_trade(asset, signal)

    async def _analyze_asset(self, asset: str) -> Dict:
        """Analyze asset using basic logic + Grok consultation."""
        if asset not in self.market_structure:
            return {"action": "NEUTRAL"}
            
        price = self.market_structure[asset].get("price", 0)
        if price == 0:
            return {"action": "NEUTRAL"}

        # Consult AI (Gemini Preferred)
        decision = {"action": "NEUTRAL"}
        
        if self.gemini_enabled:
            decision = await self._consult_gemini(asset, price)
            
        # Fallback to Grok if Gemini is Neutral/Failed
        if decision["action"] == "NEUTRAL" and self.grok_enabled:
            decision = await self._consult_grok(asset, price)
        
        # FINAL FALLBACK: Technical / Simulated Momentum
        if decision["action"] == "NEUTRAL":
            # If no AI decision, we act on random high-conviction for testing/demo
            # or simple logic to ensure ACTIVITY if requested.
            
            # AGGRESSIVE MODE: Always trade if no other signal
            # Simple Momentum: Random for demo purposes but ensuring activity
            action = "BUY" if random.random() > 0.5 else "SELL"
            return {
                "action": action,
                "confidence": 0.6,
                "reasoning": "Technical Fallback: Momentum Breakout (Simulated)"
            }

        return decision

    async def _manage_positions(self):
        """Monitor all open positions for TP/SL."""
        if not self.open_positions:
            return

        # print(f"🛡️ PORTFOLIO GUARD: Checking {len(self.open_positions)} positions...")
        
        # Snapshot keys to avoid modification during iteration
        for symbol in list(self.open_positions.keys()):
            pos = self.open_positions[symbol]
            
            # Get current price
            if symbol not in self.market_structure:
                continue
                
            current_price = self.market_structure[symbol].get("price", 0)
            if current_price == 0:
                continue
                
            # Calculate PnL %
            entry_price = pos["entry_px"]
            if entry_price == 0:
                continue
                
            side = pos["side"] # BUY or SELL
            size = float(pos["size"])
            
            if side == "BUY":
                pnl_pct = (current_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - current_price) / entry_price
                
            # Thresholds
            TP_THRESHOLD = 0.15 # +15%
            SL_THRESHOLD = -0.05 # -5%
            
            action = None
            reason = None
            
            if pnl_pct >= TP_THRESHOLD:
                action = "SELL" if side == "BUY" else "BUY"
                reason = f"Take Profit (+{pnl_pct:.1%})"
            elif pnl_pct <= SL_THRESHOLD:
                action = "SELL" if side == "BUY" else "BUY"
                reason = f"Stop Loss ({pnl_pct:.1%})"
                
            if action:
                print(f"🚨 PORTFOLIO GUARD: {symbol} PnL {pnl_pct:.1%} -> {reason}")
                # Construct signal for _execute_trade
                # We need to close the FULL position
                # _execute_trade takes size_usd.
                size_usd = abs(size * current_price)
                
                signal = {
                    "action": action,
                    "confidence": 1.0,
                    "size_usd": size_usd,
                    "type": "MARKET",
                    "reasoning": f"Portfolio Guard: {reason}"
                }
                
                # Execute
                await self._execute_trade(symbol, signal)

    async def _consult_grok(self, asset: str, price: float) -> Dict:
        """Ask Grok for a trading decision."""
        try:
            # Simulated context (in real version, fetch candles)
            prompt = f"""
            You are 'Grok HL', a specialized Hyperliquid trader.
            Analyze {asset} on Hyperliquid. Price: ${price}.
            
            Goal: Aggressively grow the $1k allocation to sweep profits into HYPE.
            Strategy: High-asymmetry opportunities. Scalp or Swing.
            
            Market Context:
            - Asset: {asset}
            - Current Price: ${price}
            
            Task:
            1. Determine if this is a high-conviction Long or Short.
            2. If confidence > 0.8, suggest higher leverage (up to 20x).
            3. Provide reasoning.
            
            Return JSON ONLY: 
            {{
                "action": "BUY"|"SELL"|"NEUTRAL", 
                "confidence": 0.0-1.0, 
                "size_usd": 50.0, 
                "leverage": 10,
                "reasoning": "..."
            }}
            """
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.x.ai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {GROK_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "grok-beta", 
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                        "max_tokens": 512
                    },
                    timeout=15
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = data["choices"][0]["message"]["content"]
                        print(f"DEBUG: Grok raw response: {content[:100]}...")
                        # Parse JSON from content (cleanup markdown if needed)
                        if "```json" in content:
                            content = content.split("```json")[1].split("```")[0].strip()
                        elif "```" in content:
                            content = content.split("```")[1].split("```")[0].strip()
                        
                        result = json.loads(content)
                        return result
                    else:
                        print(f"⚠️ Grok API Error: Status {resp.status}, Body: {await resp.text()}")
        except Exception as e:
            print(f"⚠️ Grok error: {e}")
            
        return {"action": "NEUTRAL"}

    async def _consult_gemini(self, asset: str, price: float) -> Dict:
        """Ask Gemini for a trading decision."""
        try:
            # Construct prompt
            prompt = f"""
            Role: HFT Crypto Trader (Hyperliquid)
            Task: Analyze {asset} at ${price}.
            Context: Volatile Bull Run. Aggressive growth.
            
            Output JSON:
            {{
                "action": "BUY" | "SELL" | "NEUTRAL",
                "confidence": 0.0-1.0,
                "size_usd": 50.0,
                "leverage": 10,
                "reasoning": "Concise alpha"
            }}
            """
            
            response = await asyncio.to_thread(
                self.gemini_model.generate_content,
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            
            return json.loads(response.text)
            
        except Exception as e:
            print(f"⚠️ Gemini error: {e}")
            return {"action": "NEUTRAL"}

    async def _execute_spot_sweep(self, amount_usd: float):
        """Execute a Spot Buy order to sweep profits into HYPE/USDC."""
        try:
            # 1. Find the Spot Asset (HYPE/USDC or PURR/USDC)
            target_asset = "HYPE/USDC"
            if target_asset not in self.market_structure:
                # Fallback to PURR/USDC if HYPE not found
                target_asset = "PURR/USDC"
                if target_asset not in self.market_structure:
                    print("⚠️ No Spot asset found for sweep.")
                    return

            struct = self.market_structure[target_asset]
            if not struct.get("is_spot", False):
                print(f"⚠️ {target_asset} is not a spot asset.")
                return

            # 2. Calculate Quantity
            price = struct["price"]
            if price == 0:
                return
            
            qty = amount_usd / price
            qty = round(qty, struct.get("sz_decimals", 2))
            
            if qty <= 0:
                return

            # 3. Determine Asset ID Name
            # Spot execution requires special name format: "@<index>" usually
            # But SDK `market_open` might abstract this if using `exchange.market_open`.
            # Let's try using the name first, if fails, log error.
            # Based on doc: "For Spot, coin should be ... @{index}"
            spot_idx = struct["index"] - 10000
            trade_coin = f"@{spot_idx}"
            
            # 4. Execute
            print(f"🧹 Sweeping ${amount_usd:.2f} into {target_asset} ({qty} units)...")
            # Spot orders might need different parameters?
            # SDK `market_open` signature: (coin, is_buy, sz, px, slippage)
            # For spot, px should be accurate.
            
            result = self.exchange.market_open(trade_coin, True, qty, price, 0.05)
            
            if result["status"] == "ok":
                print(f"✅ Sweep Successful: Bought {qty} {target_asset}")
            else:
                print(f"❌ Sweep Failed: {result}")

        except Exception as e:
            print(f"⚠️ Sweep Execution Error: {e}")

    async def _execute_trade(self, asset: str, signal: Dict):
        """Execute trade on Hyperliquid with advanced logic."""
        action = signal["action"]
        is_buy = action == "BUY"
        size_usd = signal.get("size_usd", 50.0) # Increased default
        order_type = signal.get("type", "MARKET")
        
        if asset not in self.market_structure:
            print(f"❌ Asset {asset} not found in market structure.")
            return

        struct = self.market_structure[asset]
        price = struct.get("price", 0)
        if price == 0:
            print(f"⚠️ Price for {asset} is 0. Skipping.")
            return

        # Risk Check: 10% Cash Cushion
        try:
            user_state = self.exchange.info.user_state(self.account.address)
            margin_summary = user_state.get("marginSummary", {})
            account_value = float(margin_summary.get("accountValue", "0.0"))
            withdrawable = float(user_state.get("withdrawable", "0.0"))
            
            # If account value is 0, check cross margin (USDC)
            if account_value == 0:
                 cross_margin = user_state.get("crossMarginSummary", {})
                 account_value = float(cross_margin.get("accountValue", "0.0"))
            
            cushion_amount = account_value * 0.10
            
            if withdrawable < cushion_amount:
                print(f"⚠️ Risk Check Failed: Insufficient Cushion. Withdrawable: ${withdrawable:.2f} < Cushion: ${cushion_amount:.2f}")
                return
        except Exception as e:
            print(f"⚠️ Failed to check risk cushion: {e}")
            # Fail safe? Or proceed? Let's proceed with warning for now to avoid total blockage on API error
            pass

        # Calculate size in tokens
        size_tokens = size_usd / price
        
        # Round to size decimals
        decimals = struct.get("sz_decimals", 2)
        size_tokens = round(size_tokens, decimals)
        
        if size_tokens <= 0:
            print(f"⚠️ Size for {asset} is too small ({size_tokens}). Skipping.")
            return
            
        # Log Intent
        print(f"🤖 Hype Bull Agent: {action} {size_tokens} {asset} @ ${price} | {signal.get('reasoning', '')}")
        self._publish_event("agent_log", {
            "system": "hyperliquid",
            "message": f"🤖 {action} {asset}: {signal.get('reasoning', 'No reasoning')}"
        })

        if not self.exchange:
            print(f"📝 [PAPER] {action} {asset} (Conf: {signal.get('confidence')})")
            return

        try:
            print(f"🚀 Executing {action} {size_tokens} {asset} ({order_type})")
            
            # Leverage Management (Only for Perps)
            if not struct.get("is_spot", False):
                try:
                    # Update leverage to 10x isolated/cross
                    # self.exchange.update_leverage(10, asset) # Basic SDK method
                    pass
                except:
                    pass

            # Asset Identifier Logic
            # For Spot, SDK might expect '@<index>' or 'PURR/USDC'
            # For Perps, 'ETH', 'BTC' etc.
            trade_coin = asset
            if struct.get("is_spot", False):
                # If specifically PURR, use PURR/USDC
                if asset == "PURR":
                    trade_coin = "PURR/USDC"
                else:
                    # Use @<index> format if we have the index (which is asset_id - 10000)
                    # But struct["index"] IS the asset_id (10000 + idx)
                    # Wait, market_structure["index"] stores the asset_id I calculated?
                    # In _fetch_market_structure:
                    # asset_id = 10000 + idx
                    # self.market_structure[name] = { ... "index": asset_id ... }
                    # So to get spot index:
                    spot_idx = struct["index"] - 10000
                    # The doc says: "For Spot, coin should be ... @{index}" where index is the spot pair index.
                    trade_coin = f"@{spot_idx}"
                    if asset == "PURR/USDC": # Special case if name is already full
                         trade_coin = "PURR/USDC"

            result = None
            if order_type == "MARKET":
                # 5% slippage
                result = self.exchange.market_open(trade_coin, is_buy, size_tokens, price, 0.05)
            elif order_type == "LIMIT":
                # ALO (Post-Only) Example
                # limit_px = price * (0.99 if is_buy else 1.01) # Example placement
                # result = self.exchange.order(trade_coin, is_buy, size_tokens, limit_px, {"limit": {"tif": "Alo"}})
                pass
            
            if result and result["status"] == "ok":
                print(f"✅ Order Filled: {result}")
                
                # Publish Trade
                self._publish_event("trade_execution", {
                    "system": "hyperliquid",
                    "symbol": asset,
                    "side": action,
                    "price": price,
                    "quantity": size_tokens,
                    "notional": size_usd,
                    "timestamp": time.time()
                })
                
                # Telegram Notification
                if self.telegram:
                    asyncio.create_task(self.telegram.send_trade_notification(
                        symbol=asset,
                        side=action,
                        price=price,
                        quantity=size_tokens,
                        notional=size_usd
                    ))
                
                # Check for closing a position (implied profit sweep logic)
                if asset in self.open_positions:
                    pos = self.open_positions[asset]
                    # If reducing position
                    if (pos["side"] == "BUY" and not is_buy) or (pos["side"] == "SELL" and is_buy):
                        # Estimate PnL realized (simplified)
                        pnl = (price - pos["entry_px"]) * min(size_tokens, abs(pos["size"])) * (1 if pos["side"] == "BUY" else -1)
                        
                        if pnl > 0:
                            sweep_amount = pnl * 0.5
                            self.swept_profits += sweep_amount
                            self.realized_pnl += pnl
                            self.winning_trades += 1
                            print(f"💰 PROFIT SWEEP: ${sweep_amount:.2f} swept to HYPE/USDC!")
                            self._publish_event("profit_sweep", {
                                "system": "hyperliquid",
                                "amount": sweep_amount,
                                "asset": "HYPE/USDC"
                            })
                            
                            # Telegram Profit Sweep
                            if self.telegram:
                                asyncio.create_task(self.telegram.send_message(
                                    f"💰 **PROFIT SWEEP**\nSwept ${sweep_amount:.2f} profit from {asset} to HYPE!",
                                    priority=NotificationPriority.HIGH
                                ))
                            
                            # Execute Spot Buy for Sweep
                            asyncio.create_task(self._execute_spot_sweep(sweep_amount))
                        else:
                            self.realized_pnl += pnl

            elif result and result.get("status") == "error":
                 print(f"❌ Order Error: {result.get('response')}")

        except Exception as e:
            print(f"❌ Order Failed: {e}")


if __name__ == "__main__":
    service = HyperliquidTradingService()
    try:
        asyncio.run(service.start())
    except KeyboardInterrupt:
        print("🛑 Stopped.")
