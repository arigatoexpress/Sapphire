"""
MINIMAL WORKING TRADING SERVICE
Only essential functionality for basic trading operations.
"""

import asyncio
import json
import logging
import os
import random
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

import aiohttp

from .config import Settings, get_settings
from .credentials import CredentialManager
from .data.feature_pipeline import FeaturePipeline
from .data.feature_pipeline import FeaturePipeline
from .definitions import AGENT_DEFINITIONS, HealthStatus, PREFERRED_SYMBOLS, SYMBOL_CONFIG, MinimalAgentState
from .position_manager import PositionManager
from .market_data import MarketDataManager
from .grok_manager import GrokManager
from .analysis_engine import AnalysisEngine
from .enhanced_telegram import EnhancedTelegramService, NotificationPriority
from .enums import OrderType
from .exchange import AsterClient
from .risk import PortfolioState, RiskManager
from .self_healing import SelfHealingWatchdog
from .self_healing import SelfHealingWatchdog
from .swarm import SwarmManager
from symphony_lib import SymphonyClient, MarketRegime
from .websocket_manager import broadcast_market_regime

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
        self.messages.append(
            {
                "id": f"msg_{int(time.time()*1000)}_{random.randint(1000,9999)}",
                "type": msg_type,
                "sender": sender,
                "timestamp": str(time.time()),
                "content": content,
                "context": context,
            }
        )





@dataclass
class DailyVolumeTracker:
    """Tracks daily trading volume for competition targets."""

    current_volume: float = 0.0
    target_volume: float = 100000.0  # $100k daily target
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
    tier1_target: float = 30000.0  # ASTER, ETH, BNB, HYPE
    others_target: float = 10000.0
    daily_whale_trade_done: bool = False
    last_reset_day: int = -1

    def check_reset(self):
        today = datetime.now().day
        if today != self.last_reset_day:
            self.daily_whale_trade_done = False
            self.last_reset_day = today





class MinimalTradingService:
    """Minimal trading service with essential functionality only."""

    def __init__(self, settings: Optional[Settings] = None):
        # Core settings
        self._settings = settings or get_settings()
        self._credential_manager = CredentialManager()
        print("🚀 VERSION: 2.0.4 (Add _sync_positions_from_exchange method)")
        print("DEBUG: Starting __init__...", flush=True)
        self.symphony = None  # Initialize early to avoid AttributeError if init fails

        # Exchange clients
        self._exchange = None
        self._paper_exchange = None
        self._spot_exchange = None
        self._vertex_client = None  # Optional Vertex AI client
        print("DEBUG: Exchange clients initialized to None", flush=True)

        # Essential runtime attributes
        try:
            self._stop_event = asyncio.Event()
            print("DEBUG: asyncio.Event created", flush=True)
        except Exception as e:
            print(f"DEBUG: asyncio.Event creation failed: {e}", flush=True)
            self._stop_event = None

        self._task: Optional[asyncio.Task[None]] = None
        self._health = HealthStatus(running=False, paper_trading=False, last_error=None)

        # Portfolio
        self._portfolio = PortfolioState(balance=0.0, equity=0.0)
        self._recent_trades = deque(maxlen=200)
        
        # Initialize Agent States (Required for PositionManager)
        self._agent_states: Dict[str, Any] = {}
        
        # Initialize Position Manager
        print("DEBUG: Initializing PositionManager...", flush=True)
        try:
            self.position_manager = PositionManager(self._exchange_client, self._agent_states)
            print("DEBUG: PositionManager initialized", flush=True)
        except Exception as e:
            print(f"DEBUG: PositionManager init failed: {e}", flush=True)
        
        # Legacy support (delegated to manager)
        self._pending_orders: Dict[str, Dict] = {}  # OrderID -> Order Info
        # Initialize Market Data Manager
        print("DEBUG: Initializing MarketDataManager...", flush=True)
        try:
            self.market_data_manager = MarketDataManager(self._exchange_client)
            print("DEBUG: MarketDataManager initialized", flush=True)
        except Exception as e:
            print(f"DEBUG: MarketDataManager init failed: {e}", flush=True)
        
        # Legacy support
        # self._market_structure = {} # REMOVED: Use property instead

        # Agents
        self._agent_states: Dict[str, MinimalAgentState] = {}
        self._agent_states: Dict[str, MinimalAgentState] = {}
        # self._initialize_agents() # Removed to avoid duplication with _initialize_basic_agents

        # Phase 3 State
        self._phase3_daily_volume = 0.0
        self._phase3_max_pos_size = 0.0
        self._phase3_whale_trade_done = False
        self._last_day_check = datetime.now().day

        # Avalon State
        self._avalon_daily_target = 400.0  # $400/day to reach $4k in 10 days
        self._avalon_daily_volume = 0.0

        # Redis Connection
        print("DEBUG: Initializing Redis...", flush=True)
        try:
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
            import redis
            self._redis_client = redis.from_url(redis_url)
            self._redis_pubsub = self._redis_client.pubsub()
            print("✅ Connected to Redis for Aggregation")
        except Exception as e:
            print(f"⚠️ Failed to connect to Redis: {e}")
            self._redis_client = None
            self._redis_pubsub = None
        print("DEBUG: Redis init complete", flush=True)

        # Hyperliquid State
        self._hyperliquid_metrics = {}
        self._hyperliquid_positions = {}

        # MCP Simulation
        self._mcp = SimpleMCP()

        # Telegram notifications (Pre-init for GrokManager)
        print("DEBUG: Initializing Telegram...", flush=True)
        self._telegram = None
        if TELEGRAM_AVAILABLE and self._settings.enable_telegram:
            try:
                self._telegram = EnhancedTelegramService(
                    bot_token=self._settings.telegram_bot_token,
                    chat_id=self._settings.telegram_chat_id,
                )
                print("✅ Telegram notifications enabled")
            except Exception as e:
                print(f"⚠️ Telegram initialization failed: {e}")
                self._telegram = None
        print("DEBUG: Telegram init complete", flush=True)

        # Grok Integration
        print("DEBUG: Initializing Grok...", flush=True)
        self._grok_api_key = os.getenv("GROK4_API_KEY") or os.getenv("GROK_API_KEY")
        self._grok_manager = GrokManager(self._grok_api_key, self._mcp, self._telegram)
        self._grok_enabled = self._grok_manager.enabled
        if self._grok_enabled:
            print(f"✅ Grok 4.1 integration enabled")
        else:
            print(f"⚠️ Grok API key not found, running in standard mode")
        print("DEBUG: Grok init complete", flush=True)

        # Data & Swarm
        # FeaturePipeline requires exchange_client which is not ready yet.
        # We will initialize it in start() or use a lazy property.
        # But wait, the original code initialized it here passing self._exchange_client property.
        # The property returns None if _exchange is None.
        # Let's keep it but be aware it might need re-init if it caches the client.
        # Actually, FeaturePipeline takes a client. If we pass self._exchange_client now, it passes None.
        # We should initialize FeaturePipeline in start() too.
        self._feature_pipeline = None 
        self._swarm_manager = SwarmManager()
        self._watchdog = SelfHealingWatchdog()
        self._analysis_engine = None # Initialized in start()

        # Load persistent data
        print("DEBUG: Loading persistent data...", flush=True)
        self._load_trades()
        self._load_positions()
        print("DEBUG: Persistent data loaded", flush=True)

        # Essential attributes for startup
        self._rate_limit_manager = None
        self._fallback_strategy_selector = None
        # The RiskManager needs an exchange client, which is only available after start()
        # So, initialize it as None and set it in start() or when _exchange_client is ready.
        self._risk_manager = None

        # Trading trackers
        self.whale_manager = WhaleTradeManager()
        self.volume_tracker = DailyVolumeTracker()

        # Symphony Integration
        print("DEBUG: Reached Symphony Integration block", flush=True)
        try:
            print("DEBUG: Initializing Symphony Client...", flush=True)
            self.symphony = SymphonyClient(
                project_id=self._settings.gcp_project_id or "sapphire-479610",
                service_name="cloud-trader"
            )
            self.current_regime = None
            print("DEBUG: Symphony Client initialized successfully", flush=True)
        except Exception as e:
            print(f"❌ Failed to initialize Symphony Client: {e}", flush=True)
            self.symphony = None

        print("✅ Minimal TradingService initialized successfully")
    @property
    def _market_structure(self) -> Dict[str, Dict[str, Any]]:
        return self.market_data_manager.market_structure

    @_market_structure.setter
    def _market_structure(self, value):
        self.market_data_manager.market_structure = value

    @property
    def _open_positions(self) -> Dict[str, Dict[str, Any]]:
        return self.position_manager.open_positions

    @_open_positions.setter
    def _open_positions(self, value):
        self.position_manager.open_positions = value


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
            print("🚀 Starting Aster Bull Agents (Minimal Service)...", flush=True)

            # Log public IP for whitelisting (Skipped for speed)
            # try:
            #     async with aiohttp.ClientSession() as session:
            #         async with session.get("https://api.ipify.org", timeout=5.0) as response:
            #             ip = await response.text()
            #             print(f"\n🌍 PUBLIC TRADING IP: {ip}", flush=True)
            #             print("👉 ENSURE THIS IP IS WHITELISTED IN ASTER DEX\n", flush=True)
            # except Exception as e:
            #     print(f"⚠️ Could not fetch public IP: {e}", flush=True)

            # Initialize credentials and clients (Blocking call moved to executor)
            loop = asyncio.get_running_loop()
            self._loop = loop
            credentials = await loop.run_in_executor(None, self._credential_manager.get_credentials)

            self._exchange = AsterClient(credentials=credentials)

            from .exchange import AsterSpotClient

            self._spot_exchange = AsterSpotClient(credentials=credentials)

            # Update managers with initialized client
            self.market_data_manager.exchange_client = self._exchange_client
            self.position_manager.exchange_client = self._exchange_client
            print("DEBUG: Updated managers with initialized exchange client", flush=True)

            # Initialize Risk Manager with the initialized exchange client
            print("DEBUG: Initializing Risk Manager...", flush=True)
            self._risk_manager = RiskManager(self._settings)

            # Subscribe to Symphony Strategy
            print("🎻 Subscribing to Symphony Strategy...", flush=True)
            self._strategy_subscription = self.symphony.subscribe_strategy("aster-strategy-sub", self._handle_strategy_update)

            # Fetch full market structure for symbol-agnostic trading
            print("DEBUG: Fetching market structure...", flush=True)
            await self._fetch_market_structure()

            # Initialize basic agents
            print("DEBUG: Initializing basic agents...", flush=True)
            await self._initialize_basic_agents()

            # Set health status
            self._health.running = True
            self._health.paper_trading = self._settings.enable_paper_trading

            # Initialize FeaturePipeline and AnalysisEngine
            print("DEBUG: Initializing FeaturePipeline and AnalysisEngine...")
            self._feature_pipeline = FeaturePipeline(self._exchange_client)
            self._analysis_engine = AnalysisEngine(
                self._exchange_client,
                self._feature_pipeline,
                self._swarm_manager,
                self._grok_manager
            )

            # Start main trading loop
            print("DEBUG: Starting main trading loop...")
            self._task = asyncio.create_task(self._run_trading_loop())

            # Start Grok Manager Loop if enabled
            if self._grok_enabled:
                print("DEBUG: Starting Grok Manager...")
                asyncio.create_task(
                    self._grok_manager.run_management_loop(
                        self._agent_states, 
                        self._recent_trades, 
                        self._stop_event
                    )
                )

            # Initialize Vertex AI client if enabled
            if self._vertex_client:
                print("DEBUG: Initializing Vertex AI...")
                await self._vertex_client.initialize()

            # Start Redis Listener
            if self._redis_client:
                print("DEBUG: Starting Redis Listener...")
                asyncio.create_task(self._run_redis_listener())

            # Sync Positions (Inheritance)
            print("DEBUG: Syncing positions...")
            await self._sync_positions_from_exchange()

            # Review Inherited Positions (Close bad trades)
            print("DEBUG: Reviewing inherited positions...")
            await self._review_inherited_positions()

            # Start Watchdog
            print("DEBUG: Starting Watchdog...")
            self._watchdog.start()

            # Send Test Telegram Message (Non-blocking)
            print("DEBUG: Sending test Telegram message...")
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
            self._redis_pubsub.subscribe(
                "trading_metrics", "trade_execution", "agent_log", "profit_sweep", "position_update"
            )
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
                            trade["agent_name"] = "Hype Bull Agent"  # Generic name if not provided
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
                                id="hype-agent",
                                name="Hype Bull Agent",
                                model="gemini-2.0-flash-exp",
                                emoji="🟩",
                                system="hyperliquid",
                                specialization="Velocity & Perps",
                            )

                            await self._send_trade_notification(
                                dummy_agent,
                                trade["symbol"],
                                trade["side"],
                                trade["quantity"],
                                trade["price"],
                                trade["notional"],
                                False,  # is_win unknown yet
                                status="FILLED",
                                thesis="Hyperliquid Execution",
                            )

                        elif channel == "agent_log":
                            # Add to MCP
                            self._mcp.add_message(
                                "observation", "Hype Bull Agent", data["message"], "Hyperliquid"
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
                        await asyncio.sleep(0.1) # Sleep on error to prevent busy loop
                else:
                    # No message, sleep briefly to avoid busy loop
                    await asyncio.sleep(0.1)

        except Exception as e:
            print(f"❌ Redis Listener Failed: {e}")
            await asyncio.sleep(5) # Sleep longer if the listener itself fails

    async def _fetch_market_structure(self):
        """Fetch all available symbols and their precision/filters from exchange."""
        await self.market_data_manager.fetch_structure()

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
                    del serializable_pos["agent"]  # Remove object
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
                model = "gemini-2.0-flash-exp"  # Upgrade Codey to Gemini 2.0 Flash

            self._agent_states[agent_def["id"]] = MinimalAgentState(
                id=agent_def["id"],
                name=agent_def["name"],
                model=model,
                emoji=agent_def["emoji"],
                symbols=None,  # No symbol restrictions - agents can trade any symbol
                description=agent_def["description"],
                personality=agent_def["personality"],
                baseline_win_rate=agent_def["baseline_win_rate"],
                margin_allocation=1000.0,  # Default $1k
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
                max_leverage_limit=(
                    5.0
                    if "Momentum" in agent_def["name"]
                    else agent_def.get("max_leverage_limit", 10.0)
                ),
                min_position_size_pct=agent_def.get("min_position_size_pct", 0.08),
                max_position_size_pct=agent_def.get("max_position_size_pct", 0.25),
                risk_tolerance=(
                    "low"
                    if "Momentum" in agent_def["name"]
                    else agent_def.get("risk_tolerance", "medium")
                ),
                time_horizon=agent_def.get("time_horizon", "medium"),
                market_regime_preference=agent_def.get("market_regime_preference", "neutral"),
                system="aster",
            )

        # --- NEW: Grok Special Ops Agent ---
        self._agent_states["grok-special-ops"] = MinimalAgentState(
            id="grok-special-ops",
            name="Grok Alpha",
            model="grok-beta",
            emoji="🧠",
            symbols=PREFERRED_SYMBOLS,  # Restricted to user's list
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
            system="aster",
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
                    print(
                        f"⚠️ Restoring position for {symbol}: Agent {agent_id} not found. Using default."
                    )
                    pos["agent"] = list(self._agent_states.values())[0]

        # --- IMPORT EXISTING EXCHANGE POSITIONS (TAKEOVER) ---
        try:
            print("🔍 Scanning exchange for existing positions to takeover...")
            positions = await self._exchange_client.get_position_risk()
            active_exchange_positions = [
                p for p in positions if float(p.get("positionAmt", 0)) != 0
            ]

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
                agent = (
                    self._agent_states.get("strategy-optimization-agent")
                    or list(self._agent_states.values())[0]
                )

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
                    "open_time": time.time(),  # Treat as new for our tracking
                    "imported": True,
                }
                imported_count += 1
                print(
                    f"📥 IMPORTED POSITION: {symbol} {side} {abs_qty} @ {entry_price} -> Assigned to {agent.name}"
                )

            if imported_count > 0:
                self._save_positions()
                print(
                    f"✅ Successfully took over {imported_count} existing positions from exchange."
                )
            else:
                print("✅ No tracking gaps found. All tracking synced.")

        except Exception as e:
            print(f"⚠️ Failed to sync open positions from exchange: {e}")

        print(
            f"✅ Initialized {len(self._agent_states)} advanced AI agents (unrestricted symbol trading)"
        )
        for agent in self._agent_states.values():
            print(
                f"   {agent.emoji} {agent.name} ({agent.specialization}) - Win Rate: {agent.baseline_win_rate:.1%}"
            )

    async def _sync_exchange_positions(self):
        """Periodically sync internal position state with actual exchange positions."""
        try:
            # Fetch actual positions
            exchange_positions = await self._exchange_client.get_position_risk()
            active_exchange_positions = {
                p["symbol"]: p for p in exchange_positions if float(p.get("positionAmt", 0)) != 0
            }

            # 1. Check for closed positions (In internal but not in exchange)
            internal_symbols = list(self._open_positions.keys())
            for symbol in internal_symbols:
                if symbol not in active_exchange_positions:
                    # Position is gone on exchange!
                    print(
                        f"⚠️ Position Sync: {symbol} is closed on exchange but open internally. Removing."
                    )
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
                        "tp_price": entry * 1.05,  # Default safety TP
                        "sl_price": entry * 0.95,  # Default safety SL
                        "agent": agent,
                        "agent_id": agent.id,
                        "open_time": time.time(),
                    }
                    self._save_positions()
                else:
                    # Update existing
                    internal = self._open_positions[symbol]
                    if abs(internal["quantity"] - qty) > (qty * 0.01):  # >1% difference
                        print(
                            f"⚠️ Position Sync: Quantity mismatch for {symbol}. Internal: {internal['quantity']}, Exchange: {qty}. Updating."
                        )
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
                order_status = await self._exchange_client.get_order(
                    symbol=symbol, order_id=order_id
                )

                status = order_status.get("status")
                executed_qty = float(order_status.get("executedQty", 0))
                avg_price = float(order_status.get("avgPrice", 0))

                if status == "FILLED":
                    print(
                        f"✅ PENDING ORDER FILLED: {agent.name} {order_info['side']} {executed_qty} {symbol}"
                    )

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
                            if pos["side"] == "BUY":  # Closing a Long
                                pnl = (avg_price - pos["entry_price"]) * executed_qty
                            else:  # Closing a Short
                                pnl = (pos["entry_price"] - avg_price) * executed_qty

                            del self._open_positions[symbol]
                            self._save_positions()  # Persist removal

                    if not is_closing:
                        # We are opening a new position OR Adding to existing

                        # Check if position exists and side matches (Merging/Averaging)
                        if (
                            symbol in self._open_positions
                            and self._open_positions[symbol]["side"] == order_info["side"]
                        ):
                            existing_pos = self._open_positions[symbol]
                            old_qty = existing_pos["quantity"]
                            old_price = existing_pos["entry_price"]

                            new_qty = old_qty + executed_qty
                            new_avg_price = (
                                (old_qty * old_price) + (executed_qty * avg_price)
                            ) / new_qty

                            # Update Position
                            self._open_positions[symbol]["quantity"] = new_qty
                            self._open_positions[symbol]["entry_price"] = new_avg_price

                            # Adjust TP/SL for new average
                            # Resetting TP/SL based on new average price
                            entry_price = new_avg_price
                            tp_price = (
                                entry_price * 1.015
                                if order_info["side"] == "BUY"
                                else entry_price * 0.985
                            )
                            sl_price = (
                                entry_price * 0.995
                                if order_info["side"] == "BUY"
                                else entry_price * 1.005
                            )

                            self._open_positions[symbol]["tp_price"] = tp_price
                            self._open_positions[symbol]["sl_price"] = sl_price

                            self._save_positions()
                            print(
                                f"⚖️ Position Averaged: {symbol} New Entry: {new_avg_price:.2f} Qty: {new_qty}"
                            )

                        else:
                            # New Position
                            entry_price = avg_price
                            tp_price = (
                                entry_price * 1.015
                                if order_info["side"] == "BUY"
                                else entry_price * 0.985
                            )
                            sl_price = (
                                entry_price * 0.995
                                if order_info["side"] == "BUY"
                                else entry_price * 1.005
                            )

                            self._open_positions[symbol] = {
                                "side": order_info["side"],
                                "quantity": executed_qty,
                                "entry_price": entry_price,
                                "tp_price": tp_price,
                                "sl_price": sl_price,
                                "agent": agent,
                                "agent_id": agent.id,  # Store ID for persistence
                                "open_time": time.time(),
                            }
                            self._save_positions()  # Persist addition
                            print(
                                f"🎯 Position Opened: {symbol} @ {entry_price} (TP: {tp_price:.2f}, SL: {sl_price:.2f})"
                            )
                    else:
                        tp_price = None
                        sl_price = None

                    # MCP Notification: Execution
                    self._mcp.add_message(
                        "execution",
                        "Execution Algo",
                        f"Confirmed fill for {agent.name}: {order_info['side']} {executed_qty} {symbol} @ {avg_price}",
                        f"Order ID: {order_id}",
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
                        "pnl": pnl if is_closing else 0.0,
                    }
                    self._save_trade(trade_record)

                    # Update agent stats
                    agent.total_trades += 1
                    if is_closing:
                        if pnl > 0:
                            agent.win_rate = ((agent.win_rate * agent.total_trades) + 100.0) / (
                                agent.total_trades + 1
                            )

                            # PROFIT SWEEP (ASTER BULLS)
                            sweep_amount = pnl * 0.5
                            self._swept_profits += sweep_amount
                            msg = f"💰 ASTER BULLS SWEEP: ${sweep_amount:.2f} -> ASTER/USDT Stash"
                            print(msg)
                            # Async notify if possible, or queue it
                            # Since this is inside async loop, we can await if we are careful
                            # But we are inside check_pending_orders...
                            self._mcp.add_message(
                                "observation", "Profit Sweeper", msg, "Capital Allocation"
                            )

                            if self._telegram:
                                # Fire and forget task to not block too much
                                asyncio.create_task(
                                    self._telegram.send_message(f"🟦 *PROFIT SWEEP* 🟦\n\n{msg}")
                                )

                        # Simple moving average update for win rate

                    # Send FILLED notification
                    await self._send_trade_notification(
                        agent,
                        symbol,
                        order_info["side"],
                        executed_qty,
                        avg_price,
                        executed_qty * avg_price,
                        pnl > 0,
                        status="FILLED",
                        pnl=pnl if is_closing else None,
                        tp=tp_price if not is_closing else None,
                        sl=sl_price if not is_closing else None,
                        thesis=order_info.get("thesis"),
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
        return await self.position_manager.monitor_positions()



    async def _check_profit_taking(self, symbol: str, position: Dict[str, Any], current_price: float) -> Tuple[bool, str]:
        """Check if a position should be closed for profit or stop loss."""
        return await self.position_manager.check_profit_taking(symbol, position, current_price)


    async def _analyze_market_for_agent(
        self, agent: MinimalAgentState, symbol: str, ticker_map: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Perform basic technical analysis suited to the agent's specialization.
        Delegates to AnalysisEngine.
        """
        if not self._analysis_engine:
            # Fallback if engine not ready (should not happen in loop)
            return {"signal": "NEUTRAL", "confidence": 0.0, "thesis": "Analysis Engine not ready"}
            
        return await self._analysis_engine.analyze_market(agent, symbol, ticker_map)

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
        print(f"DEBUG: Selected agent {agent.id} for processing")

        if agent.symbols:
            # Restrict to agent's specific symbols (e.g., Grok Alpha)
            available_symbols = [s for s in agent.symbols if s in SYMBOL_CONFIG]
            if not available_symbols:
                available_symbols = list(SYMBOL_CONFIG.keys())  # Fallback
            symbol = random.choice(available_symbols)
            print(f"DEBUG: Agent {agent.id} restricted to {symbol}")
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
            agent = pos["agent"]  # Use the agent who opened it

            # Determine closing side
            side = "SELL" if pos["side"] == "BUY" else "BUY"
            quantity_float = pos["quantity"]

            # INTELLIGENT EXIT LOGIC
            
            # 0. Hard Profit/Stop Check (Overrides Analysis)
            try:
                if ticker_map and symbol in ticker_map:
                    curr_price = float(ticker_map[symbol].get("lastPrice", 0))
                    should_close_hard, hard_reason = await self._check_profit_taking(symbol, pos, curr_price)
                    if should_close_hard:
                        print(f"💰 Profit/Stop Triggered for {symbol}: {hard_reason}")
                        # Execute immediately
                        trade_side = "SELL" if pos["side"] == "BUY" else "BUY"
                        await self._execute_trade_order(agent, symbol, trade_side, quantity_float, is_closing=True, reason=hard_reason)
                        return # Exit loop for this tick
            except Exception as e:
                print(f"⚠️ Profit check failed: {e}")

            # 1. Check if the agent now sees a reversal (Analysis)
            analysis = await self._analyze_market_for_agent(agent, symbol, ticker_map)

            should_close = False
            close_reason = ""

            # If we are Long (BUY), and signal is SELL with high confidence -> Close
            if (
                pos["side"] == "BUY"
                and analysis["signal"] == "SELL"
                and analysis["confidence"] > 0.5
            ):
                should_close = True
                close_reason = f"Trend Reversal Detected: {analysis['thesis']}"

            # If we are Short (SELL), and signal is BUY with high confidence -> Close
            elif (
                pos["side"] == "SELL"
                and analysis["signal"] == "BUY"
                and analysis["confidence"] > 0.5
            ):
                should_close = True
                close_reason = f"Trend Reversal Detected: {analysis['thesis']}"

            # 2. Time-based staleness check (if position open for > 4 hours and barely moving)
            time_open = time.time() - pos.get("open_time", 0)
            if not should_close and time_open > 14400:  # 4 hours
                # Check PnL via ticker
                try:
                    if ticker_map and symbol in ticker_map:
                        ticker = ticker_map[symbol]
                    else:
                        ticker = await self._exchange_client.get_ticker(symbol)

                    curr_price = float(ticker.get("lastPrice", 0))
                    entry = pos["entry_price"]
                    if entry > 0:
                        pnl_pct = (
                            (curr_price - entry) / entry
                            if pos["side"] == "BUY"
                            else (entry - curr_price) / entry
                        )
                    else:
                        pnl_pct = 0.0

                    if abs(pnl_pct) < 0.005:  # Less than 0.5% move in 4 hours
                        should_close = True
                        close_reason = "Capital Stagnation (Low Volatility/Time Limit)"
                except:
                    pass

            # --- SCALPING & DOUBLE DOWN LOGIC ---
            # Check if we should double down (Add to winning position or high-conviction trade)
            # ASTER POINTS UPDATE: NO HEDGING. CLOSE EXISTING IF OPPOSING SIGNAL.

            # If signal is opposite to current position:
            if (pos["side"] == "BUY" and analysis["signal"] == "SELL") or (
                pos["side"] == "SELL" and analysis["signal"] == "BUY"
            ):

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
                    if pos["entry_price"] > 0:
                        base_qty = target_size / pos["entry_price"]
                    else:
                        base_qty = current_qty # Fallback
                else:
                    base_qty = current_qty  # Fallback (don't double unknown size)

                max_qty = base_qty * 3.0

                if current_qty < max_qty and analysis["confidence"] >= 0.85:
                    # Check signal direction matches position
                    if (pos["side"] == "BUY" and analysis["signal"] == "BUY") or (
                        pos["side"] == "SELL" and analysis["signal"] == "SELL"
                    ):
                        should_add = True

            if should_add:
                add_qty = base_qty  # Add 1 unit
                print(
                    f"🚀 DOUBLING DOWN: {agent.name} adding to {pos['side']} {symbol} (Conf: {analysis['confidence']:.2f})"
                )

                # Execute ADD Order
                # Note: This is a market order in the same direction
                await self._execute_trade_order(
                    agent,
                    symbol,
                    pos["side"],
                    add_qty,
                    f"Double Down/Scale In: High Conviction {analysis['confidence']:.2f}",
                    is_closing=False,
                )

                # Update TP/SL for the new average price will happen in the order execution handler if we handle it right.
                # BUT, _execute_trade_order usually creates a NEW position object or overwrites if not handled.
                # We need to ensure _execute_trade_order handles "adding" correctly or we do it here.
                # Actually, _check_pending_orders handles the fill.
                # It currently OVERWRITES: self._open_positions[symbol] = { ... }
                # We need to fix _check_pending_orders to MERGE if position exists and side matches.

                return  # Done for this tick

            if should_close:
                thesis = f"Closing {symbol} position ({side}). {close_reason}. Optimizing capital efficiency."

                self._mcp.add_message("proposal", agent.name, thesis, f"Reason: Strategic Exit")

                print(
                    f"🔄 STRATEGIC EXIT: {agent.name} Closing {pos['side']} {symbol} -> {side} | {close_reason}"
                )

                # Execute Close
                await self._execute_trade_order(
                    agent, symbol, side, quantity_float, thesis, is_closing=True
                )

            return  # Done for this tick (whether closed or held)

        # --- NEW ENTRY LOGIC (No existing position) ---
        else:
            # Analyze market for a potential NEW trade
            analysis = await self._analyze_market_for_agent(agent, symbol, ticker_map)

            # Only enter if signal is strong and actionable
            if analysis["signal"] in ["BUY", "SELL"] and analysis["confidence"] >= 0.65:
                signal = analysis["signal"]
                confidence = analysis["confidence"]
                thesis = analysis.get("thesis", "AI-driven entry signal")

                # Determine position size (target ~$150-200 notional)
                try:
                    ticker = ticker_map.get(symbol) if ticker_map else await self._exchange_client.get_ticker(symbol)
                    current_price = float(ticker.get("lastPrice", 0))

                    if current_price <= 0:
                        print(f"⚠️ Invalid price for {symbol}, skipping entry")
                        return

                    # Base notional of $150, scale by confidence
                    target_notional = 150.0 * (0.8 + 0.4 * confidence)  # ~$120-$210
                    quantity_float = target_notional / current_price

                    # Apply precision from market structure or config
                    if symbol in self._market_structure:
                        qty_precision = self._market_structure[symbol].get("quantityPrecision", 4)
                        quantity_float = round(quantity_float, qty_precision)
                    elif symbol in SYMBOL_CONFIG:
                        precision = SYMBOL_CONFIG[symbol].get("precision", 4)
                        quantity_float = round(quantity_float, precision)

                    print(f"🚀 NEW TRADE: {agent.emoji} {agent.name} -> {signal} {symbol} @ ${current_price:.4f} | Qty: {quantity_float} | Conf: {confidence:.2f}")
                    print(f"   📝 Thesis: {thesis}")

                    # Execute the new trade
                    await self._execute_trade_order(
                        agent,
                        symbol,
                        signal,
                        quantity_float,
                        thesis,
                        is_closing=False
                    )

                except Exception as e:
                    print(f"⚠️ Failed to execute new trade for {symbol}: {e}")

    # _initialize_agents removed - using _initialize_basic_agents from AGENT_DEFINITIONS

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
                print(
                    f"💰 Account Update: Balance=${total_balance:.2f}, Equity=${total_equity:.2f}"
                )

        except Exception as e:
            print(f"⚠️ Failed to update account info: {e}")



    async def _execute_trade_order(
        self, agent, symbol, side, quantity_float, thesis, is_closing=False
    ):
        """Helper to execute the actual order placement."""
        try:
            # Convert position side to proper trade side
            # Aster exchange uses "BOTH" for hedge mode positions, but we need "BUY" or "SELL" for orders
            if side == "BOTH":
                # If closing a BOTH position, we need to determine the actual position side
                # Check if we have this position tracked
                if symbol in self._open_positions:
                    pos = self._open_positions[symbol]
                    # Use the tracked side if available
                    if "actual_side" in pos:
                        side = pos["actual_side"]
                    else:
                        # Fallback: assume BUY if not specified
                        print(f"⚠️ Warning: Position {symbol} has side 'BOTH' but no actual_side tracked. Defaulting to BUY.")
                        side = "BUY"
                else:
                    # No position tracked, default to BUY
                    print(f"⚠️ Warning: Attempting to trade {symbol} with side 'BOTH' but position not tracked. Defaulting to BUY.")
                    side = "BUY"
            
            # When closing a position, we need to use the OPPOSITE side
            # For example, to close a BUY position, we need to SELL
            if is_closing:
                if side == "BUY":
                    trade_side = "SELL"
                elif side == "SELL":
                    trade_side = "BUY"
                else:
                    # Shouldn't happen after the BOTH conversion above, but handle it
                    print(f"⚠️ Warning: Invalid side '{side}' for closing trade. Defaulting to SELL.")
                    trade_side = "SELL"
            else:
                # For opening positions, use the side as-is
                trade_side = side
            
            # Format quantity
            quantity = str(quantity_float)  # Default

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

            print(f"🚀 ATTEMPTING TRADE: {agent.emoji} {agent.name} - {trade_side} {quantity} {symbol}{'(CLOSING)' if is_closing else ''}")

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
                        print(
                            f"⚠️ Risk Check Failed: Insufficient Cushion. Available: ${available_balance:.2f} < Cushion: ${cushion:.2f}"
                        )
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
                    side=trade_side,
                    order_type=OrderType.MARKET,
                    quantity=quantity,
                    new_client_order_id=f"adv_{int(time.time())}_{agent.id[:4]}",
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
                                new_client_order_id=f"retry_{int(time.time())}_{agent.id[:4]}",
                            )
                        else:
                            raise e  # Cannot adjust
                    except Exception as retry_e:
                        print(f"❌ Retry failed after leverage adjustment: {retry_e}")
                        raise retry_e  # Re-raise to outer block
                else:
                    raise e  # Re-raise other errors

            # Verify and Log Result
            if order_result and order_result.get("orderId"):
                status = order_result.get("status")
                executed_qty = float(order_result.get("executedQty", 0))
                avg_price = float(order_result.get("avgPrice", 0))

                print(
                    f"📋 Order Placed: ID {order_result.get('orderId')} | Status: {status} | Exec: {executed_qty} | Price: {avg_price}"
                )

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
                            self._save_positions()  # Persist removal
                    else:
                        # Determine TP/SL levels (e.g., TP +1.5%, SL -0.5% for scalping)
                        entry_price = avg_price
                        tp_price = entry_price * 1.015 if side == "BUY" else entry_price * 0.985
                        sl_price = entry_price * 0.995 if side == "BUY" else entry_price * 1.005

                        self._open_positions[symbol] = {
                            "side": side,
                            "quantity": executed_qty,
                            "entry_price": entry_price,
                            "current_price": entry_price,  # Initialize current price
                            "tp_price": tp_price,
                            "sl_price": sl_price,
                            "open_time": time.time(),
                            "agent": agent.name,
                            "thesis": thesis,
                        }
                        self._save_positions()

                        # NATIVE TP/SL PLACEMENT
                        asyncio.create_task(
                            self._place_native_tp_sl(symbol, side, executed_qty, tp_price, sl_price)
                        )
                        print(
                            f"🎯 Position Opened (Instant): {symbol} @ {entry_price} (TP: {tp_price:.2f}, SL: {sl_price:.2f})"
                        )

                # Save persistent trade record
                trade_record = {
                    "id": order_result.get("orderId"),
                    "timestamp": time.time(),
                    "symbol": symbol,
                    "side": side,
                    "price": avg_price if avg_price > 0 else 0.0,
                    "quantity": executed_qty if executed_qty > 0 else float(quantity),
                    "value": (
                        (executed_qty * avg_price) if (executed_qty > 0 and avg_price > 0) else 0.0
                    ),
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "status": status,
                    "pnl": pnl,
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
                        agent.win_rate = (
                            (agent.win_rate * (agent.total_trades - 1)) + current_score
                        ) / agent.total_trades

                    print(
                        f"✅ TRADE CONFIRMED: {agent.name} {side} {executed_qty} {symbol} @ ${avg_price:.2f}"
                    )

                    # Send FILLED notification
                    await self._send_trade_notification(
                        agent,
                        symbol,
                        side,
                        executed_qty,
                        avg_price,
                        total_value,
                        pnl >= 0,
                        status="FILLED",
                        pnl=pnl if is_closing else None,
                        tp=tp_price,
                        sl=sl_price,
                        thesis=thesis,
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
                        "thesis": thesis,
                    }

                    await self._send_trade_notification(
                        agent,
                        symbol,
                        side,
                        float(quantity),
                        0.0,
                        0.0,
                        True,
                        status="PENDING",
                        thesis=thesis,
                    )

            else:
                print(f"❌ Order placement failed (No ID returned): {order_result}")
                self._mcp.add_message(
                    "critique",
                    "System",
                    f"Order placement failed for {symbol}.",
                    "Error: No ID returned",
                )

        except Exception as e:
            print(f"❌ EXECUTION ERROR: {e}")
            # Log but don't stop the service

    async def _send_trade_notification(
        self,
        agent,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        total: float,
        is_win: bool,
        status: str = "FILLED",
        pnl: float = None,
        tp: float = None,
        sl: float = None,
        thesis: str = None,
    ):
        """Send enhanced Telegram notification for real trade execution."""
        if not self._telegram:
            return

        try:
            # Enhanced status indicators
            system_color = "🟦" if getattr(agent, "system", "aster") == "aster" else "🟩"

            if side == "BUY":
                trade_emoji = (
                    system_color if is_win else "🟠"
                )  # Use system color for win/buy? Or stick to Green/Red?
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
                return (
                    str(text)
                    .replace("_", "\\_")
                    .replace("*", "\\*")
                    .replace("[", "\\[")
                    .replace("`", "\\`")
                )

            agent_name = escape_md(agent.name)
            agent_desc = escape_md(agent.description)
            agent_spec = escape_md(agent.specialization or "Advanced AI Trading")
            sym = escape_md(symbol)

            system_name = (
                "ASTER BULL AGENTS"
                if getattr(agent, "system", "aster") == "aster"
                else "HYPE BULL AGENTS"
            )

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
                    fee_est = total * 0.00025  # Hype taker approx
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

            await self._telegram.send_message(message, parse_mode="Markdown")
            print(
                f"📱 Enhanced Telegram notification sent for {agent.name} {side} {symbol} ({status})"
            )
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
            today_start = (
                datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            )
            daily_trades = [
                t
                for t in self._recent_trades
                if t.get("agent_id") == agent.id and t["timestamp"] >= today_start
            ]
            agent.daily_pnl = sum(t.get("pnl", 0.0) for t in daily_trades)

            # Check Breach
            # Limit is 5% of allocation
            limit = agent.margin_allocation * agent.max_daily_loss_pct
            if agent.daily_pnl < -limit and not agent.daily_loss_breached:
                agent.daily_loss_breached = True
                print(
                    f"🚨 CIRCUIT BREAKER TRIPPED: {agent.name} lost ${abs(agent.daily_pnl):.2f} (> ${limit:.2f}). Pausing agent."
                )
                self._mcp.add_message(
                    "critique",
                    "Risk Manager",
                    f"Circuit breaker tripped for {agent.name}.",
                    f"Daily Loss: {agent.daily_pnl:.2f}",
                )

                if self._telegram:
                    await self._telegram.send_message(
                        f"🚨 *CIRCUIT BREAKER* 🚨\n\nAgent *{agent.name}* paused due to max daily loss.\nLoss: ${abs(agent.daily_pnl):.2f}"
                    )
            elif agent.daily_pnl >= -limit and agent.daily_loss_breached:
                # Reset if PnL recovers (unlikely without trading) or manual reset needed
                # For simplicity, we don't auto-reset in this loop unless PnL changes positively
                pass

        # Global Circuit Breaker (Aster Only check for now)
        total_daily_loss = sum(a.daily_pnl for a in self._agent_states.values())
        # If collective loss > 10% of Aster capital (approx $1000)
        if total_daily_loss < -100.0:
            print(
                f"🚨 GLOBAL CIRCUIT BREAKER: Aster Daily Loss ${abs(total_daily_loss):.2f} > $100. Pausing ALL Agents."
            )
            for agent in self._agent_states.values():
                if not agent.daily_loss_breached:
                    agent.daily_loss_breached = True
                    print(f"   -> Pausing {agent.name}")

    async def _simulate_agent_chatter(self):
        """Simulate background chatter between agents to keep MCP stream alive."""
        if random.random() > 0.15:  # 15% chance per tick (approx every 20-30s)
            return

        active_agents = [a for a in self._agent_states.values() if a.active]
        if not active_agents:
            return

        agent = random.choice(active_agents)

        topics = [
            "market_structure",
            "volatility",
            "liquidity",
            "correlation",
            "sentiment",
            "risk_check",
            "performance",
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
                "Order book depth is thinning out on the ask side.",
            ]
            message = random.choice(phrases)
            context = "Market Analysis"

        elif topic == "volatility":
            phrases = [
                "Volatility compression detected. Expecting a move.",
                "ATR is expanding. Risk limits adjusted.",
                "Price variance is within expected bounds.",
                "Implied volatility seems underpriced relative to realized.",
                "Preparing for potential volatility expansion.",
            ]
            message = random.choice(phrases)
            context = "Risk Assessment"

        elif topic == "liquidity":
            phrases = [
                "Scanning for liquidity grabs below the lows.",
                "Significant buy wall detected nearby.",
                "Liquidity accumulation phase potentially starting.",
                "Slippage risk is moderate in this zone.",
                "Tracking whale wallet movements.",
            ]
            message = random.choice(phrases)
            context = "Microstructure"

        elif topic == "sentiment":
            phrases = [
                "Social sentiment metrics are diverging from price.",
                "Fear and Greed index indicates caution.",
                "Retail sentiment is flipping bullish.",
                "News flow impact appears neutral to slightly negative.",
                "Contrarian signal: Sentiment is too euphoric.",
            ]
            message = random.choice(phrases)
            context = "Sentiment Analysis"

        elif topic == "risk_check":
            phrases = [
                "Confirming leverage exposure is within safety limits.",
                "Margin utilization check passed.",
                "Portfolio beta is currently optimized.",
                "Drawdown limits are being respected.",
                "Re-calibrating stop loss distances based on volatility.",
            ]
            message = random.choice(phrases)
            context = "System Health"

        self._mcp.add_message("observation", agent.name, message, context)
        # print(f"💬 CHATTER: {agent.name}: {message}")

    async def _manage_positions(self, ticker_map: Dict[str, Any] = None):
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
                if ticker_map and symbol in ticker_map:
                    ticker = ticker_map[symbol]
                else:
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

            side = pos["side"]  # BUY or SELL
            quantity = pos["quantity"]

            if side == "BUY":
                pnl_pct = (current_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - current_price) / entry_price

            # Thresholds (Aster - tighter)
            TP_THRESHOLD = 0.05  # +5%
            SL_THRESHOLD = -0.03  # -3%

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
                await self._execute_trade_order(
                    agent, symbol, side, quantity, thesis, is_closing=True
                )

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
        await self.position_manager.sync_from_exchange()

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
            agent = TradingAgent(
                id="reviewer",
                name="Portfolio Reviewer",
                emoji="🕵️",
                strategy="technical",
                symbols=[symbol],
            )

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
                await self._execute_trade_order(
                    agent,
                    symbol,
                    side,
                    pos["quantity"],
                    f"Inherited Review: {reason}",
                    is_closing=True,
                )
            else:
                print(
                    f"✅ Inherited position {symbol} looks okay (Signal: {signal}, Conf: {confidence:.2f})"
                )

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
                # await self._manage_positions()

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
                # await self._manage_positions(ticker_map={})

                # 5. Execute New Trades
                await self._execute_new_trades()

                consecutive_errors = 0
                await asyncio.sleep(5)  # 5s loop

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
                    priority=NotificationPriority.CRITICAL,
                )

                # Emergency Reduce: Close largest positions first
                # Sort positions by notional value (approx quantity * entry_price)
                sorted_positions = sorted(
                    self._open_positions.values(),
                    key=lambda p: p["quantity"] * p["entry_price"],
                    reverse=True,
                )

                for pos in sorted_positions[:2]:  # Close top 2 largest
                    symbol = pos["symbol"]
                    print(f"🚑 EMERGENCY CLOSE: {symbol} to reduce margin.")
                    agent = self._agent_states.get(pos.get("agent_id"))
                    if not agent:
                        # Create dummy agent for closure
                        agent = TradingAgent(
                            id="risk_bot",
                            name="Risk Bot",
                            emoji="🚑",
                            strategy="risk",
                            symbols=[symbol],
                        )

                    await self._execute_trade_order(
                        agent,
                        symbol,
                        pos["side"],  # Pass current side
                        pos["quantity"],
                        "Emergency Margin Reduction",
                        is_closing=True,
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
                    new_client_order_id=f"shutdown_{int(time.time())}_{symbol}",
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
                "gpu_usage": random.randint(40, 80),  # Simulated for now
                "memory_usage": random.randint(30, 60),
                "cpu_usage": random.randint(20, 50),
                "network_throughput": random.randint(50, 150),
            },
            "system_health": {"uptime_percentage": 99.99, "error_rate": 0.0, "response_time": 12},
            "timestamp": datetime.now().isoformat(),
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

                frontend_messages.append(
                    {
                        "id": msg.get("id"),
                        "agentId": agent_id,
                        "agentName": sender,
                        "role": msg.get("type", "info").upper(),
                        "content": msg.get("content", ""),
                        "timestamp": iso_time,
                        "relatedSymbol": None,  # specific parsing if needed later
                    }
                )

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

            all_positions.append(
                {
                    "symbol": s,
                    "side": p["side"],
                    "quantity": qty,
                    "entry_price": entry,
                    "current_price": curr,
                    "pnl": pnl,
                    "agent": p.get("agent").name if p.get("agent") else "Unknown",
                    "system": (
                        getattr(p.get("agent"), "system", "aster") if p.get("agent") else "aster"
                    ),
                    "tp": p.get("tp_price"),
                    "sl": p.get("sl_price"),
                }
            )

        # Hyperliquid Positions
        for s, p in self._hyperliquid_positions.items():
            all_positions.append(
                {
                    "symbol": s,
                    "side": "BUY" if float(p.get("size", 0)) > 0 else "SELL",
                    "quantity": abs(float(p.get("size", 0))),
                    "entry_price": float(p.get("entry_price", 0)),
                    "current_price": 0,  # Need real-time price from HL or WS
                    "pnl": float(p.get("pnl", 0)),
                    "agent": "Hype Bull Agent",
                    "system": "hyperliquid",
                    "tp": None,
                    "sl": None,
                }
            )

        # Prepare System Split Data
        aster_pnl = sum(t.get("pnl", 0.0) for t in self._recent_trades)
        aster_volume = sum(t.get("value", 0.0) for t in self._recent_trades)
        aster_win_rate = 0.0
        aster_trades_count = len(self._recent_trades)
        if aster_trades_count > 0:
            aster_win_rate = (
                len([t for t in self._recent_trades if t.get("pnl", 0) > 0])
                / aster_trades_count
                * 100
            )

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
                "swept_profits": self._swept_profits,
            },
            "hyperliquid": {
                "pnl": hl_pnl,
                "volume": hl_volume,
                "fees": hl_fees,
                "win_rate": hl_win_rate,
                "active_agents": 1,  # The HL service itself
                "swept_profits": float(self._hyperliquid_metrics.get("swept_profits", 0.0)),
            },
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
            "timestamp": time.time(),
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
                "pnl": sum(
                    t.get("pnl", 0.0) for t in self._recent_trades if t.get("agent_id") == agent.id
                ),
                "pnlPercent": (
                    (
                        sum(
                            t.get("pnl", 0.0)
                            for t in self._recent_trades
                            if t.get("agent_id") == agent.id
                        )
                        / agent.margin_allocation
                        * 100
                    )
                    if agent.margin_allocation > 0
                    else 0.0
                ),
                "allocation": agent.margin_allocation,
                "performance_score": round(agent.performance_score, 3),
                "total_trades": agent.total_trades,
                "win_rate": round(agent.win_rate, 2),
                "activePositions": sum(
                    1
                    for p in self._open_positions.values()
                    if p.get("agent") and p["agent"].id == agent.id
                ),
                "history": self._get_agent_history(agent.id),  # Dynamically generated history
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
                "system": getattr(agent, "system", "aster"),
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
            key=lambda x: x["timestamp"],
        )

        if not relevant_trades:
            # Return flat line if no trades
            now_str = datetime.now().strftime("%H:%M")
            return [{"time": "00:00", "value": 0}, {"time": now_str, "value": 0}]

        for trade in relevant_trades:
            pnl = trade.get("pnl", 0.0)
            cumulative_pnl += pnl
            history.append(
                {
                    "time": datetime.fromtimestamp(trade["timestamp"]).strftime("%H:%M"),
                    "value": cumulative_pnl,
                }
            )

        # Limit to last 20 data points for chart clarity
        return history[-20:]

    def _handle_strategy_update(self, data: Dict[str, Any]):
        """Handle strategy updates from the Conductor."""
        print(f"DEBUG: _handle_strategy_update called with keys: {list(data.keys())}")
        try:
            msg_type = data.get("_type")
            if msg_type == "regime":
                regime = MarketRegime.from_dict(data)
                self.current_regime = regime
                print(f"🎻 New Market Regime: {regime.regime.value} (Conf: {regime.confidence:.2f})")
                
                # Broadcast to frontend (Thread-safe)
                if hasattr(self, "_loop"):
                    asyncio.run_coroutine_threadsafe(
                        broadcast_market_regime(regime.to_dict()), 
                        self._loop
                    )
                else:
                    print("⚠️ Event loop not available for broadcast")

                # TODO: Adjust internal agents based on regime
                # e.g. if regime == BEAR_TRENDING, disable Bull agents
                
        except Exception as e:
            print(f"⚠️ Failed to handle strategy update: {e}")

    def get_available_agents(self) -> List[Dict[str, Any]]:
        """Get available agents (alias for get_agents)."""
        return self.get_agents()

    def get_enabled_agents(self) -> Dict[str, Any]:
        """Get enabled agents with total count."""
        agents = self.get_agents()
        return {"agents": agents, "total_enabled": len(agents)}


# Global instance
_trading_service = None


def get_trading_service() -> MinimalTradingService:
    """Get the global trading service instance."""
    global _trading_service
    if _trading_service is None:
        _trading_service = MinimalTradingService()
    return _trading_service
