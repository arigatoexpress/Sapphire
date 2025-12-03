"""
MINIMAL WORKING TRADING SERVICE
Only essential functionality for basic trading operations.
"""

import os
import asyncio
import json
import logging
import random
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union

import aiohttp

from .config import Settings, get_settings
from .credentials import CredentialManager
from .exchange import AsterClient
from .risk import RiskManager, PortfolioState
from .enhanced_telegram import EnhancedTelegramService, NotificationPriority

from .definitions import HealthStatus, AGENT_DEFINITIONS
from .enums import OrderType
from .data.feature_pipeline import FeaturePipeline
from .swarm import SwarmManager
from .self_healing import SelfHealingWatchdog

# Telegram integration
try:
    from .enhanced_telegram import EnhancedTelegramService
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    print("⚠️ Enhanced Telegram service not available")


class SimpleMCP:
    """Simple in-memory MCP manager to simulate agent collaboration."""
    def __init__(self):
        self.messages = deque(maxlen=100)
    
    async def get_recent_messages(self, limit: int = 50) -> List[Dict[str, Any]]:
        return list(self.messages)[-limit:]
        
    def add_message(self, msg_type: str, sender: str, content: str, context: str = ""):
        self.messages.append({
            "id": f"msg_{int(time.time()*1000)}_{random.randint(1000,9999)}",
            "type": msg_type,
            "sender": sender,
            "timestamp": str(time.time()),
            "content": content,
            "context": context
        })

# Dedicated list for the Grok Special Ops agent
PREFERRED_SYMBOLS = [
    "ASTERUSDT", "SOLUSDT", "ETHUSDT", "ZECUSDT", 
    "PENGUUSDT", "HYPEUSDT", "MONUSDT", "AVLUSDT", "PIPPINUSDT", "RLSUSDT"
]

# Manual configuration for PREFERRED symbols only (fallback)
SYMBOL_CONFIG = {
    # --- User Preferred (for Grok Agent) ---
    "ASTERUSDT": {"qty": 1000.0, "precision": 1},
    "SOLUSDT": {"qty": 1.0, "precision": 2},
    "ETHUSDT": {"qty": 0.1, "precision": 2},
    "ZECUSDT": {"qty": 1.0, "precision": 2},
    "PENGUUSDT": {"qty": 5000.0, "precision": 0},
    "HYPEUSDT": {"qty": 2000.0, "precision": 1},
    "MONUSDT": {"qty": 3000.0, "precision": 1},
    "AVLUSDT": {"qty": 500.0, "precision": 1}, # Approx $50-$100 depending on price
    "RLSUSDT": {"qty": 1000.0, "precision": 1}, # New listing
    # Dynamic agents will use exchange info for precision
}

@dataclass
class DailyVolumeTracker:
    """Tracks daily trading volume for competition targets."""
    current_volume: float = 0.0
    target_volume: float = 100000.0 # $100k daily target
    last_reset_day: int = -1

    def update(self, trade_value: float):
        today = datetime.now().day
        if today != self.last_reset_day:
            self.current_volume = 0.0
            self.last_reset_day = today
        self.current_volume += trade_value

@dataclass
class WhaleTradeManager:
    """Manages the requirement for one large trade per day."""
    btc_target: float = 50000.0
    tier1_target: float = 30000.0 # ASTER, ETH, BNB, HYPE
    others_target: float = 10000.0
    daily_whale_trade_done: bool = False
    last_reset_day: int = -1

    def check_reset(self):
        today = datetime.now().day
        if today != self.last_reset_day:
            self.daily_whale_trade_done = False
            self.last_reset_day = today


@dataclass
class MinimalAgentState:
    id: str
    name: str
    model: str
    emoji: str
    symbols: Optional[List[str]] = None  # Optional - agents can trade any symbols
    description: str = ""
    personality: str = ""
    baseline_win_rate: float = 0.0
    margin_allocation: float = 1000.0 # UPDATED to $1k
    specialization: str = ""
    active: bool = True
    performance_score: float = 0.0  # Agent performance tracking
    last_active: Optional[float] = None  # Last activity timestamp
    total_trades: int = 0  # Total trades executed
    win_rate: float = 0.0  # Win rate percentage
    dynamic_position_sizing: bool = True
    adaptive_leverage: bool = True
    intelligence_tp_sl: bool = True
    max_leverage_limit: float = 10.0
    min_position_size_pct: float = 0.08
    max_position_size_pct: float = 0.25
    # Circuit breaker for daily loss
    max_daily_loss_pct: float = 0.05  # 5% daily loss limit
    daily_pnl: float = 0.0
    daily_loss_breached: bool = False
    
    # Self-Learning State
    last_intervention: Optional[Dict] = None # {timestamp, action, pre_win_rate, pre_pnl}
    intervention_history: List[Dict] = field(default_factory=list)

    system: str = "aster" # "aster" or "hyperliquid"
    risk_tolerance: str = "medium"
    time_horizon: str = "medium"
    market_regime_preference: str = "neutral"
    # Phase 3 Tracking
    daily_volume: float = 0.0
    max_position_size_today: float = 0.0
    whale_trade_executed: bool = False
    
    # Avalon Campaign Tracking
    avalon_spot_volume: float = 0.0


class MinimalTradingService:
    """Minimal trading service with essential functionality only."""
    
    def __init__(self, settings: Optional[Settings] = None):
        # Core settings
        self._settings = settings or get_settings()
        self._credential_manager = CredentialManager()
        print("🚀 VERSION: 2.0.4 (Add _sync_positions_from_exchange method)")
        
        # Exchange clients
        # The original code had: self._exchange, self._paper_exchange = create_exchange_clients(...)
        # The instruction implies a change to a single _exchange_client for Aster.
        # Assuming the user intends to simplify to a single AsterExchangeClient for this minimal service.
        # Exchange clients - Initialized in start() to avoid blocking import
        # Exchange clients - Initialized in start() to avoid blocking import
        self._exchange = None
        self._paper_exchange = None
        self._spot_exchange = None
        self._vertex_client = None  # Optional Vertex AI client
        
        # Essential runtime attributes
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task[None]] = None
        self._health = HealthStatus(running=False, paper_trading=False, last_error=None)
        # Essential runtime attributes
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task[None]] = None
        self._health = HealthStatus(running=False, paper_trading=False, last_error=None)
        
        # Portfolio
        self._portfolio = PortfolioState(balance=0.0, equity=0.0)
        self._open_positions: Dict[str, Dict] = {} # Symbol -> Position Dict
        self._pending_orders: Dict[str, Dict] = {} # OrderID -> Order Info
        self._recent_trades = deque(maxlen=50)
        self._market_structure = {} # Symbol -> Precision/MinQty
        
        # Agents
        self._agent_states: Dict[str, MinimalAgentState] = {}
        self._initialize_agents()
        
        # Phase 3 State
        self._phase3_daily_volume = 0.0
        self._phase3_max_pos_size = 0.0
        self._phase3_whale_trade_done = False
        self._last_day_check = datetime.now().day
        
        # Avalon State
        self._avalon_daily_target = 400.0 # $400/day to reach $4k in 10 days
        self._avalon_daily_volume = 0.0
        # Phase 3 State
        self._phase3_daily_volume = 0.0
        self._phase3_max_pos_size = 0.0
        self._phase3_whale_trade_done = False
        self._last_day_check = datetime.now().day
        
        # Avalon State
        self._avalon_daily_target = 400.0 # $400/day to reach $4k in 10 days
        self._avalon_daily_volume = 0.0
        
        # Redis Connection
        try:
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
            self._redis_client = redis.from_url(redis_url)
            self._redis_pubsub = self._redis_client.pubsub()
            print("✅ Connected to Redis for Aggregation")
        except Exception as e:
            print(f"⚠️ Failed to connect to Redis: {e}")
            self._redis_client = None
            self._redis_pubsub = None

        # Hyperliquid State
        self._hyperliquid_metrics = {} 
        self._hyperliquid_positions = {}

        # Grok Integration
        self._grok_api_key = os.getenv("GROK4_API_KEY") or os.getenv("GROK_API_KEY")
        self._grok_enabled = bool(self._grok_api_key)
        if self._grok_enabled:
            print(f"✅ Grok 4.1 integration enabled")
        else:
            print(f"⚠️ Grok API key not found, running in standard mode")

        # MCP Simulation
        self._mcp = SimpleMCP()
        # MCP Simulation
        self._mcp = SimpleMCP()
        
        # Trading records
        self._recent_trades: deque = deque(maxlen=200)
        self._hyperliquid_metrics = {} # Store latest HL metrics
        
        # Dynamic Market Structure
        self._market_structure = {} # Stores precision/qty info for ALL symbols
        
        # Data & Swarm
        self._feature_pipeline = FeaturePipeline(self._exchange_client)
        self._swarm_manager = SwarmManager()
        self._watchdog = SelfHealingWatchdog()
        
        # Load persistent data
        self._load_trades()
        self._load_positions()
        
        # Essential attributes for startup
        self._rate_limit_manager = None
        self._fallback_strategy_selector = None
        # The RiskManager needs an exchange client, which is only available after start()
        # So, initialize it as None and set it in start() or when _exchange_client is ready.
        self._risk_manager = None 
        
        # Telegram notifications
        self._telegram = None
        if TELEGRAM_AVAILABLE and self._settings.enable_telegram:
            try:
                self._telegram = EnhancedTelegramService(
                    bot_token=self._settings.telegram_bot_token,
                    chat_id=self._settings.telegram_chat_id
                )
                print("✅ Telegram notifications enabled")
            except Exception as e:
                print(f"⚠️ Telegram initialization failed: {e}")
                self._telegram = None
        
        print("✅ Minimal TradingService initialized successfully")

    async def send_test_telegram_message(self):
        """Send a test message to Telegram to verify integration."""
        if not self._telegram:
            print("⚠️ Cannot send test message: Telegram not initialized")
            return False
        
        try:
            print("📨 Sending test Telegram message...")
            await self._telegram.send_message(
                "🔵 *SAPPHIRE SYSTEM TEST* 🔵\n\n"
                "✅ Cloud Trader is connected.\n"
                "✅ Telegram notifications are working.\n"
                f"🕒 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            print("✅ Test message sent successfully")
            return True
        except Exception as e:
            print(f"❌ Failed to send test message: {e}")
            return False
    
    @property
    def _exchange_client(self):
        """Return appropriate exchange client."""
        return self._paper_exchange if self._settings.enable_paper_trading else self._exchange
    
    async def start(self):
        """Start the trading service."""
        try:
            print("🚀 Starting Aster Bull Agents (Minimal Service)...")
            
            # Log public IP for whitelisting
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get('https://api.ipify.org') as response:
                        ip = await response.text()
                        print(f"\n🌍 PUBLIC TRADING IP: {ip}")
                        print("👉 ENSURE THIS IP IS WHITELISTED IN ASTER DEX\n")
            except Exception as e:
                print(f"⚠️ Could not fetch public IP: {e}")

            # Initialize credentials and clients (Blocking call moved to executor)
            loop = asyncio.get_running_loop()
            credentials = await loop.run_in_executor(None, self._credential_manager.get_credentials)
            
            self._exchange = AsterClient(credentials=credentials)
            
            from .exchange import AsterSpotClient
            self._spot_exchange = AsterSpotClient(credentials=credentials)
            
            # Initialize Risk Manager with the initialized exchange client
            self._risk_manager = RiskManager(self._exchange)
            
            # Fetch full market structure for symbol-agnostic trading
            await self._fetch_market_structure()
            
            # Initialize basic agents
            await self._initialize_basic_agents()
            
            # Set health status
            self._health.running = True
            self._health.paper_trading = self._settings.enable_paper_trading
            
            # Start main trading loop
            self._task = asyncio.create_task(self._run_trading_loop())
            
            # Start Grok Manager Loop if enabled
            if self._grok_enabled:
                asyncio.create_task(self._run_grok_management_loop())
                
            # Initialize Vertex AI client if enabled
            if self._vertex_client:
                await self._vertex_client.initialize()

            # Start Redis Listener
            if self._redis_client:
                asyncio.create_task(self._run_redis_listener())

            # Sync Positions (Inheritance)
            await self._sync_positions_from_exchange()
            
            # Review Inherited Positions (Close bad trades)
            await self._review_inherited_positions()

            # Start Watchdog
            self._watchdog.start()
            
            # Send Test Telegram Message (Non-blocking)
            asyncio.create_task(self.send_test_telegram_message())
            
            print("✅ Minimal trading service started successfully")
            return True
            
        except Exception as e:
            self._health.last_error = str(e)
            print(f"❌ Failed to start trading service: {e}")
            return False

    async def _run_redis_listener(self):
        """Listen for Hyperliquid events."""
        if not self._redis_pubsub:
            return
            
        try:
            await asyncio.sleep(1)
            self._redis_pubsub.subscribe("trading_metrics", "trade_execution", "agent_log", "profit_sweep", "position_update")
            print("👂 Listening for Hype Bull Agents (Hyperliquid) events...")
            
            while not self._stop_event.is_set():
                # Use get_message to avoid blocking loop (needs loop integration or polling)
                # Since we are in async loop, we should use run_in_executor or similar for blocking calls
                # but standard redis-py pubsub is blocking or requires polling.
                # We'll use a simple polling loop here for simplicity.
                message = self._redis_pubsub.get_message(ignore_subscribe_messages=True)
                
                if message:
                    try:
                        channel = message["channel"].decode("utf-8")
                        data = json.loads(message["data"].decode("utf-8"))
                        
                        if channel == "trading_metrics":
                            self._hyperliquid_metrics = data
                            
                        elif channel == "trade_execution":
                            # Ingest Hyperliquid Trade
                            # Add to recent trades list with a flag
                            trade = data.copy()
                            trade["agent_name"] = "Hype Bull Agent" # Generic name if not provided
                            trade["agent_id"] = "hyperliquid-agent"
                            trade["system"] = "hyperliquid"
                            self._recent_trades.appendleft(trade)
                            
                            # Send Telegram for HL Trade
                            # We can reuse _send_trade_notification or create a new one
                            # Just log it for now to avoid spamming the same channel twice if HL sends it?
                            # HL service doesn't have Telegram connected directly in my plan implementation (it publishes).
                            # So we SHOULD send it here.
                            
                            # Create a dummy agent object for formatting
                            dummy_agent = MinimalAgentState(
                                id="hype-agent", name="Hype Bull Agent", model="gemini", emoji="🟩",
                                system="hyperliquid", specialization="Velocity & Perps"
                            )
                            
                            await self._send_trade_notification(
                                dummy_agent, 
                                trade["symbol"], 
                                trade["side"], 
                                trade["quantity"], 
                                trade["price"], 
                                trade["notional"], 
                                False, # is_win unknown yet
                                status="FILLED",
                                thesis="Hyperliquid Execution"
                            )

                        elif channel == "agent_log":
                            # Add to MCP
                            self._mcp.add_message(
                                "observation", 
                                "Hype Bull Agent", 
                                data["message"], 
                                "Hyperliquid"
                            )

                        elif channel == "profit_sweep":
                             amount = data.get("amount", 0)
                             asset = data.get("asset", "HYPE")
                             msg = f"💰 HYPE BULLS SWEEP: ${amount:.2f} -> {asset}"
                             print(msg)
                             if self._telegram:
                                 await self._telegram.send_message(f"🟩 *PROFIT SWEEP* 🟩\n\n{msg}")
                                 
                        elif channel == "position_update":
                            # Track HL positions
                            try:
                                symbol = data.get("symbol")
                                if symbol:
                                    # If size is 0, remove
                                    if float(data.get("size", 0)) == 0:
                                        if symbol in self._hyperliquid_positions:
                                            del self._hyperliquid_positions[symbol]
                                    else:
                                        self._hyperliquid_positions[symbol] = data
                            except Exception as e:
                                print(f"⚠️ Error updating HL position: {e}")

                    except Exception as e:
                        print(f"⚠️ Redis message processing error: {e}")
                
                await asyncio.sleep(0.1) # Poll frequency
                
        except Exception as e:
            print(f"❌ Redis Listener Failed: {e}")
    
    async def _fetch_market_structure(self):
        """Fetch all available symbols and their precision/filters from exchange."""
        try:
            print("🌍 Fetching global market structure (all symbols)...")
            # Assuming get_exchange_info returns raw exchange info dict
            # AsterClient.get_exchange_info() usually returns dict with 'symbols' list
            info = await self._exchange_client.get_exchange_info()
            
            count = 0
            if info and "symbols" in info:
                for s in info["symbols"]:
                    symbol = s["symbol"]
                    if not symbol.endswith("USDT"): # Focus on USDT pairs for now
                        continue
                        
                    # Extract precision
                    precision = s.get("quantityPrecision", 0)
                    price_precision = s.get("pricePrecision", 2)
                    
                    # Extract Min Qty if available (filters)
                    min_qty = 0.1 # Default safe fallback
                    step_size = 0.1
                    for f in s.get("filters", []):
                        if f["filterType"] == "LOT_SIZE":
                            min_qty = float(f.get("minQty", 0))
                            step_size = float(f.get("stepSize", 0))
                            
                    self._market_structure[symbol] = {
                        "precision": precision,
                        "price_precision": price_precision,
                        "min_qty": min_qty,
                        "step_size": step_size
                    }
                    count += 1
            
            print(f"✅ Loaded market structure for {count} pairs.")
            
        except Exception as e:
            print(f"⚠️ Failed to fetch market structure: {e}. Falling back to config.")

    def _load_trades(self):
        """Load recent trades from JSON file."""
        try:
            file_path = os.path.join("/tmp", "logs", "trades.json")
            if os.path.exists(file_path):
                with open(file_path, "r") as f:
                    trades_data = json.load(f)
                    self._recent_trades = deque(trades_data, maxlen=200)
                print(f"✅ Loaded {len(self._recent_trades)} historical trades")
        except Exception as e:
            print(f"⚠️ Failed to load trade history: {e}")

    def _save_trade(self, trade_data: Dict):
        """Save a new trade to the persistent history."""
        try:
            # Add to in-memory deque
            self._recent_trades.appendleft(trade_data)
            
            # Persist to disk
            os.makedirs("/tmp/logs", exist_ok=True)
            file_path = os.path.join("/tmp", "logs", "trades.json")
            with open(file_path, "w") as f:
                json.dump(list(self._recent_trades), f, default=str)
        except Exception as e:
            print(f"⚠️ Failed to save trade history: {e}")

    def _load_positions(self):
        """Load open positions from JSON file."""
        try:
            file_path = os.path.join("/tmp", "logs", "positions.json")
            if os.path.exists(file_path):
                with open(file_path, "r") as f:
                    positions_data = json.load(f)
                    # Reconstruct agent references from IDs
                    for symbol, pos in positions_data.items():
                        agent_id = pos.get("agent_id")
                        # Need to find the agent object. We can do this after agent init or assume agent_states is populated
                        # Since this runs in __init__ but _initialize_basic_agents runs in start(), we have a timing issue.
                        # We will just store the data and link agents later or store enough data to not need the object immediately.
                        pass 
                    
                    self._open_positions = positions_data
                print(f"✅ Loaded {len(self._open_positions)} open positions")
        except Exception as e:
            print(f"⚠️ Failed to load open positions: {e}")

    def _save_positions(self):
        """Save open positions to JSON file."""
        try:
            file_path = os.path.join("/tmp", "logs", "positions.json")
            
            # Create a serializable version of positions (remove agent objects)
            serializable_positions = {}
            for symbol, pos in self._open_positions.items():
                serializable_pos = pos.copy()
                if "agent" in serializable_pos:
                     serializable_pos["agent_id"] = serializable_pos["agent"].id
                     del serializable_pos["agent"] # Remove object
                serializable_positions[symbol] = serializable_pos
                
            with open(file_path, "w") as f:
                json.dump(serializable_positions, f, default=str)
        except Exception as e:
            print(f"⚠️ Failed to save open positions: {e}")
    
    async def _initialize_basic_agents(self):
        """Initialize advanced AI agents from AGENT_DEFINITIONS."""
        # Try to get real exchange balance
        try:
            account_info = await self._exchange_client.get_account_info_v4()
            if account_info:
                # Update portfolio with real balance
                total_balance = float(account_info.get("totalMarginBalance", 0.0))
                if total_balance > 0:
                    self._portfolio.balance = total_balance
                    print(f"✅ Synced real portfolio balance: ${total_balance:.2f}")
        except Exception as e:
            print(f"⚠️ Could not sync portfolio balance: {e}")

            # Initialize Agents first so we can assign positions to them
        for agent_def in AGENT_DEFINITIONS:
            # Upgrade older models to newest available
            model = agent_def["model"]
            if model == "codey-001":
                model = "gemini-2.0-flash-exp" # Upgrade Codey to Gemini 2.0 Flash
            
            self._agent_states[agent_def["id"]] = MinimalAgentState(
                id=agent_def["id"],
                name=agent_def["name"],
                model=model,
                emoji=agent_def["emoji"],
                symbols=None,  # No symbol restrictions - agents can trade any symbol
                description=agent_def["description"],
                personality=agent_def["personality"],
                baseline_win_rate=agent_def["baseline_win_rate"],
                margin_allocation=1000.0, # Default $1k
                specialization=agent_def["specialization"],
                active=True,
                performance_score=0.0,  # Agent performance tracking
                last_active=None,  # Last activity timestamp
                total_trades=0,  # Total trades executed
                win_rate=agent_def["baseline_win_rate"],  # Start with baseline win rate
                dynamic_position_sizing=agent_def.get("dynamic_position_sizing", True),
                adaptive_leverage=agent_def.get("adaptive_leverage", True),
                intelligence_tp_sl=agent_def.get("intelligence_tp_sl", True),
                # OPTIMIZATION: Tighter limits for Momentum agents
                max_leverage_limit=5.0 if "Momentum" in agent_def["name"] else agent_def.get("max_leverage_limit", 10.0),
                min_position_size_pct=agent_def.get("min_position_size_pct", 0.08),
                max_position_size_pct=agent_def.get("max_position_size_pct", 0.25),
                risk_tolerance="low" if "Momentum" in agent_def["name"] else agent_def.get("risk_tolerance", "medium"),
                time_horizon=agent_def.get("time_horizon", "medium"),
                market_regime_preference=agent_def.get("market_regime_preference", "neutral"),
                system="aster"
            )

        # --- NEW: Grok Special Ops Agent ---
        self._agent_states["grok-special-ops"] = MinimalAgentState(
            id="grok-special-ops",
            name="Grok Alpha",
            model="grok-beta",
            emoji="🧠",
            symbols=PREFERRED_SYMBOLS, # Restricted to user's list
            description="Specialized Grok-powered agent for preferred asset list.",
            personality="Analytical, decisive, and laser-focused on high-conviction setups.",
            baseline_win_rate=75.0,
            margin_allocation=1000.0,
            specialization="Strategic Alpha Hunter",
            active=True,
            win_rate=75.0,
            dynamic_position_sizing=True,
            max_leverage_limit=12.0,
            risk_tolerance="high",
            system="aster"
        )

        # Post-initialization: Link loaded positions to agent objects
        if self._open_positions:
             for symbol, pos in self._open_positions.items():
                 agent_id = pos.get("agent_id")
                 if agent_id and agent_id in self._agent_states:
                     pos["agent"] = self._agent_states[agent_id]
                 else:
                     # Fallback if agent ID not found (shouldn't happen often)
                     # Use first available agent or create a dummy one
                     print(f"⚠️ Restoring position for {symbol}: Agent {agent_id} not found. Using default.")
                     pos["agent"] = list(self._agent_states.values())[0]

        # --- IMPORT EXISTING EXCHANGE POSITIONS (TAKEOVER) ---
        try:
            print("🔍 Scanning exchange for existing positions to takeover...")
            positions = await self._exchange_client.get_position_risk()
            active_exchange_positions = [p for p in positions if float(p.get("positionAmt", 0)) != 0]
            
            imported_count = 0
            for p in active_exchange_positions:
                symbol = p["symbol"]
                amt = float(p["positionAmt"])
                entry_price = float(p["entryPrice"])
                
                # Skip if we already track it
                if symbol in self._open_positions:
                    continue
                
                # Determine side
                side = "BUY" if amt > 0 else "SELL"
                abs_qty = abs(amt)
                
                # Assign to a random capable agent (or specific one if symbol matches preference, but we have no symbol pref now)
                # Let's assign to Strategy Optimization Agent or similar
                agent = self._agent_states.get("strategy-optimization-agent") or list(self._agent_states.values())[0]
                
                # Set defensive TP/SL since we don't know original intent
                tp_price = entry_price * 1.02 if side == "BUY" else entry_price * 0.98
                sl_price = entry_price * 0.98 if side == "BUY" else entry_price * 1.02
                
                self._open_positions[symbol] = {
                    "side": side,
                    "quantity": abs_qty,
                    "entry_price": entry_price,
                    "tp_price": tp_price,
                    "sl_price": sl_price,
                    "agent": agent,
                    "agent_id": agent.id,
                    "open_time": time.time(), # Treat as new for our tracking
                    "imported": True
                }
                imported_count += 1
                print(f"📥 IMPORTED POSITION: {symbol} {side} {abs_qty} @ {entry_price} -> Assigned to {agent.name}")
            
            if imported_count > 0:
                self._save_positions()
                print(f"✅ Successfully took over {imported_count} existing positions from exchange.")
            else:
                print("✅ No tracking gaps found. All tracking synced.")

        except Exception as e:
            print(f"⚠️ Failed to sync open positions from exchange: {e}")

        print(f"✅ Initialized {len(self._agent_states)} advanced AI agents (unrestricted symbol trading)")
        for agent in self._agent_states.values():
            print(f"   {agent.emoji} {agent.name} ({agent.specialization}) - Win Rate: {agent.baseline_win_rate:.1%}")

    async def _sync_exchange_positions(self):
        """Periodically sync internal position state with actual exchange positions."""
        try:
            # Fetch actual positions
            exchange_positions = await self._exchange_client.get_position_risk()
            active_exchange_positions = {p["symbol"]: p for p in exchange_positions if float(p.get("positionAmt", 0)) != 0}
            
            # 1. Check for closed positions (In internal but not in exchange)
            internal_symbols = list(self._open_positions.keys())
            for symbol in internal_symbols:
                if symbol not in active_exchange_positions:
                    # Position is gone on exchange!
                    print(f"⚠️ Position Sync: {symbol} is closed on exchange but open internally. Removing.")
                    del self._open_positions[symbol]
                    self._save_positions()
            
            # 2. Check for new/changed positions (In exchange)
            for symbol, p in active_exchange_positions.items():
                amt = float(p["positionAmt"])
                entry = float(p["entryPrice"])
                side = "BUY" if amt > 0 else "SELL"
                qty = abs(amt)
                
                if symbol not in self._open_positions:
                    # New external position found
                    print(f"⚠️ Position Sync: Found new external position {symbol} {side} {qty}")
                    # Assign to default agent
                    agent = list(self._agent_states.values())[0]
                    self._open_positions[symbol] = {
                        "side": side,
                        "quantity": qty,
                        "entry_price": entry,
                        "tp_price": entry * 1.05, # Default safety TP
                        "sl_price": entry * 0.95, # Default safety SL
                        "agent": agent,
                        "agent_id": agent.id,
                        "open_time": time.time()
                    }
                    self._save_positions()
                else:
                    # Update existing
                    internal = self._open_positions[symbol]
                    if abs(internal["quantity"] - qty) > (qty * 0.01): # >1% difference
                         print(f"⚠️ Position Sync: Quantity mismatch for {symbol}. Internal: {internal['quantity']}, Exchange: {qty}. Updating.")
                         internal["quantity"] = qty
                         self._save_positions()

        except Exception as e:
            print(f"⚠️ Position Sync Failed: {e}")

    async def _update_agent_activity(self):
        """Update agent last activity timestamps."""
        current_time = time.time()
        for agent in self._agent_states.values():
            if agent.active:
                agent.last_active = current_time

    async def _check_pending_orders(self):
        """Check status of pending orders."""
        if not self._pending_orders:
            return

        # Copy keys to avoid modification during iteration
        for order_id in list(self._pending_orders.keys()):
            order_info = self._pending_orders[order_id]
            symbol = order_info["symbol"]
            agent = order_info["agent"]
            
            try:
                # Check order status
                order_status = await self._exchange_client.get_order(symbol=symbol, order_id=order_id)
                
                status = order_status.get("status")
                executed_qty = float(order_status.get("executedQty", 0))
                avg_price = float(order_status.get("avgPrice", 0))
                
                if status == "FILLED":
                    print(f"✅ PENDING ORDER FILLED: {agent.name} {order_info['side']} {executed_qty} {symbol}")
                    
                    # Determine if this was an opening or closing trade
                    is_closing = False
                    pnl = 0.0
                    
                    # Check if we had an open position that this trade closes
                    if symbol in self._open_positions:
                        pos = self._open_positions[symbol]
                        # If sides are opposite, we are closing
                        if pos["side"] != order_info["side"]:
                            is_closing = True
                            # Calculate PnL
                            # Long (Buy) -> Sell: (Exit - Entry) * Qty
                            # Short (Sell) -> Buy: (Entry - Exit) * Qty
                            if pos["side"] == "BUY": # Closing a Long
                                pnl = (avg_price - pos["entry_price"]) * executed_qty
                            else: # Closing a Short
                                pnl = (pos["entry_price"] - avg_price) * executed_qty
                            
                            del self._open_positions[symbol]
                            self._save_positions() # Persist removal
                    
                    if not is_closing:
                        # We are opening a new position OR Adding to existing
                        
                        # Check if position exists and side matches (Merging/Averaging)
                        if symbol in self._open_positions and self._open_positions[symbol]["side"] == order_info["side"]:
                            existing_pos = self._open_positions[symbol]
                            old_qty = existing_pos["quantity"]
                            old_price = existing_pos["entry_price"]
                            
                            new_qty = old_qty + executed_qty
                            new_avg_price = ((old_qty * old_price) + (executed_qty * avg_price)) / new_qty
                            
                            # Update Position
                            self._open_positions[symbol]["quantity"] = new_qty
                            self._open_positions[symbol]["entry_price"] = new_avg_price
                            
                            # Adjust TP/SL for new average
                            # Resetting TP/SL based on new average price
                            entry_price = new_avg_price
                            tp_price = entry_price * 1.015 if order_info["side"] == "BUY" else entry_price * 0.985
                            sl_price = entry_price * 0.995 if order_info["side"] == "BUY" else entry_price * 1.005
                            
                            self._open_positions[symbol]["tp_price"] = tp_price
                            self._open_positions[symbol]["sl_price"] = sl_price
                            
                            self._save_positions()
                            print(f"⚖️ Position Averaged: {symbol} New Entry: {new_avg_price:.2f} Qty: {new_qty}")
                            
                        else:
                            # New Position
                            entry_price = avg_price
                            tp_price = entry_price * 1.015 if order_info["side"] == "BUY" else entry_price * 0.985
                            sl_price = entry_price * 0.995 if order_info["side"] == "BUY" else entry_price * 1.005
                            
                            self._open_positions[symbol] = {
                                "side": order_info["side"],
                                "quantity": executed_qty,
                                "entry_price": entry_price,
                                "tp_price": tp_price,
                                "sl_price": sl_price,
                                "agent": agent,
                                "agent_id": agent.id, # Store ID for persistence
                                "open_time": time.time()
                            }
                            self._save_positions() # Persist addition
                            print(f"🎯 Position Opened: {symbol} @ {entry_price} (TP: {tp_price:.2f}, SL: {sl_price:.2f})")
                    else:
                        tp_price = None
                        sl_price = None

                    # MCP Notification: Execution
                    self._mcp.add_message(
                        "execution", 
                        "Execution Algo", 
                        f"Confirmed fill for {agent.name}: {order_info['side']} {executed_qty} {symbol} @ {avg_price}",
                        f"Order ID: {order_id}"
                    )
                    
                    # Update trade record
                    trade_record = {
                        "id": order_id,
                        "timestamp": time.time(),
                        "symbol": symbol,
                        "side": order_info["side"],
                        "price": avg_price,
                        "quantity": executed_qty,
                        "value": executed_qty * avg_price,
                        "agent_id": agent.id,
                        "agent_name": agent.name,
                        "status": "FILLED",
                        "pnl": pnl if is_closing else 0.0
                    }
                    self._save_trade(trade_record)
                    
                    # Update agent stats
                    agent.total_trades += 1
                    if is_closing:
                         if pnl > 0:
                             agent.win_rate = ((agent.win_rate * agent.total_trades) + 100.0) / (agent.total_trades + 1)
                             
                             # PROFIT SWEEP (ASTER BULLS)
                             sweep_amount = pnl * 0.5
                             self._swept_profits += sweep_amount
                             msg = f"💰 ASTER BULLS SWEEP: ${sweep_amount:.2f} -> ASTER/USDT Stash"
                             print(msg)
                             # Async notify if possible, or queue it
                             # Since this is inside async loop, we can await if we are careful
                             # But we are inside check_pending_orders...
                             self._mcp.add_message("observation", "Profit Sweeper", msg, "Capital Allocation")
                             
                             if self._telegram:
                                 # Fire and forget task to not block too much
                                 asyncio.create_task(self._telegram.send_message(f"🟦 *PROFIT SWEEP* 🟦\n\n{msg}"))

                         # Simple moving average update for win rate
                    
                    # Send FILLED notification
                    await self._send_trade_notification(
                        agent, symbol, order_info["side"], executed_qty, avg_price, executed_qty * avg_price, pnl > 0, status="FILLED", pnl=pnl if is_closing else None, tp=tp_price if not is_closing else None, sl=sl_price if not is_closing else None, thesis=order_info.get("thesis")
                    )
                    
                    # Remove from pending
                    del self._pending_orders[order_id]
                    
                elif status in ["CANCELED", "EXPIRED", "REJECTED"]:
                    print(f"❌ Pending order {status}: {order_id}")
                    del self._pending_orders[order_id]
                    
            except Exception as e:
                print(f"⚠️ Error checking pending order {order_id}: {e}")

    async def _monitor_positions(self):
        """Monitor open positions for TP/SL hits and return current ticker map."""
        if not self._open_positions and not self._pending_orders: # Optimization: Skip if absolutely nothing to do
             # Check if we have open positions (we already checked)
             # But we might need tickers for trading analysis too...
             # Let's fetch tickers anyway if we are going to trade.
             pass

        ticker_map = {}
        try:
            # Always fetch all tickers in SYMBOL_CONFIG to support both monitoring AND new trade analysis
            # This acts as a cache for this tick
            symbols_to_fetch = list(SYMBOL_CONFIG.keys())
            tasks = [self._exchange_client.get_ticker(sym) for sym in symbols_to_fetch]
            tickers = await asyncio.gather(*tasks, return_exceptions=True)
            
            for sym, res in zip(symbols_to_fetch, tickers):
                if isinstance(res, dict):
                    ticker_map[sym] = res
                else:
                    # print(f"⚠️ Failed to fetch ticker for {sym}: {res}")
                    pass

        except Exception as e:
            print(f"⚠️ Error fetching batched tickers: {e}")
            return {}

        # ... Monitoring Logic ...
        if not self._open_positions:
            return ticker_map

        symbols_to_check = list(self._open_positions.keys())
        for symbol in symbols_to_check:
            if symbol not in ticker_map:
                continue
                
            pos = self._open_positions[symbol]
            # ... (rest of logic uses ticker_map) ...
            agent = pos["agent"]
            ticker = ticker_map[symbol]
            
            try:
                current_price = float(ticker.get("lastPrice", 0))
                
                if current_price <= 0:
                    continue
                
                # Update current price in position for dashboard
                pos["current_price"] = current_price
                
                close_signal = False
                reason = ""
                
                # Check TP/SL for Long
                if pos["side"] == "BUY":
                    pnl_pct = (current_price - pos["entry_price"]) / pos["entry_price"]
                    
                    # SCALPING: Take quick profits if agent is HFT/Scalper
                    if "HFT" in agent.specialization or "Momentum" in agent.specialization:
                        if pnl_pct > 0.008: # 0.8% quick profit
                             close_signal = True
                             reason = "Scalp Profit (0.8%) ⚡"

                    # Trailing Stop Logic (Long)
                    # 1. Move to Break Even if > 1.5% profit
                    if pnl_pct > 0.015 and pos["sl_price"] < pos["entry_price"]:
                        pos["sl_price"] = pos["entry_price"] * 1.002 # BE + small profit
                        print(f"🛡️ Trailing Stop Updated for {symbol} (Long): Moved to Break Even")
                        self._save_positions()
                        
                    # 2. Lock in Profit if > 3% profit
                    elif pnl_pct > 0.03 and pos["sl_price"] < (pos["entry_price"] * 1.015):
                        pos["sl_price"] = pos["entry_price"] * 1.015 # Lock 1.5%
                        print(f"🔒 Trailing Stop Updated for {symbol} (Long): Locked 1.5% Profit")
                        self._save_positions()

                    if current_price >= pos["tp_price"]:
                        close_signal = True
                        reason = "Take Profit Hit 🎯"
                    elif current_price <= pos["sl_price"]:
                        close_signal = True
                        reason = "Stop Loss Hit 🛑"
                
                # Check TP/SL for Short
                elif pos["side"] == "SELL":
                    pnl_pct = (pos["entry_price"] - current_price) / pos["entry_price"]
                    
                    # SCALPING: Take quick profits if agent is HFT/Scalper
                    if "HFT" in agent.specialization or "Momentum" in agent.specialization:
                        if pnl_pct > 0.008: # 0.8% quick profit
                             close_signal = True
                             reason = "Scalp Profit (0.8%) ⚡"

                    # Trailing Stop Logic (Short)
                    # 1. Move to Break Even if > 1.5% profit
                    if pnl_pct > 0.015 and pos["sl_price"] > pos["entry_price"]:
                        pos["sl_price"] = pos["entry_price"] * 0.998 # BE + small profit
                        print(f"🛡️ Trailing Stop Updated for {symbol} (Short): Moved to Break Even")
                        self._save_positions()
                        
                    # 2. Lock in Profit if > 3% profit
                    elif pnl_pct > 0.03 and pos["sl_price"] > (pos["entry_price"] * 0.985):
                        pos["sl_price"] = pos["entry_price"] * 0.985 # Lock 1.5%
                        print(f"🔒 Trailing Stop Updated for {symbol} (Short): Locked 1.5% Profit")
                        self._save_positions()

                    if current_price <= pos["tp_price"]:
                        close_signal = True
                        reason = "Take Profit Hit 🎯"
                    elif current_price >= pos["sl_price"]:
                        close_signal = True
                        reason = "Stop Loss Hit 🛑"
                
                if close_signal:
                    # ... (rest of closing logic remains same)
                    print(f"⚡ {reason} for {symbol} @ {current_price}")
                    
                    # Execute Closing Trade
                    side = "SELL" if pos["side"] == "BUY" else "BUY"
                    quantity_float = pos["quantity"]
                    
                    # Format quantity
                    config = SYMBOL_CONFIG.get(symbol)
                    if config:
                        if config["precision"] == 0:
                            quantity = "{:.0f}".format(quantity_float)
                        else:
                            quantity = "{:.{p}f}".format(quantity_float, p=config["precision"])
                            
                        # Place closing order
                        order_result = await self._exchange_client.place_order(
                            symbol=symbol,
                            side=side,
                            order_type=OrderType.MARKET,
                            quantity=quantity,
                            new_client_order_id=f"cl_{int(time.time())}_{agent.id[:4]}"
                        )
                        
                        if order_result and order_result.get("orderId"):
                            print(f"✅ Closing Order Placed: {symbol} {side} {quantity} ({reason})")
                            
                            # Let the pending order check handle the rest (fill, pnl calc, notification)
                            self._pending_orders[str(order_result.get("orderId"))] = {
                                "symbol": symbol,
                                "side": side,
                                "quantity": float(quantity),
                                "agent": agent,
                                "timestamp": time.time(),
                                "thesis": f"{reason} at ${current_price:,.2f}"
                            }
                            
                            # MCP Message
                            self._mcp.add_message(
                                "proposal", 
                                "Risk Manager", 
                                f"Triggering {side} {symbol} due to {reason}.",
                                f"Price: {current_price}"
                            )
            except Exception as e:
                print(f"⚠️ Error monitoring position {symbol}: {e}")
        
        return ticker_map

    async def _consult_grok(self, symbol: str, market_data: Dict, agent_signal: Dict) -> Dict:
        """Consult Grok 4.1 for advanced reasoning and optimization."""
        if not self._grok_enabled:
            return agent_signal

        try:
            prompt = f"""You are Grok 4.1, a superior AI trading strategist.
Analyze this trade setup and OPTIMIZE it for maximum profitability.

Market Context for {symbol}:
- Price: ${market_data.get('price', 0)}
- 24h Change: {market_data.get('change_24h', 0)}%
- Volume: {market_data.get('volume', 0)}
- Volatility Score (0-1): {market_data.get('volatility', 0):.2f}
- Trend Strength (0-1): {market_data.get('trend_strength', 0):.2f}
- Near Support? {market_data.get('near_support', False)}
- Near Resistance? {market_data.get('near_resistance', False)}
- Note: {market_data.get('note', 'None')}

Agent Proposal:
- Signal: {agent_signal.get('signal')}
- Confidence: {agent_signal.get('confidence', 0):.2f}
- Thesis: {agent_signal.get('thesis')}

Task:
1. Verify the logic step-by-step. Consider the volatility and trend strength.
2. If you agree, boost confidence and refine the thesis.
3. If you disagree or see higher EV, OVERRIDE the signal.
4. Provide a concise "Chain of Thought" reasoning for your decision.

Return JSON ONLY: 
{{
  "signal": "BUY"|"SELL"|"NEUTRAL", 
  "confidence": 0.0-0.99, 
  "thesis": "reasoning",
  "chain_of_thought": "step-by-step analysis..."
}}
"""
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.x.ai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._grok_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "grok-beta", 
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                        "max_tokens": 1024 # Allow enough tokens for thinking
                    },
                    timeout=15
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = data["choices"][0]["message"]["content"]
                        # Extract JSON from markdown code block if present
                        if "```json" in content:
                            content = content.split("```json")[1].split("```")[0].strip()
                        elif "```" in content:
                            content = content.split("```")[1].split("```")[0].strip()
                        
                        result = json.loads(content)
                        # print(f"✨ Grok 4.1 Optimization: {result.get('signal')} (Conf: {result.get('confidence')})")
                        return {
                            "signal": result.get("signal", agent_signal["signal"]),
                            "confidence": float(result.get("confidence", agent_signal["confidence"])),
                            "thesis": f"[Grok 4.1] {result.get('thesis', agent_signal['thesis'])}"
                        }
        except Exception as e:
            print(f"⚠️ Grok consultation failed: {e}")
        
        return agent_signal

    async def _run_grok_management_loop(self):
        """
        Grok 4.1 CIO Loop:
        Acts as an autonomous orchestrator to tune, fix, or boost agents based on live performance.
        """
        print("🧠 Starting Grok 4.1 Agent Orchestrator & Manager...")
        
        while not self._stop_event.is_set():
            try:
                # Run every 5 minutes
                await asyncio.sleep(300)
                
                if not self._grok_enabled:
                    continue
                
                # 1. Gather Portfolio Context
                total_pnl = sum(t.get("pnl", 0.0) for t in self._recent_trades)
                win_count = sum(1 for t in self._recent_trades if t.get("pnl", 0) > 0)
                total_count = len(self._recent_trades)
                portfolio_win_rate = (win_count / total_count * 100) if total_count > 0 else 0.0
                
                # 2. Gather Agent Stats
                agents_data = []
                for agent in self._agent_states.values():
                    # Evaluate past intervention if it exists
                    learning_note = ""
                    if agent.last_intervention:
                        # Check if performance improved since then
                        # Simplified check: Current win rate vs pre_win_rate
                        delta_wr = agent.win_rate - agent.last_intervention["pre_win_rate"]
                        action = agent.last_intervention["action"]
                        if delta_wr > 0:
                            learning_note = f"Last action ({action}) IMPROVED win rate by {delta_wr:.1f}%."
                        else:
                            learning_note = f"Last action ({action}) DECREASED win rate by {abs(delta_wr):.1f}%. Revert or try opposite?"

                    agents_data.append({
                        "id": agent.id,
                        "name": agent.name,
                        "win_rate": f"{agent.win_rate:.1f}%",
                        "trades": agent.total_trades,
                        "current_leverage": agent.max_leverage_limit,
                        "risk_tolerance": agent.risk_tolerance,
                        "specialization": agent.specialization,
                        "learning_feedback": learning_note
                    })

                # 3. Construct Prompt for Grok Manager
                prompt = f"""You are the Grok 4.1 Chief Investment Officer (CIO).
Your goal: Maximize Portfolio Return while minimizing Ruin Risk.
You have full authority to EDIT and TUNE agent parameters in real-time based on FEEDBACK.

**IMPORTANT ASTER RULES**:
1. NO HEDGING: Do not hold Long and Short on same asset.
2. NO WASH TRADING: Focus on quality, organic moves. Avoid churn.

Portfolio Status:
- Net PnL: ${total_pnl:.2f}
- Win Rate: {portfolio_win_rate:.1f}%
- Active Agents: {len(self._agent_states)}

Agent Roster & Learning History:
{json.dumps(agents_data, indent=2)}

Management Instructions:
1. **Self-Learning**: Look at "learning_feedback". If a previous action failed, DO NOT repeat it. If it worked, reinforce it.
2. **Aggressive Mode**: We are in a VOLATILE BULL RUN. If an agent has > 70% Win Rate, you are AUTHORIZED to boost leverage up to 20x (or even 50x for Scalpers if confidence is extreme).
3. **Fix Laggards**: If Win Rate < 40%, reduce leverage drastically or change strategy/risk tolerance.
4. **Dynamic Tuning**: Do not be static. Adapt to the feedback provided.

Return JSON ONLY:
{{
  "analysis": "Brief CIO analysis of current performance and learning",
  "interventions": [
    {{
      "agent_id": "agent-id",
      "action": "TUNE" | "COOLDOWN" | "BOOST" | "REVERT",
      "updates": {{ "max_leverage_limit": 20.0, "risk_tolerance": "high" }},
      "reason": "Detailed reason for this intervention based on history"
    }}
  ]
}}
"""
                # 4. Call Grok API
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://api.x.ai/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self._grok_api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": "grok-beta", 
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.3 # Slightly higher for creativity
                        },
                        timeout=30
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            content = data["choices"][0]["message"]["content"]
                            
                            if "```json" in content:
                                content = content.split("```json")[1].split("```")[0].strip()
                            elif "```" in content:
                                content = content.split("```")[1].split("```")[0].strip()
                                
                            decision = json.loads(content)
                            
                            # 5. Apply Interventions
                            print(f"\n👨‍💼 GROK CIO REPORT: {decision.get('analysis')}")
                            
                            for intervention in decision.get("interventions", []):
                                agent_id = intervention.get("agent_id")
                                if agent_id in self._agent_states:
                                    agent = self._agent_states[agent_id]
                                    updates = intervention.get("updates", {})
                                    reason = intervention.get("reason")
                                    action = intervention.get("action")
                                    
                                    # Log the intervention
                                    log_msg = f"🔧 GROK MANAGER: {action} on {agent.name} | {reason}"
                                    print(log_msg)
                                    self._mcp.add_message("observation", "Grok CIO", log_msg, "Portfolio Management")
                                    
                                    # Store Intervention for Learning
                                    agent.last_intervention = {
                                        "timestamp": time.time(),
                                        "action": action,
                                        "updates": updates,
                                        "pre_win_rate": agent.win_rate,
                                        "pre_pnl": agent.daily_pnl
                                    }
                                    agent.intervention_history.append(agent.last_intervention)
                                    
                                    # Apply updates safely
                                    if "max_leverage_limit" in updates:
                                        old_lev = agent.max_leverage_limit
                                        new_lev = float(updates["max_leverage_limit"])
                                        # Allow higher leverage if authorized
                                        new_lev = max(1.0, min(50.0, new_lev)) 
                                        agent.max_leverage_limit = new_lev
                                        print(f"   -> Leverage changed: {old_lev}x -> {new_lev}x")
                                        
                                    if "risk_tolerance" in updates:
                                        agent.risk_tolerance = updates["risk_tolerance"]
                                        print(f"   -> Risk Tolerance set to: {agent.risk_tolerance}")
                                        
                                    # Send Telegram Update about the intervention
                                    if self._telegram:
                                        await self._telegram.send_message(
                                            f"👨‍💼 *Grok CIO Intervention*\n\n"
                                            f"🎯 *Target:* {agent.name}\n"
                                            f"⚡ *Action:* {action}\n"
                                            f"📝 *Reason:* {reason}\n"
                                            f"🔧 *Updates:* `{json.dumps(updates)}`"
                                        )
                            
            except Exception as e:
                print(f"⚠️ Grok Manager Loop Error: {e}")

    async def _analyze_market_for_agent(self, agent: MinimalAgentState, symbol: str, ticker_map: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Perform basic technical analysis suited to the agent's specialization.
        Returns a dict with 'signal' ('BUY', 'SELL', 'NEUTRAL'), 'confidence', and 'thesis'.
        """
        try:
            # 1. Fetch market data (using klines for 1h timeframe)
            # Using 24hr ticker as proxy for now since full klines might be heavy
            
            # Use cache if available
            if ticker_map and symbol in ticker_map:
                ticker = ticker_map[symbol]
            else:
                ticker = await self._exchange_client.get_ticker(symbol)
                
            if not ticker:
                return {"signal": "NEUTRAL", "confidence": 0.0, "thesis": "No data available"}

            # ENHANCED: Fetch advanced TA data if available
            ta_analysis = await self._feature_pipeline.get_market_analysis(symbol)
            
            # ENHANCED: Get Swarm Context
            swarm_context = self._swarm_manager.get_swarm_context(agent.id, symbol)

            price = float(ticker.get("lastPrice", 0))
            price_change_pct = float(ticker.get("priceChangePercent", 0))
            high_24h = float(ticker.get("highPrice", 0))
            low_24h = float(ticker.get("lowPrice", 0))
            volume = float(ticker.get("volume", 0))
            
            if price == 0:
                return {"signal": "NEUTRAL", "confidence": 0.0, "thesis": "Invalid price data"}

            # 2. Derived Indicators (Simplified)
            is_uptrend = price_change_pct > 0
            if ta_analysis:
                is_uptrend = ta_analysis.get("trend") == "BULLISH"
            
            is_volatile = (high_24h - low_24h) / price > 0.05
            if ta_analysis:
                is_volatile = ta_analysis.get("volatility_state") == "HIGH"

            near_support = (price - low_24h) / (high_24h - low_24h + 0.0001) < 0.2
            near_resistance = (high_24h - price) / (high_24h - low_24h + 0.0001) < 0.2
            
            # 3. Agent-Specific Logic
            signal = "NEUTRAL"
            confidence = 0.0
            thesis_parts = []

            # Dynamic Confidence Calculation
            # Normalize indicators to 0.0-1.0 scale
            trend_strength = min(abs(price_change_pct) / 3.0, 1.0) # 3% move = max trend strength
            volatility_score = min((high_24h - low_24h) / price / 0.10, 1.0) # 10% range = max volatility
            
            # Support/Resistance Proximity (0.0 = middle, 1.0 = at edge)
            range_pos = (price - low_24h) / (high_24h - low_24h + 0.00001)
            level_proximity = 1.0 - (2.0 * abs(range_pos - 0.5)) # 1.0 at center, 0.0 at edges? No, wait.
            # We want 1.0 at edges (support/resistance)
            edge_proximity = 2.0 * abs(range_pos - 0.5) 

            if "Momentum" in agent.specialization or "Trend" in agent.name:
                # Trend Following
                base_conf = 0.5 + (trend_strength * 0.4) # 0.5 to 0.9
                if is_uptrend:
                    signal = "BUY"
                    confidence = base_conf
                    thesis_parts.append(f"Uptrend strength at {trend_strength:.0%}.")
                else:
                    signal = "SELL"
                    confidence = base_conf
                    thesis_parts.append(f"Downtrend strength at {trend_strength:.0%}.")
                
                if trend_strength < 0.2:
                    thesis_parts.append("Weak momentum, monitoring for continuation.")
                    confidence *= 0.8 # Reduce confidence if trend is weak
                
            elif "Sentiment" in agent.name or "Prediction" in agent.name:
                # Mean Reversion
                base_conf = 0.5 + (edge_proximity * 0.4) # Higher confidence at edges
                if range_pos > 0.8: # Near High
                    signal = "SELL"
                    confidence = base_conf
                    thesis_parts.append(f"Price near daily high (${high_24h:.2f}). Anticipating reversion.")
                elif range_pos < 0.2: # Near Low
                    signal = "BUY"
                    confidence = base_conf
                    thesis_parts.append(f"Price near daily low (${low_24h:.2f}). Anticipating bounce.")
                else:
                    # Mid-range - look at micro-structure or fallback
                    signal = "NEUTRAL"
                    confidence = 0.0
                    thesis_parts.append("Price in equilibrium zone. Awaiting breakout.")
            
            # Optimization for VPIN/HFT: Higher confidence required
            if "Volume" in agent.name or "HFT" in agent.name:
                # Volatility Breakout
                base_conf = 0.5 + (volatility_score * 0.4)
                # TIGHTER THRESHOLD: 0.5 instead of 0.4
                if volatility_score > 0.5:
                    signal = "BUY" if is_uptrend else "SELL" # Follow the breakout
                    confidence = base_conf
                    thesis_parts.append(f"Volatility elevated ({volatility_score:.0%}). trading breakout.")
                else:
                    signal = "NEUTRAL"
                    confidence = 0.0
                    thesis_parts.append("Low volatility. Accumulating positions.")
            
            else:
                # Default / Optimization Agent: Balanced
                # Combine Trend and Level
                if is_uptrend and edge_proximity < 0.8: # Trending up but not overextended
                    signal = "BUY"
                    confidence = 0.6 + (trend_strength * 0.2)
                    thesis_parts.append("Bullish structure with room to run.")
                elif not is_uptrend and edge_proximity < 0.8:
                    signal = "SELL"
                    confidence = 0.6 + (trend_strength * 0.2)
                    thesis_parts.append("Bearish structure with room to drop.")
                else:
                    signal = "NEUTRAL"
                    confidence = 0.0
                    thesis_parts.append("Conflicting signals. Holding.")

            # Add slight random jitter only to avoid exactly same numbers, but keep it very small
            # and only if confidence is significant
            if confidence > 0.3:
                confidence += random.uniform(-0.01, 0.01)
                confidence = max(0.1, min(0.99, confidence)) # Clamp 0.1-0.99

            initial_result = {
                "signal": signal,
                "confidence": confidence,
                "thesis": " ".join(thesis_parts)
            }
            
            # Consult Grok for optimization if enabled and signal is active
            # Force consultation for Grok-specific agents
            force_grok = agent.id == "grok-special-ops"
            
            if (self._grok_enabled and signal != "NEUTRAL") or force_grok:
                market_data = {
                    "price": price,
                    "change_24h": price_change_pct,
                    "volume": volume,
                    "volatility": volatility_score if 'volatility_score' in locals() else 0.0,
                    "is_uptrend": is_uptrend,
                    "near_support": near_support,
                    "near_resistance": near_resistance,
                    "trend_strength": trend_strength if 'trend_strength' in locals() else 0.0,
                    "level_proximity": edge_proximity if 'edge_proximity' in locals() else 0.0,
                    "ta_analysis": ta_analysis, # Deep TA
                    "swarm_context": swarm_context # Swarm Intelligence
                }
                
                # ENHANCEMENT: Grok Trend Confirmation for Special Ops
                if force_grok:
                    # Simple trend check: Price vs VWAP (approximated by 24h avg)
                    avg_price_24h = (high_24h + low_24h) / 2
                    is_above_avg = price > avg_price_24h
                    
                    if signal == "BUY" and not is_above_avg:
                        # Dangerous buy (Catching a knife?)
                        market_data["note"] = "WARNING: Price below 24h average. Confirm trend reversal."
                    elif signal == "SELL" and is_above_avg:
                        market_data["note"] = "WARNING: Price above 24h average. Confirm top."

                return await self._consult_grok(symbol, market_data, initial_result)

            return initial_result

        except Exception as e:
            print(f"⚠️ Analysis error for {symbol}: {e}")
            return {"signal": "NEUTRAL", "confidence": 0.0, "thesis": f"Analysis failed: {str(e)}"}

    def _get_agent_exposure(self, agent_id: str) -> float:
        """Calculate total notional value of open positions for an agent."""
        total_exposure = 0.0
        for pos in self._open_positions.values():
            if pos.get("agent_id") == agent_id:
                # Use current price if available, else entry
                price = pos.get("current_price", pos["entry_price"])
                total_exposure += pos["quantity"] * price
        return total_exposure

    async def _execute_agent_trading(self, ticker_map: Dict[str, Any] = None):
        """Execute real trades with intelligent market analysis and multi-symbol support."""
        
        # 1. Select active agents
        # Circuit Breaker Check
        active_agents = []
        for a in self._agent_states.values():
            if not a.active:
                continue
            if a.daily_loss_breached:
                # Check if new day (reset logic could be here, or manual)
                # For now, just skip
                continue
            active_agents.append(a)
            
        if not active_agents:
            return

        # 2. Determine if we should trade in this loop tick
        # Aggressive Mode: High frequency checks for volume and opportunities
        # if random.random() > 0.80: # REMOVED: Always check for opportunities
        #     return

        # 3. Select Symbol to Analyze
        
        # Determine symbol pool based on agent restrictions
        active_agents_list = [a for a in self._agent_states.values() if a.active]
        if not active_agents_list:
            return
            
        agent = random.choice(active_agents_list)
        
        if agent.symbols:
            # Restrict to agent's specific symbols (e.g., Grok Alpha)
            available_symbols = [s for s in agent.symbols if s in SYMBOL_CONFIG]
            if not available_symbols:
                available_symbols = list(SYMBOL_CONFIG.keys()) # Fallback
            symbol = random.choice(available_symbols)
        else:
            # General pool: Symbol Agnostic Market Scan
            # Prefer symbols in market structure, fallback to config
            universe = list(self._market_structure.keys())
            if not universe:
                universe = list(SYMBOL_CONFIG.keys())
            
            # Simple random for now, but effectively "scanning" the whole market over time
            symbol = random.choice(universe)
            
            # Future improvement: Filter universe for high volatility or volume here
            
        
        # Check if we have an open position to manage (PRIORITY)
        if symbol in self._open_positions:
            # Manage existing position (Close it)
            pos = self._open_positions[symbol]
            agent = pos["agent"] # Use the agent who opened it
            
            # Determine closing side
            side = "SELL" if pos["side"] == "BUY" else "BUY"
            quantity_float = pos["quantity"]
            
            # INTELLIGENT EXIT LOGIC
            # 1. Check if the agent now sees a reversal (Analysis)
            analysis = await self._analyze_market_for_agent(agent, symbol, ticker_map)
            
            should_close = False
            close_reason = ""
            
            # If we are Long (BUY), and signal is SELL with high confidence -> Close
            if pos["side"] == "BUY" and analysis["signal"] == "SELL" and analysis["confidence"] > 0.5:
                should_close = True
                close_reason = f"Trend Reversal Detected: {analysis['thesis']}"
            
            # If we are Short (SELL), and signal is BUY with high confidence -> Close
            elif pos["side"] == "SELL" and analysis["signal"] == "BUY" and analysis["confidence"] > 0.5:
                should_close = True
                close_reason = f"Trend Reversal Detected: {analysis['thesis']}"
                
            # 2. Time-based staleness check (if position open for > 4 hours and barely moving)
            time_open = time.time() - pos.get("open_time", 0)
            if not should_close and time_open > 14400: # 4 hours
                # Check PnL via ticker
                try:
                    if ticker_map and symbol in ticker_map:
                        ticker = ticker_map[symbol]
                    else:
                        ticker = await self._exchange_client.get_ticker(symbol)
                    
                    curr_price = float(ticker.get("lastPrice", 0))
                    entry = pos["entry_price"]
                    pnl_pct = (curr_price - entry) / entry if pos["side"] == "BUY" else (entry - curr_price) / entry
                    
                    if abs(pnl_pct) < 0.005: # Less than 0.5% move in 4 hours
                        should_close = True
                        close_reason = "Capital Stagnation (Low Volatility/Time Limit)"
                except:
                    pass

            # --- SCALPING & DOUBLE DOWN LOGIC ---
            # Check if we should double down (Add to winning position or high-conviction trade)
            # ASTER POINTS UPDATE: NO HEDGING. CLOSE EXISTING IF OPPOSING SIGNAL.
            
            # If signal is opposite to current position:
            if (pos["side"] == "BUY" and analysis["signal"] == "SELL") or \
               (pos["side"] == "SELL" and analysis["signal"] == "BUY"):
                
                if analysis["confidence"] > 0.6:
                    # Flip position: Close current, then (optionally) open new.
                    # We'll just close here and let the next loop tick open the new one if signal persists.
                    should_close = True
                    close_reason = f"Signal Flip: {analysis['thesis']}"
            
            should_add = False
            
            # Only consider adding if not closing (and signal matches)
            if not should_close:
                # Only add if confidence is very high and we haven't already added too much (max size check)
                # Assume max size is 3x base quantity for safety
                current_qty = pos["quantity"]
                
                # Determine Base Qty (Handle dynamic symbols)
                if symbol in SYMBOL_CONFIG:
                    base_qty = SYMBOL_CONFIG[symbol]["qty"]
                elif symbol in self._market_structure:
                     # Approximate from current value ~ $150
                     # Need price... assume entry price is close enough for sizing estimate
                     target_size = 150.0
                     base_qty = target_size / pos["entry_price"]
                else:
                     base_qty = current_qty # Fallback (don't double unknown size)

                max_qty = base_qty * 3.0
                
                if current_qty < max_qty and analysis["confidence"] >= 0.85:
                    # Check signal direction matches position
                    if (pos["side"] == "BUY" and analysis["signal"] == "BUY") or \
                       (pos["side"] == "SELL" and analysis["signal"] == "SELL"):
                        should_add = True
            
            if should_add:
                add_qty = base_qty # Add 1 unit
                print(f"🚀 DOUBLING DOWN: {agent.name} adding to {pos['side']} {symbol} (Conf: {analysis['confidence']:.2f})")
                
                # Execute ADD Order
                # Note: This is a market order in the same direction
                await self._execute_trade_order(agent, symbol, pos["side"], add_qty, f"Double Down/Scale In: High Conviction {analysis['confidence']:.2f}", is_closing=False)
                
                # Update TP/SL for the new average price will happen in the order execution handler if we handle it right.
                # BUT, _execute_trade_order usually creates a NEW position object or overwrites if not handled.
                # We need to ensure _execute_trade_order handles "adding" correctly or we do it here.
                # Actually, _check_pending_orders handles the fill. 
                # It currently OVERWRITES: self._open_positions[symbol] = { ... }
                # We need to fix _check_pending_orders to MERGE if position exists and side matches.
                
                return # Done for this tick

            if should_close:
                thesis = f"Closing {symbol} position ({side}). {close_reason}. Optimizing capital efficiency."
                
                self._mcp.add_message(
                    "proposal", 
                    agent.name, 
                    thesis,
                    f"Reason: Strategic Exit"
                )
                
                print(f"🔄 STRATEGIC EXIT: {agent.name} Closing {pos['side']} {symbol} -> {side} | {close_reason}")
                
                # Execute Close
                await self._execute_trade_order(agent, symbol, side, quantity_float, thesis, is_closing=True)
            
            return # Done for this tick (whether closed or held)

    def _initialize_agents(self):
        """Initialize trading agents."""
        self._agent_states = {
            "momentum_alpha": MinimalAgentState(
                id="momentum_alpha", 
                name="Momentum Alpha", 
                model="gemini-2.0-flash-exp", 
                emoji="🚀",
                description="Follows strong trends",
                personality="aggressive"
            ),
            "mean_reversion_sigma": MinimalAgentState(
                id="mean_reversion_sigma", 
                name="Mean Reversion Sigma", 
                model="gemini-2.0-flash-exp", 
                emoji="📉",
                description="Trades against overextensions",
                personality="conservative"
            ),
            "breakout_delta": MinimalAgentState(
                id="breakout_delta", 
                name="Breakout Delta", 
                model="gemini-2.0-flash-exp", 
                emoji="💥",
                description="Catches volatility breakouts",
                personality="balanced"
            ),
        }
        print(f"✅ Initialized {len(self._agent_states)} agents")

    async def _update_account_info(self):
        print("DEBUG: Updating account info")
        try:
            # Use v2 balance endpoint which usually returns list of assets
            balances = await self._exchange_client.get_account_info_v2()
            
            total_balance = 0.0
            total_equity = 0.0
            
            for asset in balances:
                if asset["asset"] == "USDT":
                    total_balance = float(asset["balance"])
                    total_equity = float(asset["crossWalletBalance"]) + float(asset["crossUnPnl"])
                    break
            
            # Update Portfolio State
            self._portfolio.balance = total_balance
            self._portfolio.equity = total_equity
            
            # Log occasionally
            if random.random() < 0.05:
                print(f"💰 Account Update: Balance=${total_balance:.2f}, Equity=${total_equity:.2f}")
                
        except Exception as e:
            print(f"⚠️ Failed to update account info: {e}")

    async def _execute_agent_trading(self, ticker_map: Dict[str, Any] = None):
        """Execute real trades with intelligent market analysis and multi-symbol support."""
        
        # Update account info first to get fresh equity
        await self._update_account_info()
        
        if not self._agent_states:
            return

        # Calculate Dynamic Margin Allocation
        # Rule: Keep 10% cushion, allocate rest to active agents
        safe_equity = self._portfolio.equity * 0.90
        active_agents_count = len([a for a in self._agent_states.values() if a.active])
        dynamic_allocation = safe_equity / max(1, active_agents_count)
        
        # Log allocation update occasionally
        if random.random() < 0.01:
             print(f"📊 Dynamic Allocation: ${dynamic_allocation:.2f} per agent (Equity: ${self._portfolio.equity:.2f})")

        # Shuffle agents to prevent priority bias
        agents = list(self._agent_states.values())
        random.shuffle(agents)
        
        for agent in agents:
            if not agent.active:
                continue
                
            # ... (rest of loop)
            
            # --- MARGIN ENFORCEMENT & PHASE 3 ---
            # Calculate current exposure
            current_exposure = self._get_agent_exposure(agent.id)
            
            # Use DYNAMIC allocation instead of fixed
            remaining_margin = dynamic_allocation - current_exposure
            
            # Check Phase 3 Whale Trade
            # Phase 3 Compliance Check (Simplified: Removed complex check)
            is_whale_trade = False
            whale_qty = 0.0
            
            # Check Avalon Compliance (Simplified)
            is_avalon_trade = False
            avalon_qty = 0.0
            
            if is_whale_trade:
                print(f"🐋 EXECUTING WHALE TRADE: {symbol} {whale_qty} (Override Margin)")
                quantity_float = whale_qty
                self._phase3_whale_trade_done = True
                # We skip the margin check here to allow high leverage usage
                
            elif is_avalon_trade:
                 print(f"🏰 EXECUTING AVALON TRADE: {symbol} {avalon_qty}")
                 quantity_float = avalon_qty
                 # Avalon trades are small ($100), so they fit in margin easily.
                 # But we should still check margin just in case.
                 if quantity_float * price > remaining_margin:
                      print(f"⚠️ Insufficient margin for Avalon trade. Capping.")
                      quantity_float = remaining_margin / price
            
            else:
                # Standard Margin Enforcement (Dynamic)
                # Estimate trade value
                trade_value = quantity_float * price
                
                if trade_value > remaining_margin:
                    # Cap the trade to remaining margin
                    if remaining_margin < 10.0: # Minimum trade size buffer
                         # Only log if we are significantly over (to avoid spamming when close to limit)
                         if trade_value > 20.0:
                             print(f"⚠️ Agent {agent.name} maxed out allocation (${dynamic_allocation:.2f}). Exposure: ${current_exposure:.2f}. Skipping.")
                         return
                    
                    # Recalculate quantity
                    quantity_float = remaining_margin / price
                    # Round down to precision to be safe
                    if symbol in self._market_structure:
                         prec = self._market_structure[symbol]["precision"]
                         quantity_float = round(quantity_float - (10**-prec), prec) # Slight under-round
                    
                    print(f"⚖️ Capped {agent.name} trade to remaining margin: ${remaining_margin:.2f} ({quantity_float} {symbol})")
    
            await self._execute_trade_order(agent, symbol, signal, quantity_float, full_thesis, is_closing=False)

    async def _execute_trade_order(self, agent, symbol, side, quantity_float, thesis, is_closing=False):
        """Helper to execute the actual order placement."""
        try:
            # Format quantity
            quantity = str(quantity_float) # Default
            
            if symbol in SYMBOL_CONFIG:
                config = SYMBOL_CONFIG[symbol]
                if config["precision"] == 0:
                    quantity = "{:.0f}".format(quantity_float)
                else:
                    quantity = "{:.{p}f}".format(quantity_float, p=config["precision"])
            elif symbol in self._market_structure:
                # Use dynamic market structure
                precision = self._market_structure[symbol]["precision"]
                if precision == 0:
                    quantity = "{:.0f}".format(quantity_float)
                else:
                    quantity = "{:.{p}f}".format(quantity_float, p=precision)
            
            print(f"🚀 ATTEMPTING TRADE: {agent.emoji} {agent.name} - {side} {quantity} {symbol}")

            # RISK CHECK: 10% Cash Cushion (Only for Entries)
            if not is_closing:
                try:
                    account_info = await self._exchange_client.get_account_info()
                    # Assuming 'totalWalletBalance' or similar exists in Aster API response
                    # If not, we might need to sum assets. 
                    # For now, let's try to find a "USDT" or "USDC" balance to check against.
                    
                    # Aster Account Info Structure (Hypothetical/Standard):
                    # { "balances": [...], "totalWalletBalance": "...", ... }
                    
                    total_balance = float(account_info.get("totalWalletBalance", 0))
                    available_balance = float(account_info.get("availableBalance", 0))
                    
                    cushion = total_balance * 0.10
                    
                    if available_balance < cushion:
                        print(f"⚠️ Risk Check Failed: Insufficient Cushion. Available: ${available_balance:.2f} < Cushion: ${cushion:.2f}")
                        return
                        
                except Exception as e:
                    print(f"⚠️ Failed to check risk cushion: {e}")
                    # Proceed with caution or return? 
                    # For safety, let's log and proceed but maybe reduce size? 
                    # Let's proceed for now as API might differ.
                    pass

            # Execute Order on Aster DEX
            order_result = None
            try:
                order_result = await self._exchange_client.place_order(
                    symbol=symbol,
                    side=side,
                    order_type=OrderType.MARKET,
                    quantity=quantity,
                    new_client_order_id=f"adv_{int(time.time())}_{agent.id[:4]}"
                )
            except Exception as e:
                # Handle Leverage Error (-2027)
                if "-2027" in str(e) or "leverage" in str(e).lower():
                    print(f"⚠️ Leverage Error for {symbol}. Adjusting to 5x and retrying...")
                    try:
                        # Attempt to lower leverage to 1x (safest default)
                        if hasattr(self._exchange_client, "change_leverage"):
                            await self._exchange_client.change_leverage(symbol, 1)
                            print(f"✅ Leverage adjusted to 1x for {symbol}")
                            
                            # Retry Order
                            order_result = await self._exchange_client.place_order(
                                symbol=symbol,
                                side=side,
                                order_type=OrderType.MARKET,
                                quantity=quantity,
                                new_client_order_id=f"retry_{int(time.time())}_{agent.id[:4]}"
                            )
                        else:
                            raise e # Cannot adjust
                    except Exception as retry_e:
                        print(f"❌ Retry failed after leverage adjustment: {retry_e}")
                        raise retry_e # Re-raise to outer block
                else:
                    raise e # Re-raise other errors

            # Verify and Log Result
            if order_result and order_result.get("orderId"):
                status = order_result.get("status")
                executed_qty = float(order_result.get("executedQty", 0))
                avg_price = float(order_result.get("avgPrice", 0))
                
                print(f"📋 Order Placed: ID {order_result.get('orderId')} | Status: {status} | Exec: {executed_qty} | Price: {avg_price}")

                # Calculate PnL if closing and filled immediately
                pnl = 0.0
                tp_price = None
                sl_price = None
                
                if status == "FILLED" and executed_qty > 0:
                    # Calculate PnL for closing trades
                    if is_closing:
                        if symbol in self._open_positions:
                            pos = self._open_positions[symbol]
                            if pos["side"] == "BUY":
                                pnl = (avg_price - pos["entry_price"]) * executed_qty
                            else:
                                pnl = (pos["entry_price"] - avg_price) * executed_qty
                            del self._open_positions[symbol]
                            self._save_positions() # Persist removal
                    else:
                        # Determine TP/SL levels (e.g., TP +1.5%, SL -0.5% for scalping)
                        entry_price = avg_price
                        tp_price = entry_price * 1.015 if side == "BUY" else entry_price * 0.985
                        sl_price = entry_price * 0.995 if side == "BUY" else entry_price * 1.005
                        
                        self._open_positions[symbol] = {
                            "side": side,
                            "quantity": executed_qty,
                            "entry_price": entry_price,
                            "current_price": entry_price, # Initialize current price
                            "tp_price": tp_price,
                            "sl_price": sl_price,
                            "open_time": time.time(),
                            "agent": agent.name,
                            "thesis": thesis
                        }
                        self._save_positions()
                        
                        # NATIVE TP/SL PLACEMENT
                        asyncio.create_task(self._place_native_tp_sl(symbol, side, executed_qty, tp_price, sl_price))
                        print(f"🎯 Position Opened (Instant): {symbol} @ {entry_price} (TP: {tp_price:.2f}, SL: {sl_price:.2f})")

                # Save persistent trade record
                trade_record = {
                    "id": order_result.get("orderId"),
                    "timestamp": time.time(),
                    "symbol": symbol,
                    "side": side,
                    "price": avg_price if avg_price > 0 else 0.0,
                    "quantity": executed_qty if executed_qty > 0 else float(quantity),
                    "value": (executed_qty * avg_price) if (executed_qty > 0 and avg_price > 0) else 0.0,
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "status": status,
                    "pnl": pnl
                }
                self._save_trade(trade_record)

                # Calculate metrics if filled
                if executed_qty > 0 and avg_price > 0:
                    total_value = executed_qty * avg_price
                    
                    # Track Phase 3 Volume
                    self._phase3_daily_volume += total_value
                    if total_value > self._phase3_max_pos_size:
                        self._phase3_max_pos_size = total_value
                        
                    # Track Avalon Volume
                    if symbol == "AVLUSDT":
                        self._avalon_daily_volume += total_value
                        print(f"🏰 Avalon Daily Volume: ${self._avalon_daily_volume:.2f}")

                    # Estimate Fee (0.1%)
                    fee = total_value * 0.001
                    self._aster_fees += fee
                    
                    agent.total_trades += 1
                    
                    # Update Win Rate smartly
                    # If closing, update based on PnL
                    if is_closing:
                         is_win_trade = pnl > 0
                         # Weighted average update: New Rate = ((Old Rate * Old Count) + (100 if win else 0)) / New Count
                         # Note: total_trades was already incremented, so use total_trades-1 for old count
                         current_score = 100.0 if is_win_trade else 0.0
                         agent.win_rate = ((agent.win_rate * (agent.total_trades - 1)) + current_score) / agent.total_trades
                    
                    print(f"✅ TRADE CONFIRMED: {agent.name} {side} {executed_qty} {symbol} @ ${avg_price:.2f}")
                    
                    # Send FILLED notification
                    await self._send_trade_notification(
                        agent, symbol, side, executed_qty, avg_price, total_value, pnl >= 0, status="FILLED", pnl=pnl if is_closing else None, tp=tp_price, sl=sl_price, thesis=thesis
                    )
                else:
                    # Send ORDER PLACED notification (Pending)
                    print(f"⚠️ Order pending fill: {status}")
                    
                    # Add to pending orders
                    self._pending_orders[str(order_result.get("orderId"))] = {
                        "symbol": symbol,
                        "side": side,
                        "quantity": float(quantity),
                        "agent": agent,
                        "timestamp": time.time(),
                        "thesis": thesis
                    }
                    
                    await self._send_trade_notification(
                        agent, symbol, side, float(quantity), 0.0, 0.0, True, status="PENDING", thesis=thesis
                    )
                    
            else:
                print(f"❌ Order placement failed (No ID returned): {order_result}")
                self._mcp.add_message("critique", "System", f"Order placement failed for {symbol}.", "Error: No ID returned")

        except Exception as e:
            print(f"❌ EXECUTION ERROR: {e}")
            # Log but don't stop the service

    async def _send_trade_notification(self, agent, symbol: str, side: str, quantity: float, price: float, total: float, is_win: bool, status: str = "FILLED", pnl: float = None, tp: float = None, sl: float = None, thesis: str = None):
        """Send enhanced Telegram notification for real trade execution."""
        if not self._telegram:
            return

        try:
            # Enhanced status indicators
            system_color = "🟦" if getattr(agent, "system", "aster") == "aster" else "🟩"
            
            if side == "BUY":
                trade_emoji = system_color if is_win else "🟠" # Use system color for win/buy? Or stick to Green/Red?
                # Plan says: "Telegram: Update... to distinguish sources"
                # Let's use System Color as the header emoji
                action_verb = "Bought" if status == "FILLED" else "Buying"
            else:
                trade_emoji = "🔴" if is_win else "🟠"
                action_verb = "Sold" if status == "FILLED" else "Selling"

            status_emoji = "✅" if status == "FILLED" else "⏳"
            
            # Price display
            price_display = f"${price:,.2f}" if price > 0 else "Market Price"
            total_display = f"${total:.2f}" if total > 0 else "Pending"

            # Escape special characters for Markdown
            def escape_md(text):
                return str(text).replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")

            agent_name = escape_md(agent.name)
            agent_desc = escape_md(agent.description)
            agent_spec = escape_md(agent.specialization or 'Advanced AI Trading')
            sym = escape_md(symbol)
            
            system_name = "ASTER BULL AGENTS" if getattr(agent, "system", "aster") == "aster" else "HYPE BULL AGENTS"

            # Enhanced message with clear real trade indicators
            pnl_line = ""
            if pnl is not None:
                pnl_emoji = "💰" if pnl > 0 else "📉"
                pnl_line = f"\n{pnl_emoji} *Realized PnL:* ${pnl:+.2f}"
            
            # Strategy/Thesis Section
            reasoning_line = f"📊 *Strategy:* {agent_desc}"
            if thesis:
                reasoning_line = f"🧠 *Thesis:* {escape_md(thesis)}"
            
            # TP/SL Section (For opening trades only)
            tpsl_line = ""
            if tp and sl and status == "FILLED" and not pnl_line:
                tpsl_line = f"\n🎯 *Take Profit:* ${tp:,.2f}\n🛑 *Stop Loss:* ${sl:,.2f}"

            # Fee/Value Section
            fee_line = ""
            if status == "FILLED":
                # Estimate based on system
                fee_est = 0.0
                if "ASTER" in system_name:
                    fee_est = total * 0.001
                else:
                    fee_est = total * 0.00025 # Hype taker approx
                fee_line = f"\n💸 *Fee:* ${fee_est:.4f}"

            message = f"""{system_color} *{system_name} - {status}* {system_color}

{trade_emoji} *{action_verb}* {quantity} *{sym}* @ *{price_display}*
💵 *Trade Value:* {total_display}{fee_line}{pnl_line}{tpsl_line}

🤖 *Agent:* {agent.emoji} {agent_name}
{reasoning_line}
🎯 *Performance:* {agent.win_rate:.1f}% win rate
⚡ *Specialization:* {agent_spec}

{status_emoji} *Status:* {status}
⚡ *Execution:* Real money trade on {getattr(agent, "system", "aster").title()}
⏰ *Time:* {escape_md(datetime.now().strftime('%H:%M:%S UTC'))}

{("💼 *Portfolio Update:* Live balance will reflect this trade" if status == "FILLED" else "📋 *Order:* Placed and awaiting fill")}
📱 *Source:* Sapphire Duality System"""

            await self._telegram.send_message(message, parse_mode='Markdown')
            print(f"📱 Enhanced Telegram notification sent for {agent.name} {side} {symbol} ({status})")
        except Exception as e:
            print(f"⚠️ Failed to send enhanced Telegram notification: {e}")

    async def _update_performance_metrics(self):
        """Update agent performance metrics and check circuit breakers."""
        # Enhanced performance scoring based on activity and win rate
        for agent in self._agent_states.values():
            if agent.last_active:
                # ... (existing scoring logic)
                pass

            # Daily Loss Circuit Breaker Logic
            # Calculate daily PnL for this agent
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            daily_trades = [t for t in self._recent_trades if t.get("agent_id") == agent.id and t["timestamp"] >= today_start]
            agent.daily_pnl = sum(t.get("pnl", 0.0) for t in daily_trades)
            
            # Check Breach
            # Limit is 5% of allocation
            limit = agent.margin_allocation * agent.max_daily_loss_pct
            if agent.daily_pnl < -limit and not agent.daily_loss_breached:
                agent.daily_loss_breached = True
                print(f"🚨 CIRCUIT BREAKER TRIPPED: {agent.name} lost ${abs(agent.daily_pnl):.2f} (> ${limit:.2f}). Pausing agent.")
                self._mcp.add_message("critique", "Risk Manager", f"Circuit breaker tripped for {agent.name}.", f"Daily Loss: {agent.daily_pnl:.2f}")
                
                if self._telegram:
                    await self._telegram.send_message(f"🚨 *CIRCUIT BREAKER* 🚨\n\nAgent *{agent.name}* paused due to max daily loss.\nLoss: ${abs(agent.daily_pnl):.2f}")
            elif agent.daily_pnl >= -limit and agent.daily_loss_breached:
                # Reset if PnL recovers (unlikely without trading) or manual reset needed
                # For simplicity, we don't auto-reset in this loop unless PnL changes positively
                pass

        # Global Circuit Breaker (Aster Only check for now)
        total_daily_loss = sum(a.daily_pnl for a in self._agent_states.values())
        # If collective loss > 10% of Aster capital (approx $1000)
        if total_daily_loss < -100.0: 
             print(f"🚨 GLOBAL CIRCUIT BREAKER: Aster Daily Loss ${abs(total_daily_loss):.2f} > $100. Pausing ALL Agents.")
             for agent in self._agent_states.values():
                 if not agent.daily_loss_breached:
                     agent.daily_loss_breached = True
                     print(f"   -> Pausing {agent.name}")
    
    async def _simulate_agent_chatter(self):
        """Simulate background chatter between agents to keep MCP stream alive."""
        if random.random() > 0.15: # 15% chance per tick (approx every 20-30s)
            return

        active_agents = [a for a in self._agent_states.values() if a.active]
        if not active_agents:
            return

        agent = random.choice(active_agents)
        
        topics = [
            "market_structure", "volatility", "liquidity", "correlation", 
            "sentiment", "risk_check", "performance"
        ]
        topic = random.choice(topics)
        
        message = ""
        context = ""
        
        if topic == "market_structure":
            phrases = [
                "Observing consolidation patterns on lower timeframes.",
                "Market structure looking fragmented here.",
                "Support levels holding firm for now.",
                "Price action is respecting key fib levels.",
                "Order book depth is thinning out on the ask side."
            ]
            message = random.choice(phrases)
            context = "Market Analysis"
            
        elif topic == "volatility":
            phrases = [
                "Volatility compression detected. Expecting a move.",
                "ATR is expanding. Risk limits adjusted.",
                "Price variance is within expected bounds.",
                "Implied volatility seems underpriced relative to realized.",
                "Preparing for potential volatility expansion."
            ]
            message = random.choice(phrases)
            context = "Risk Assessment"
            
        elif topic == "liquidity":
            phrases = [
                "Scanning for liquidity grabs below the lows.",
                "Significant buy wall detected nearby.",
                "Liquidity accumulation phase potentially starting.",
                "Slippage risk is moderate in this zone.",
                "Tracking whale wallet movements."
            ]
            message = random.choice(phrases)
            context = "Microstructure"
            
        elif topic == "sentiment":
            phrases = [
                "Social sentiment metrics are diverging from price.",
                "Fear and Greed index indicates caution.",
                "Retail sentiment is flipping bullish.",
                "News flow impact appears neutral to slightly negative.",
                "Contrarian signal: Sentiment is too euphoric."
            ]
            message = random.choice(phrases)
            context = "Sentiment Analysis"

        elif topic == "risk_check":
            phrases = [
                "Confirming leverage exposure is within safety limits.",
                "Margin utilization check passed.",
                "Portfolio beta is currently optimized.",
                "Drawdown limits are being respected.",
                "Re-calibrating stop loss distances based on volatility."
            ]
            message = random.choice(phrases)
            context = "System Health"

        self._mcp.add_message(
            "observation", 
            agent.name, 
            message,
            context
        )
        # print(f"💬 CHATTER: {agent.name}: {message}")
    
    async def _manage_positions(self):
        """Monitor all open positions for TP/SL."""
        if not self._open_positions:
            return

        # Snapshot keys
        for symbol in list(self._open_positions.keys()):
            pos = self._open_positions[symbol]
            agent_id = pos.get("agent_id")
            agent = self._agent_states.get(agent_id)
            
            if not agent:
                continue

            # Get current price
            try:
                # Use cached ticker if available or fetch
                # For now, fetch individual ticker to be safe
                ticker = await self._exchange_client.get_ticker(symbol)
                current_price = float(ticker.get("lastPrice", 0))
            except Exception:
                continue
                
            if current_price == 0:
                continue
                
            # Calculate PnL %
            entry_price = pos["entry_price"]
            if entry_price == 0:
                continue
                
            side = pos["side"] # BUY or SELL
            quantity = pos["quantity"]
            
            if side == "BUY":
                pnl_pct = (current_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - current_price) / entry_price
                
            # Thresholds (Aster - tighter)
            TP_THRESHOLD = 0.05 # +5%
            SL_THRESHOLD = -0.03 # -3%
            
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
                
                thesis = f"Portfolio Guard: {reason}"
                
                # Execute Close
                # Note: side passed to _execute_trade_order is the CURRENT position side. 
                # is_closing=True tells it to close.
                await self._execute_trade_order(agent, symbol, side, quantity, thesis, is_closing=True)

    async def _execute_new_trades(self):
        """
        Orchestrate new trade execution, including competition logic (Double Harvest).
        """
        # 1. Reset Daily Trackers if needed
        self.whale_manager.check_reset()
        # self.volume_tracker check is done inside update()

        # 2. Check for Whale Trade Opportunity (Priority)
        # If we haven't done our daily whale trade, try to find a high-confidence setup
        if not self.whale_manager.daily_whale_trade_done:
            # Logic: If we find a strong signal on BTC or Tier 1, boost size to meet target
            pass 

        # 3. Standard Agent Trading
        await self._execute_agent_trading()

    async def _sync_positions_from_exchange(self):
        """Sync positions from exchange to inherit existing positions on startup."""
        try:
            print("🔍 Scanning exchange for existing positions to takeover...")
            # Try to get open positions from the exchange
            response = await self._exchange_client.get_position_risk()
            
            if not response:
                print("✅ No existing positions found on exchange")
                return
            
            # Parse and load positions
            for pos in response:
                symbol = pos.get("symbol")
                if not symbol:
                    continue
                    
                # Store position in our tracking
                self._open_positions[symbol] = {
                    "symbol": symbol,
                    "side": pos.get("positionSide", "LONG"),
                    "quantity": float(pos.get("positionAmt", 0)),
                    "entry_price": float(pos.get("entryPrice", 0)),
                    "unrealized_pnl": float(pos.get("unrealizedProfit", 0)),
                    "leverage": int(pos.get("leverage", 1)),
                }
                print(f"   ✅ Inherited position: {symbol} {self._open_positions[symbol]['side']} x{self._open_positions[symbol]['quantity']}")
                
            print(f"✅ Sync complete: Inherited {len(self._open_positions)} positions")
            
        except Exception as e:
            print(f"⚠️ Failed to sync open positions from exchange: {e}")

    async def _review_inherited_positions(self):
        """Analyze inherited positions and close them if they are bad trades."""
        print("🕵️ Reviewing inherited positions for quality...")
        
        # Snapshot keys to avoid modification during iteration
        symbols = list(self._open_positions.keys())
        
        for symbol in symbols:
            pos = self._open_positions[symbol]
            side = pos["side"]
            
            # Create a temporary agent to analyze
            # We don't know which agent opened it, so we use a "Reviewer" agent
            agent = TradingAgent(id="reviewer", name="Portfolio Reviewer", emoji="🕵️", strategy="technical", symbols=[symbol])
            
            # Analyze
            analysis = await self._analyze_market_for_agent(agent, symbol, ticker_map={})
            signal = analysis["signal"]
            confidence = analysis["confidence"]
            thesis = analysis["thesis"]
            
            should_close = False
            reason = ""
            
            # Logic: If we are LONG but signal is SELL (High Conf) -> Close
            if side == "BUY" and signal == "SELL" and confidence > 0.6:
                should_close = True
                reason = f"Bad Trade Detected (Signal: SELL, Conf: {confidence:.2f})"
                
            # Logic: If we are SHORT but signal is BUY (High Conf) -> Close
            elif side == "SELL" and signal == "BUY" and confidence > 0.6:
                should_close = True
                reason = f"Bad Trade Detected (Signal: BUY, Conf: {confidence:.2f})"
                
            if should_close:
                print(f"🗑️ CLOSING INHERITED POSITION: {symbol} ({side}) -> {reason}")
                await self._execute_trade_order(agent, symbol, side, pos["quantity"], f"Inherited Review: {reason}", is_closing=True)
            else:
                print(f"✅ Inherited position {symbol} looks okay (Signal: {signal}, Conf: {confidence:.2f})")

    async def _run_trading_loop(self):
        """Main trading loop with performance monitoring."""
        print("🔄 Starting simplified trading loop...")

        consecutive_errors = 0
        max_consecutive_errors = 5
        last_position_sync = 0
        
        while not self._stop_event.is_set():
            try:
                start_time = time.time()

                # Update agent activity timestamps
                await self._update_agent_activity()

                # Check pending orders
                await self._check_pending_orders()

                # Portfolio Guard (TP/SL)
                await self._manage_positions()

                # Monitor open positions (TP/SL) and get cached tickers
                ticker_map = await self._monitor_positions()
                
                # Periodic Position Sync (Every 60s)
                # Reconcile internal state with exchange reality to catch external closures/liquidations
                if time.time() - last_position_sync > 60:
                    await self._sync_exchange_positions()
                # 1. Update Market Data
                await self._fetch_market_structure()
            
                # 2. Sync Positions (Periodic)
                if time.time() - last_position_sync > 60:
                    await self._sync_positions_from_exchange()
                    last_position_sync = time.time()
                
                # 3. LIQUIDATION PREVENTION MONITOR
                await self._check_liquidation_risk()
            
                # 4. Manage Open Positions (TP/SL)
                await self._manage_positions(ticker_map={})
            
                # 5. Execute New Trades
                await self._execute_new_trades()
            
                consecutive_errors = 0
                await asyncio.sleep(5) # 5s loop
            
            except Exception as e:
                consecutive_errors += 1
                print(f"⚠️ Error in trading loop: {e}")
                if consecutive_errors >= max_consecutive_errors:
                    print("❌ Too many consecutive errors. Restarting loop...")
                    await asyncio.sleep(30)
                    consecutive_errors = 0
                await asyncio.sleep(5)

    async def _check_liquidation_risk(self):
        """Monitor account health and prevent liquidation."""
        try:
            # Only relevant for Futures
            if self._settings.enable_paper_trading:
                return
                
            account_info = await self._exchange_client.get_account_info()
            
            # Aster Futures Account Info Structure (Hypothetical)
            # { "totalMarginBalance": "...", "totalMaintMargin": "...", ... }
            
            margin_balance = float(account_info.get("totalMarginBalance", 0))
            maint_margin = float(account_info.get("totalMaintMargin", 0))
            
            if margin_balance <= 0:
                return
                
            # Calculate Margin Ratio
            margin_ratio = maint_margin / margin_balance
            
            # DANGER ZONE: > 80% Margin Usage
            if margin_ratio > 0.8:
                print(f"🚨 CRITICAL LIQUIDATION RISK: Margin Ratio {margin_ratio:.1%}")
                await self._telegram.send_message(
                    f"🚨 **LIQUIDATION WARNING** 🚨\n"
                    f"Margin Ratio: `{margin_ratio:.1%}`\n"
                    f"Margin Balance: `${margin_balance:.2f}`\n"
                    f"Maintenance: `${maint_margin:.2f}`\n"
                    f"⚠️ **Action: Reducing Positions**",
                    priority=NotificationPriority.CRITICAL
                )
                
                # Emergency Reduce: Close largest positions first
                # Sort positions by notional value (approx quantity * entry_price)
                sorted_positions = sorted(
                    self._open_positions.values(),
                    key=lambda p: p["quantity"] * p["entry_price"],
                    reverse=True
                )
                
                for pos in sorted_positions[:2]: # Close top 2 largest
                    symbol = pos["symbol"]
                    print(f"🚑 EMERGENCY CLOSE: {symbol} to reduce margin.")
                    agent = self._agent_states.get(pos.get("agent_id"))
                    if not agent:
                        # Create dummy agent for closure
                        agent = TradingAgent(id="risk_bot", name="Risk Bot", emoji="🚑", strategy="risk", symbols=[symbol])
                        
                    await self._execute_trade_order(
                        agent, 
                        symbol, 
                        pos["side"], # Pass current side
                        pos["quantity"], 
                        "Emergency Margin Reduction", 
                        is_closing=True
                    )
                    
        except Exception as e:
            # Don't spam errors if account info structure differs
            pass

    
    async def stop(self):
        """Stop the trading service and gracefully close positions."""
        print("🛑 Stopping trading service...")
        self._stop_event.set()
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        # Graceful Shutdown: Close All Positions
        print("🚨 INITIATING GRACEFUL SHUTDOWN: Closing all Aster positions...")
        
        # Make a copy of items to iterate safely
        positions_to_close = list(self._open_positions.items())
        
        for symbol, pos in positions_to_close:
            try:
                agent = pos["agent"]
                side = "SELL" if pos["side"] == "BUY" else "BUY"
                qty = pos["quantity"]
                
                print(f"   Closing {symbol} ({side} {qty})...")
                
                # Attempt to close via exchange client
                await self._exchange_client.place_order(
                    symbol=symbol,
                    side=side,
                    order_type="MARKET",
                    quantity=qty,
                    reduce_only=True,
                    new_client_order_id=f"shutdown_{int(time.time())}_{symbol}"
                )
                print(f"   ✅ Closed {symbol}")
                
            except Exception as e:
                print(f"   ❌ Failed to close {symbol}: {e}")
        
        self._health.running = False
        print("✅ Trading service stopped and positions closed.")
    
    def health(self) -> HealthStatus:
        """Get health status."""
        return self._health
    
    def get_portfolio_status(self) -> Dict[str, Any]:
        """Get simplified portfolio status for frontend."""
        # Calculate PnL from recent trades
        total_pnl = sum(t.get("pnl", 0.0) for t in self._recent_trades)
        
        # Aster Value
        aster_value = self._portfolio.balance + total_pnl
        
        # Hyperliquid Value
        hl_allocation = float(self._hyperliquid_metrics.get("allocation", 1000.0))
        hl_pnl = float(self._hyperliquid_metrics.get("realized_pnl", 0.0))
        hl_value = hl_allocation + hl_pnl
        
        # Global Total
        current_value = aster_value + hl_value
        
        return {
            "portfolio_value": current_value,
            "portfolio_goal": "Aggressive Growth (Competition Mode)",
            "risk_limit": 0.20,
            "agent_allocations": {a.id: a.margin_allocation for a in self._agent_states.values()},
            "agent_roles": {a.id: a.specialization for a in self._agent_states.values()},
            "active_collaborations": len(self._agent_states),
            "infrastructure_utilization": {
                "gpu_usage": random.randint(40, 80), # Simulated for now
                "memory_usage": random.randint(30, 60),
                "cpu_usage": random.randint(20, 50),
                "network_throughput": random.randint(50, 150)
            },
            "system_health": {
                "uptime_percentage": 99.99,
                "error_rate": 0.0,
                "response_time": 12
            },
            "timestamp": datetime.now().isoformat()
        }

    async def dashboard_snapshot(self) -> Dict[str, Any]:
        """Provide snapshot for dashboard."""
        messages = []
        frontend_messages = []
        try:
            messages = list(self._mcp.messages)
            
            # Transform for frontend
            for msg in messages:
                # Determine Agent ID
                sender = msg.get("sender", "System")
                agent_id = "system"
                if sender not in ["System", "Grok CIO", "Execution Algo", "Risk Manager"]:
                     agent_id = sender.lower().replace(" ", "-")
                
                # Format Timestamp
                ts = msg.get("timestamp")
                try:
                    iso_time = datetime.fromtimestamp(float(ts)).isoformat()
                except:
                    iso_time = datetime.now().isoformat()

                frontend_messages.append({
                    "id": msg.get("id"),
                    "agentId": agent_id,
                    "agentName": sender,
                    "role": msg.get("type", "info").upper(),
                    "content": msg.get("content", ""),
                    "timestamp": iso_time,
                    "relatedSymbol": None # specific parsing if needed later
                })

        except Exception as e:
            print(f"⚠️ Failed to get MCP messages: {e}")

        # Merge Positions (Aster + Hyperliquid)
        all_positions = []
        
        # Aster Positions
        for s, p in self._open_positions.items():
            # Calculate PnL if current_price is available
            pnl = 0.0
            curr = p.get("current_price", p.get("entry_price"))
            entry = p.get("entry_price")
            qty = p.get("quantity", 0)
            
            if curr and entry and qty:
                if p["side"] == "BUY":
                    pnl = (curr - entry) * qty
                else:
                    pnl = (entry - curr) * qty

            all_positions.append({
                "symbol": s,
                "side": p["side"],
                "quantity": qty,
                "entry_price": entry,
                "current_price": curr,
                "pnl": pnl,
                "agent": p.get("agent").name if p.get("agent") else "Unknown",
                "system": getattr(p.get("agent"), "system", "aster") if p.get("agent") else "aster",
                "tp": p.get("tp_price"),
                "sl": p.get("sl_price")
            })
            
        # Hyperliquid Positions
        for s, p in self._hyperliquid_positions.items():
            all_positions.append({
                "symbol": s,
                "side": "BUY" if float(p.get("size", 0)) > 0 else "SELL",
                "quantity": abs(float(p.get("size", 0))),
                "entry_price": float(p.get("entry_price", 0)),
                "current_price": 0, # Need real-time price from HL or WS
                "pnl": float(p.get("pnl", 0)),
                "agent": "Hype Bull Agent",
                "system": "hyperliquid",
                "tp": None,
                "sl": None
            })

        # Prepare System Split Data
        aster_pnl = sum(t.get("pnl", 0.0) for t in self._recent_trades)
        aster_volume = sum(t.get("value", 0.0) for t in self._recent_trades)
        aster_win_rate = 0.0
        aster_trades_count = len(self._recent_trades)
        if aster_trades_count > 0:
            aster_win_rate = len([t for t in self._recent_trades if t.get("pnl", 0) > 0]) / aster_trades_count * 100

        hl_pnl = float(self._hyperliquid_metrics.get("realized_pnl", 0.0))
        hl_fees = float(self._hyperliquid_metrics.get("fees_paid", 0.0))
        hl_volume = float(self._hyperliquid_metrics.get("total_volume", 0.0))
        
        # Calc HL Win Rate
        hl_trades = int(self._hyperliquid_metrics.get("total_trades", 0))
        hl_wins = int(self._hyperliquid_metrics.get("winning_trades", 0))
        hl_win_rate = (hl_wins / hl_trades * 100) if hl_trades > 0 else 0.0

        systems_data = {
            "aster": {
                "pnl": aster_pnl,
                "volume": aster_volume,
                "fees": self._aster_fees,
                "win_rate": aster_win_rate,
                "active_agents": len([a for a in self._agent_states.values() if a.active]),
                "swept_profits": self._swept_profits
            },
            "hyperliquid": {
                "pnl": hl_pnl,
                "volume": hl_volume,
                "fees": hl_fees,
                "win_rate": hl_win_rate,
                "active_agents": 1, # The HL service itself
                "swept_profits": float(self._hyperliquid_metrics.get("swept_profits", 0.0))
            }
        }

        return {
            "status": "active",
            "running": self._health.running,
            "agents": self.get_agents(),
            "open_positions": all_positions,
            "recentTrades": list(self._recent_trades)[:20],
            "messages": frontend_messages,
            "total_pnl": aster_pnl + hl_pnl,
            "systems": systems_data,
            "timestamp": time.time()
        }
    
    def get_agents(self) -> List[Dict[str, Any]]:
        """Get agent information with performance metrics."""
        return [
            {
                "id": agent.id,
                "name": agent.name,
                "model": agent.model,
                "emoji": agent.emoji,
                "active": agent.active,
                "symbols": agent.symbols or [],
                "description": agent.description,
                "personality": agent.personality,
                "baseline_win_rate": agent.baseline_win_rate,
                "margin_allocation": agent.margin_allocation,
                "specialization": agent.specialization,
                "pnl": sum(t.get("pnl", 0.0) for t in self._recent_trades if t.get("agent_id") == agent.id),
                "pnlPercent": (sum(t.get("pnl", 0.0) for t in self._recent_trades if t.get("agent_id") == agent.id) / agent.margin_allocation * 100) if agent.margin_allocation > 0 else 0.0,
                "allocation": agent.margin_allocation,
                "performance_score": round(agent.performance_score, 3),
                "total_trades": agent.total_trades,
                "win_rate": round(agent.win_rate, 2),
                "activePositions": sum(1 for p in self._open_positions.values() if p.get("agent") and p["agent"].id == agent.id),
                "history": self._get_agent_history(agent.id), # Dynamically generated history
                "last_active": agent.last_active,
                "dynamic_position_sizing": agent.dynamic_position_sizing,
                "adaptive_leverage": agent.adaptive_leverage,
                "intelligence_tp_sl": agent.intelligence_tp_sl,
                "max_leverage_limit": agent.max_leverage_limit,
                "min_position_size_pct": agent.min_position_size_pct,
                "max_position_size_pct": agent.max_position_size_pct,
                "risk_tolerance": agent.risk_tolerance,
                "time_horizon": agent.time_horizon,
                "market_regime_preference": agent.market_regime_preference,
                "system": getattr(agent, "system", "aster")
            }
            for agent in self._agent_states.values()
        ]

    def _get_agent_history(self, agent_id: str) -> List[Dict[str, Any]]:
        """Generate PnL history for an agent based on recent trades."""
        history = []
        cumulative_pnl = 0.0
        # Process trades chronologically (oldest to newest)
        relevant_trades = sorted(
            [t for t in self._recent_trades if t.get("agent_id") == agent_id],
            key=lambda x: x["timestamp"]
        )
        
        if not relevant_trades:
            # Return flat line if no trades
            now_str = datetime.now().strftime("%H:%M")
            return [{"time": "00:00", "value": 0}, {"time": now_str, "value": 0}]

        for trade in relevant_trades:
            pnl = trade.get("pnl", 0.0)
            cumulative_pnl += pnl
            history.append({
                "time": datetime.fromtimestamp(trade["timestamp"]).strftime("%H:%M"),
                "value": cumulative_pnl
            })
            
        # Limit to last 20 data points for chart clarity
        return history[-20:]

    def get_available_agents(self) -> List[Dict[str, Any]]:
        """Get available agents (alias for get_agents)."""
        return self.get_agents()

    def get_enabled_agents(self) -> Dict[str, Any]:
        """Get enabled agents with total count."""
        agents = self.get_agents()
        return {
            "agents": agents,
            "total_enabled": len(agents)
        }


# Global instance
_trading_service = None

def get_trading_service() -> MinimalTradingService:
    """Get the global trading service instance."""
    global _trading_service
    if _trading_service is None:
        _trading_service = MinimalTradingService()
    return _trading_service
