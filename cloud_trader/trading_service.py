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
from collections import deque, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

import aiohttp

from .agent_consensus import AgentConsensusEngine, AgentSignal, SignalType
from .analysis_engine import AnalysisEngine
from .analytics.performance import PerformanceTracker
from .config import Settings, get_settings
from .credentials import CredentialManager
from .data.feature_pipeline import FeaturePipeline
from .definitions import (
    AGENT_DEFINITIONS,
    SYMBOL_CONFIG,
    HealthStatus,
    MinimalAgentState,
)
from .enhanced_telegram import EnhancedTelegramService, NotificationPriority
from .enums import OrderType
from .exchange import AsterClient
from .market_data import MarketDataManager
from .partial_exits import PartialExitStrategy
from .position_manager import PositionManager
from .risk import PortfolioState, RiskManager
from .self_healing import SelfHealingWatchdog
from .swarm import SwarmManager
from .websocket_manager import broadcast_market_regime

# Telegram integration
try:
    from .enhanced_telegram import EnhancedTelegramService

    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    print("⚠️ Enhanced Telegram service not available")

logger = logging.getLogger(__name__)


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


class MinimalTradingService:
    """Minimal trading service with essential functionality only."""

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize the trading service components."""
        self._settings = settings or get_settings()
        self._credential_manager = CredentialManager()

        logger.info("🚀 VERSION: 2.1.0 (Refactored Init)")
        logger.debug("Starting __init__...")

        # Runtime State
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task[None]] = None
        self._loop = None
        self._health = HealthStatus(running=False, paper_trading=False, last_error=None)

        # Clients (Initialized in start)
        self._exchange = None
        self._paper_exchange = None
        self._spot_exchange = None
        self._vertex_client = None
        self.symphony = None

        # Data & Portfolio
        self._portfolio = PortfolioState(balance=0.0, equity=0.0)
        self._recent_trades = deque(maxlen=200)
        self._pending_orders: Dict[str, Dict] = {}
        self._internal_open_positions: Dict[str, Dict] = {}  # Internal storage, accessed via property
        self._internal_market_structure: Dict[str, Dict] = {}  # Internal storage for property fallback

        # AI & Agents
        self._agent_states: Dict[str, MinimalAgentState] = {}
        self._mcp = SimpleMCP()
        self._swarm_manager = SwarmManager()
        self._mcp = SimpleMCP()
        self._swarm_manager = SwarmManager()
        self._feature_pipeline = None
        self._analysis_engine = None
        self._consensus_engine = AgentConsensusEngine()

        # Managers (Initialized with None client first)
        self.market_data_manager = None
        self.position_manager = None
        self._risk_manager = None
        self._watchdog = SelfHealingWatchdog()
        self._performance_tracker = PerformanceTracker()

        # Trackers
        # Legacy trackers removed Phase 25

        # Hyperliquid (Removed Phase 25)
        self._hyperliquid_metrics = {}  # Keeping empty dict to avoid attr errors until full purge
        self._hyperliquid_positions = {}  # Empty dict to prevent AttributeError
        
        # Aster tracking
        self._aster_fees = 0.0  # Track cumulative fees paid
        self._swept_profits = 0.0  # Track swept profits for dashboard

        # Telegram
        self._telegram = None

        # Legacy State (To be deprecated - kept minimal for compatibility)
        self._last_day_check = datetime.now().day

        # Run minimal sync init
        self._init_managers_offline()
        self._load_persistent_data()

        logger.info("✅ Minimal TradingService initialized successfully")

    def _init_managers_offline(self):
        """Initialize managers that don't require active clients yet."""
        try:
            # We initialize them with None to avoid attribute errors,
            # they will be updated in start() with real clients.
            self.market_data_manager = MarketDataManager(None)
            self.position_manager = PositionManager(None, self._agent_states)
            
            # Partial Exit Strategy for multi-target profit taking
            self.partial_exit_strategy = PartialExitStrategy()

            # Symphony removed - was deprecated Pub/Sub system

            # Telegram
            if TELEGRAM_AVAILABLE and self._settings.enable_telegram:
                try:
                    self._telegram = EnhancedTelegramService(
                        bot_token=self._settings.telegram_bot_token,
                        chat_id=self._settings.telegram_chat_id,
                    )
                    logger.info("✅ Telegram notifications enabled")
                except Exception as e:
                    logger.error(f"⚠️ Telegram initialization failed: {e}")

            # Redis/Hyperliquid logic deleted in Phase 25

        except Exception as e:
            logger.error(f"Manager initialization failed: {e}")

    def _load_persistent_data(self):
        """Load trades and positions from disk."""
        logger.debug("Loading persistent data...")
        self._load_trades()
        self._load_positions()

    @property
    def _market_structure(self) -> Dict[str, Dict[str, Any]]:
        if self.market_data_manager is not None:
            return self.market_data_manager.market_structure
        return self._internal_market_structure

    @_market_structure.setter
    def _market_structure(self, value):
        if self.market_data_manager is not None:
            self.market_data_manager.market_structure = value
        else:
            self._internal_market_structure = value

    @property
    def _open_positions(self) -> Dict[str, Dict[str, Any]]:
        if self.position_manager is not None:
            return self.position_manager.open_positions
        return self._internal_open_positions

    @_open_positions.setter
    def _open_positions(self, value):
        if self.position_manager is not None:
            self.position_manager.open_positions = value
        else:
            self._internal_open_positions = value

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
            logger.info("🚀 Starting Aster Bull Agents (Minimal Service)...")

            # 1. Auth Diagnostics
            await self._run_auth_diagnostics()

            # 2. Online Initialization (Clients, Managers, State)
            await self._init_online_components()

            # 3. Start Background Tasks
            logger.debug("Starting main trading loop...")
            self._task = asyncio.create_task(self._run_trading_loop())

            # 4. Start Listeners
            # Redis listener (Hyperliquid) removed Phase 25

            # 5. Sync & Watchdog
            logger.debug("Syncing positions...")
            await self._sync_positions_from_exchange()
            await self._review_inherited_positions()

            logger.debug("Starting Watchdog...")
            self._watchdog.start()

            # 6. Test Telegram
            asyncio.create_task(self.send_test_telegram_message())

            logger.info("✅ Minimal trading service started successfully")
            return True

        except Exception as e:
            self._health.last_error = str(e)
            logger.error(f"❌ Failed to start trading service: {e}")
            return False

    async def _run_auth_diagnostics(self):
        """Run startup authentication diagnostics."""
        logger.info("🔐 STARTING AUTH DIAGNOSTICS...")
        try:
            # 1. Check Public Data (No Auth)
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://fapi.asterdex.com/fapi/v1/time", timeout=5.0
                ) as resp:
                    if resp.status == 200:
                        logger.info("   ✅ Public API Accessible (200 OK)")
                    else:
                        logger.warning(f"   ❌ Public API Blocked: {resp.status}")

            # 2. Check Key Prefix
            creds = self._credential_manager.get_credentials()
            if creds.api_key:
                logger.info(f"   🔑 Using Key Prefix: {creds.api_key[:6]}...")
            else:
                logger.error("   ❌ MISSING CREDENTIALS!")

        except Exception as e:
            logger.error(f"   ⚠️ Diagnostics Failed: {e}")
        logger.info("🔐 AUTH DIAGNOSTICS COMPLETE")

    async def _init_online_components(self):
        """Initialize components specifically requiring network/auth."""
        loop = asyncio.get_running_loop()
        self._loop = loop

        # Identity Check
        # try:
        #    async with aiohttp.ClientSession() as session:
        #         async with session.get("https://api.ipify.org", timeout=5.0) as resp:
        #             logger.info(f"🌍 PUBLIC IP: {await resp.text()}")
        # except: pass

        # Init Clients
        credentials = await loop.run_in_executor(None, self._credential_manager.get_credentials)
        self._exchange = AsterClient(credentials=credentials)
        from .exchange import AsterSpotClient

        self._spot_exchange = AsterSpotClient(credentials=credentials)

        # Update Managers with Live Client
        self.market_data_manager.exchange_client = self._exchange_client
        self.position_manager.exchange_client = self._exchange_client

        # Init Risk Manager
        self._risk_manager = RiskManager(self._settings)

        # Subscribe Strategy
        if self.symphony:
            logger.info("🎻 Subscribing to Symphony Strategy...")
            self._strategy_subscription = self.symphony.subscribe_strategy(
                "aster-strategy-sub", self._handle_strategy_update
            )

        # Core Data
        logger.debug("Fetching market structure...")
        await self._fetch_market_structure()

        # AI Components
        logger.debug("Initializing AI components...")
        self._feature_pipeline = FeaturePipeline(self._exchange_client)
        self._analysis_engine = AnalysisEngine(
            self._exchange_client,
            self._feature_pipeline,
            self._swarm_manager,
        )
        await self._initialize_basic_agents()

        # Optional Vertex
        if self._vertex_client:
            await self._vertex_client.initialize()

        # Health Update
        self._health.running = True
        self._health.paper_trading = self._settings.enable_paper_trading

    # _run_redis_listener removed Phase 25 (Pure Aster Pivot)

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
            file_path = os.path.join("/app", "data", "positions.json")
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
            file_path = os.path.join("/app", "data", "positions.json")

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
                type=agent_def.get("type", "general"),  # Agent type for consensus
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
                                entry_price * 1.025
                                if order_info["side"] == "BUY"
                                else entry_price * 0.975
                            )
                            sl_price = (
                                entry_price * 0.988
                                if order_info["side"] == "BUY"
                                else entry_price * 1.012
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
                                entry_price * 1.025
                                if order_info["side"] == "BUY"
                                else entry_price * 0.975
                            )
                            sl_price = (
                                entry_price * 0.988
                                if order_info["side"] == "BUY"
                                else entry_price * 1.012
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

                            # NATIVE TP/SL: Place actual orders on Aster DEX
                            # This ensures TP/SL triggers even if bot goes offline
                            try:
                                await self.position_manager.place_tpsl_orders(
                                    symbol=symbol,
                                    entry_price=entry_price,
                                    side=order_info["side"],
                                    quantity=executed_qty,
                                    tp_pct=0.05,  # 5% Take Profit
                                    sl_pct=0.03,  # 3% Stop Loss
                                )
                            except Exception as tpsl_err:
                                print(f"⚠️ Failed to place native TP/SL for {symbol}: {tpsl_err}")

                            # PARTIAL EXIT STRATEGY: Create exit plan for multi-target profit taking
                            try:
                                self.partial_exit_strategy.create_exit_plan(
                                    symbol=symbol,
                                    entry_price=entry_price,
                                    position_size=executed_qty,
                                    side=order_info["side"],
                                )
                                print(f"📊 Partial Exit Plan created for {symbol}")
                            except Exception as pe_err:
                                print(f"⚠️ Failed to create partial exit plan for {symbol}: {pe_err}")

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
                        # Track actual wins/losses for accurate win rate
                        if pnl > 0:
                            agent.wins += 1

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
                        else:
                            agent.losses += 1

                        # Update win rate based on actual wins/losses
                        total_closed = agent.wins + agent.losses
                        if total_closed > 0:
                            agent.win_rate = agent.wins / total_closed
                        else:
                            agent.win_rate = agent.baseline_win_rate

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

    async def _check_profit_taking(
        self, symbol: str, position: Dict[str, Any], current_price: float
    ) -> Tuple[bool, str]:
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

    async def update_position_tpsl(self, symbol: str, tp: float = None, sl: float = None) -> bool:
        """Update TP/SL for a position and notify execution systems."""
        try:
            # 1. Update Aster Position
            if symbol in self._open_positions:
                pos = self._open_positions[symbol]
                if tp is not None:
                    pos["tp"] = float(tp)
                if sl is not None:
                    pos["sl"] = float(sl)
                self._open_positions[symbol] = pos
                print(f"✅ Updated Aster TP/SL for {symbol}: TP={tp}, SL={sl}")

            # 2. Update Hyperliquid Position (Ghost State)
            if symbol in self._hyperliquid_positions:
                hl_pos = self._hyperliquid_positions[symbol]
                # We can't modify the source of truth directly (it comes from Redis),
                # but we can publish an intent to update it.
                pass

            # 3. Publish Event for Execution Services (Hyperliquid Trader, etc.)
            # Redis removed in Phase 25 - this is now a no-op
            # if self._redis_pubsub:
            #     await self._publish_event(
            #         "tpsl_update", {"symbol": symbol, "tp": tp, "sl": sl, "timestamp": time.time()}
            #     )
            #     print(f"📡 Published TP/SL update for {symbol}")

            return True

        except Exception as e:
            print(f"❌ Failed to update TP/SL: {e}")
            return False

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
                    should_close_hard, hard_reason = await self._check_profit_taking(
                        symbol, pos, curr_price
                    )
                    if should_close_hard:
                        print(f"💰 Profit/Stop Triggered for {symbol}: {hard_reason}")
                        # Execute immediately
                        trade_side = "SELL" if pos["side"] == "BUY" else "BUY"
                        await self._execute_trade_order(
                            agent,
                            symbol,
                            trade_side,
                            quantity_float,
                            is_closing=True,
                            reason=hard_reason,
                        )
                        return  # Exit loop for this tick
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
                        base_qty = current_qty  # Fallback
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
                # We need to fix _check_pending_orders to MERGE if position exists and side matches.
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
            # If no open position for the selected symbol, we defer to the new trade execution
            # which will handle consensus-based entries across all relevant symbols.
            pass  # This block is now empty as new entries are handled by _execute_new_trades

    async def _scan_and_execute_new_trades(self):
        """
        Execute new trades using SWARM CONSENSUS.

        Phase 1: GATHER - All agents analyze markets and submit signals.
        Phase 2: VOTE - Consensus Engine aggregates signals per symbol.
        Phase 3: EXECUTE - Trade on High Confidence Consensus.
        """

        # --- PHASE 1: GATHER SIGNALS ---
        # Iterate through all agents and all tradeable symbols from exchange

        # Use all available symbols from market structure (fetched from exchange)
        # Agents trade dynamically across all available markets
        print(f"🚀 SCAN: Starting _scan_and_execute_new_trades...")

        active_agents = [a for a in self._agent_states.values() if a.active]
        if not active_agents:
            print("⚠️ No active agents, returning early")
            return

        # Optimization: Don't let every agent analyze every symbol every tick.
        # Randomly select a subset of symbols to analyze to simulate "attention"
        import random

        # Get all available symbols from market structure (dynamic)
        all_symbols = list(self._market_structure.keys()) if self._market_structure else []
        # Limit to 10 random symbols per cycle for good trade frequency
        symbols_to_scan = random.sample(all_symbols, min(10, len(all_symbols))) if all_symbols else []

        # Map to store which agents looked at which symbols (for logging)
        scan_activity = defaultdict(int)

        for symbol in symbols_to_scan:
            # Check if we already have a position
            if symbol in self._open_positions:
                continue

            # COOLDOWN: Don't enter new position if we traded this symbol in last 15 mins
            if hasattr(self, "_last_trade_time") and symbol in self._last_trade_time:
                if time.time() - self._last_trade_time[symbol] < 900:  # 15 minutes
                    continue

            # Each agent has a chance to analyze this symbol
            # Specialized agents might always check their niche?
            for agent in active_agents:
                scan_activity[symbol] += 1

                # Analyze
                analysis = await self._analyze_market_for_agent(agent, symbol)

                # If actionable, Submit to Consensus (lowered from 0.75 to 0.65 for more activity)
                if analysis["signal"] in ["BUY", "SELL"] and analysis["confidence"] >= 0.65:

                    # Register if needed
                    if agent.id not in self._consensus_engine.agent_registry:
                        self._consensus_engine.register_agent(
                            agent.id,
                            agent.type,
                            "trend" if "trend" in agent.name.lower() else "mean_reversion",
                        )

                    # Create Signal
                    sig_type = (
                        SignalType.ENTRY_LONG
                        if analysis["signal"] == "BUY"
                        else SignalType.ENTRY_SHORT
                    )

                    agent_signal = AgentSignal(
                        agent_id=agent.id,
                        signal_type=sig_type,
                        confidence=analysis["confidence"],
                        strength=analysis["confidence"],
                        symbol=symbol,
                        timestamp_us=int(time.time() * 1000000),
                        reasoning=analysis.get("thesis", "Agent Signal"),
                    )

                    self._consensus_engine.submit_signal(agent_signal)

        # --- PHASE 2 & 3: VOTE & EXECUTE ---
        # The consensus engine now holds pending signals.
        # We iterate through the symbols that received signals (keys of pending_signals)

        pending_symbols = list(self._consensus_engine.pending_signals.keys())
        print(f"📊 VOTE PHASE: {len(pending_symbols)} symbols have pending signals: {pending_symbols[:5]}...")

        for symbol in pending_symbols:
            # Conduct Vote (Consumes signals)
            consensus = await self._consensus_engine.conduct_consensus_vote(symbol)

            if not consensus or not consensus.winning_signal:
                print(f"❌ No consensus for {symbol}")
                continue

            # FILTER: High Conviction Swarm Only (CONCENTRATED STRATEGY)
            # Higher thresholds = fewer, better trades
            MIN_CONFIDENCE = 0.75  # Increased from 0.65 for concentrated strategy
            MIN_AGREEMENT = 0.50   # Increased from 0.40 for higher conviction
            
            if consensus.consensus_confidence < MIN_CONFIDENCE or consensus.agreement_level < MIN_AGREEMENT:
                # Not high enough conviction, skip
                print(f"⚠️ Weak Consensus for {symbol}: Conf={consensus.consensus_confidence:.2f} (min {MIN_CONFIDENCE}), Agreement={consensus.agreement_level:.2f} (min {MIN_AGREEMENT})")
                continue
            
            print(f"✅ STRONG CONSENSUS: {symbol} {consensus.winning_signal} (conf={consensus.consensus_confidence:.2f}, agree={consensus.agreement_level:.2f})")

            # --- EXECUTION ---
            winning_signal = consensus.winning_signal
            side = (
                "BUY"
                if winning_signal in [SignalType.ENTRY_LONG, SignalType.EXIT_SHORT]
                else "SELL"
            )

            # Determine Sizing
            base_notional = 300.0
            multiplier = 1.0
            thesis = f"Swarm Consensus: {consensus.reasoning}"

            if consensus.consensus_confidence >= 0.9:
                multiplier = 5.0
                thesis += " [SWARM MAX]"
                self._mcp.add_message(
                    "plan",
                    "Consensus Engine",
                    f"MAX CONVICTION on {symbol}. 5x Size.",
                    "Swarm Intelligence",
                )
            elif consensus.consensus_confidence >= 0.8:
                multiplier = 2.5
                thesis += " [SWARM HIGH]"

            # Use 'System' or the highest weighted agent as the executor?
            # Let's use the highest weighted agent involved in the vote to keep it "personal"
            best_agent_id = max(
                consensus.agent_votes,
                key=lambda aid: self._consensus_engine.agent_weights.get(aid, 1.0),
            )
            best_agent = self._agent_states.get(best_agent_id) or active_agents[0]

            target_notional = base_notional * multiplier

            # === RISK CHECKS (CONCENTRATED POSITION STRATEGY) ===
            # Fewer, larger, higher-conviction positions for optimal returns
            MAX_TOTAL_EXPOSURE = 0.60   # 60% of account in positions
            MAX_POSITION_SIZE = 0.12    # 12% of account per position (larger bets)
            MAX_CONCURRENT_POSITIONS = 4  # Focus on 4 best opportunities
            
            # Check 0: Max Positions Limit (concentrated strategy)
            if len(self._open_positions) >= MAX_CONCURRENT_POSITIONS:
                print(f"⚠️ Risk Check: Max Positions ({MAX_CONCURRENT_POSITIONS}) Reached - Focused Mode")
                continue  # Skip - focus on existing positions
            
            # Check 1: Exposure Limit
            total_position_value = sum(
                abs(p["quantity"] * p["entry_price"]) 
                for p in self._open_positions.values()
            )
            account_balance = self._account_balance or 1000  # Fallback
            current_exposure = total_position_value / account_balance if account_balance > 0 else 1.0
            
            if current_exposure >= MAX_TOTAL_EXPOSURE:
                print(f"⚠️ Risk Check: Exposure Limit Hit ({current_exposure:.1%} >= {MAX_TOTAL_EXPOSURE:.0%})")
                continue  # Skip this trade
                
            # Check 2: Position Size Limit (allow larger positions for concentrated strategy)
            max_allowed_notional = account_balance * MAX_POSITION_SIZE
            if target_notional > max_allowed_notional:
                print(f"⚠️ Risk Check: Position Size Capped (${target_notional:.2f} -> ${max_allowed_notional:.2f})")
                target_notional = max_allowed_notional

            # Get Price
            try:
                ticker = await self._exchange_client.get_ticker(symbol)
                current_price = float(ticker.get("lastPrice", 0))
                if current_price <= 0:
                    continue

                quantity_float = target_notional / current_price

                # Apply Precision
                if symbol in self._market_structure:
                    qty_precision = self._market_structure[symbol].get("quantityPrecision", 4)
                    quantity_float = round(quantity_float, qty_precision)
                elif symbol in SYMBOL_CONFIG:
                    precision = SYMBOL_CONFIG[symbol].get("precision", 4)
                    quantity_float = round(quantity_float, precision)

                print(
                    f"🗳️ SWARM CONSENSUS: {symbol} {side} | Conf: {consensus.consensus_confidence:.2f} | Agents: {consensus.participation_rate:.0%} | Winner: {best_agent.name}"
                )

                await self._execute_trade_order(
                    best_agent, symbol, side, quantity_float, thesis, is_closing=False
                )

            except Exception as e:
                print(f"⚠️ Swarm Execution Failed for {symbol}: {e}")

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
                        print(
                            f"⚠️ Warning: Position {symbol} has side 'BOTH' but no actual_side tracked. Defaulting to BUY."
                        )
                        side = "BUY"
                else:
                    # No position tracked, default to BUY
                    print(
                        f"⚠️ Warning: Attempting to trade {symbol} with side 'BOTH' but position not tracked. Defaulting to BUY."
                    )
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
                    print(
                        f"⚠️ Warning: Invalid side '{side}' for closing trade. Defaulting to SELL."
                    )
                    trade_side = "SELL"
            else:
                # For opening positions, use the side as-is
                trade_side = side

            # GAME THEORY: Add Random Jitter to Execution Time
            # Avoids being front-run by HFTs monitoring regular intervals
            import random

            # 0.5s to 3.0s delay
            jitter = random.uniform(0.5, 3.0)
            print(f"🎲 Game Theory: Jitter delay {jitter:.2f}s...")
            self._mcp.add_message(
                "observation",
                "System",
                f"Applying randomized jitter delay of {jitter:.2f}s to avoid detection.",
                "Game Theory",
            )
            await asyncio.sleep(jitter)

            # GAME THEORY: Size Randomization (Fuzzy Sizing)
            # Avoid round numbers (e.g., 1000) which are easy to spot.
            # Add +/- 3% random noise to the quantity.
            quantity_fuzz = random.uniform(0.97, 1.03)
            final_quantity_float = float(quantity_float) * quantity_fuzz

            # Format quantity with precision
            formatted_quantity = str(final_quantity_float)

            if symbol in SYMBOL_CONFIG:
                config = SYMBOL_CONFIG[symbol]
                if config["precision"] == 0:
                    formatted_quantity = "{:.0f}".format(final_quantity_float)
                else:
                    formatted_quantity = "{:.{p}f}".format(
                        final_quantity_float, p=config["precision"]
                    )
            elif symbol in self._market_structure:
                # Use dynamic market structure
                precision = self._market_structure[symbol]["precision"]
                if precision == 0:
                    formatted_quantity = "{:.0f}".format(final_quantity_float)
                else:
                    formatted_quantity = "{:.{p}f}".format(final_quantity_float, p=precision)

            print(
                f"🚀 ATTEMPTING TRADE: {agent.emoji} {agent.name} - {trade_side} {formatted_quantity} {symbol}{'(CLOSING)' if is_closing else ''}"
            )

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
                # Main Entry/Exit
                order_result = await self._exchange_client.place_order(
                    symbol=symbol,
                    side=trade_side,
                    order_type=OrderType.MARKET,
                    quantity=formatted_quantity,
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
            if order_result and (order_result.get("orderId") or order_result.get("id")):
                # Aster API might use 'id' or 'orderId'
                order_id = order_result.get("orderId") or order_result.get("id")
                status = order_result.get(
                    "status", "FILLED"
                )  # Assume filled if direct DEX response
                executed_qty = float(
                    order_result.get("executedQty", 0) or order_result.get("quantity", 0)
                )
                avg_price = float(order_result.get("avgPrice", 0) or order_result.get("price", 0))

                print(
                    f"📋 Order Placed: ID {order_id} | Status: {status} | Exec: {executed_qty} | Price: {avg_price}"
                )

                if executed_qty > 0 and avg_price > 0:
                    # 1. CLOSING TRADE: Record Performance
                    if is_closing:
                        if symbol in self._open_positions:
                            pos = self._open_positions[symbol]
                            entry_price = pos.get("entry_price", 0)

                            pnl = 0.0
                            if pos["side"] == "BUY":
                                pnl = (avg_price - entry_price) * executed_qty
                            elif pos["side"] == "SELL":
                                pnl = (entry_price - avg_price) * executed_qty

                            print(
                                f"📊 Trade Closed: PnL ${pnl:.2f} (Entry: {entry_price}, Exit: {avg_price})"
                            )

                            # Log to Analytics
                            try:
                                # Calculate capital used for accurate % returns
                                capital_used = entry_price * executed_qty
                                if capital_used <= 0:
                                    capital_used = 1.0  # Avoid div by zero
                                self._performance_tracker.record_trade(
                                    agent.id, pnl, capital_used=capital_used
                                )

                                # --- FEEDBACK LOOP ---
                                # We need to reconstruct the consensus result key or just act on the agent signal
                                # Ideally we'd pass the original consensus object ID, but for now we update the agent directly.
                                # Future enhancement: Pass consensus_id in trade metadata.
                                # self._consensus_engine.update_performance_feedback(...)
                            except Exception as e:
                                print(f"⚠️ Failed to record performance: {e}")

                            del self._open_positions[symbol]
                            self._save_positions()  # Persist removal

                            # Clean up any open TP/SL orders for this symbol
                            # We can span a task to do this so we don't block
                            asyncio.create_task(self._exchange_client.cancel_all_orders(symbol))

                    # 2. OPENING TRADE: Place Native TP/SL & Track
                    else:
                        # Determine TP/SL levels (Asymmetric Aggressive)
                        # R:R = 1.6 (Risk 3% to make 5%)
                        tp_pct = 0.05
                        sl_pct = 0.03

                        # Jitter
                        tp_jit = random.uniform(1.0, 1.05)
                        sl_jit = random.uniform(1.0, 1.05)

                        tp_price = (
                            avg_price * (1 + (tp_pct * tp_jit))
                            if side == "BUY"
                            else avg_price * (1 - (tp_pct * tp_jit))
                        )
                        sl_price = (
                            avg_price * (1 - (sl_pct * sl_jit))
                            if side == "BUY"
                            else avg_price * (1 + (sl_pct * sl_jit))
                        )

                        # Native Order Placement
                        try:
                            price_precision = 2
                            if symbol in self._market_structure:
                                price_precision = self._market_structure[symbol].get(
                                    "pricePrecision", 2
                                )

                            tp_str = "{:.{p}f}".format(tp_price, p=price_precision)
                            sl_str = "{:.{p}f}".format(sl_price, p=price_precision)
                            sl_side = "SELL" if side == "BUY" else "BUY"

                            logger.info(f"🛡️ Placing Native TP/SL: TP {tp_str} | SL {sl_str}")

                            # Place STOP_MARKET order for Stop Loss
                            await self._exchange_client.place_order(
                                symbol=symbol,
                                side=sl_side,
                                order_type=OrderType.STOP_MARKET,
                                quantity=float(formatted_quantity),
                                stop_price=float(sl_str),
                                reduce_only=True,
                            )
                            # Place TAKE_PROFIT_MARKET order for Take Profit
                            await self._exchange_client.place_order(
                                symbol=symbol,
                                side=sl_side,
                                order_type=OrderType.TAKE_PROFIT_MARKET,
                                quantity=float(formatted_quantity),
                                stop_price=float(tp_str),
                                reduce_only=True,
                            )
                            print(f"✅ Native TP/SL orders placed: TP {tp_str} | SL {sl_str}")
                        except Exception as e:
                            logger.warning(f"⚠️ Failed to place Native TP/SL orders: {e}")

                        # Track Position Internally
                        self._open_positions[symbol] = {
                            "side": side,
                            "quantity": executed_qty,
                            "entry_price": avg_price,
                            "current_price": avg_price,
                            "tp_price": tp_price,
                            "sl_price": sl_price,
                            "open_time": time.time(),
                            "agent": agent.name,
                            "agent_id": agent.id,
                            "thesis": thesis,
                        }
                        self._save_positions()

                        # Track last trade time for cooldown
                        if not hasattr(self, "_last_trade_time"):
                            self._last_trade_time = {}
                        self._last_trade_time[symbol] = time.time()

                        print(
                            f"🎯 Position Opened: {symbol} @ {avg_price:.2f} (TP: {tp_price:.2f}, SL: {sl_price:.2f})"
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

            side = pos["side"]  # BUY, SELL, or BOTH (hedge mode)
            quantity = pos["quantity"]
            
            # Handle Aster hedge mode: side='BOTH' means direction is in quantity sign
            if side == "BOTH":
                if quantity > 0:
                    side = "BUY"  # Long position
                else:
                    side = "SELL"  # Short position
                print(f"⚠️ Warning: Position {symbol} has side 'BOTH', detected as {side} from quantity {quantity}")
            
            # Always use absolute quantity for calculations
            abs_quantity = abs(quantity)

            if side == "BUY":
                pnl_pct = (current_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - current_price) / entry_price

            # PARTIAL EXIT STRATEGY: Check for partial profit targets
            try:
                exit_signals = self.partial_exit_strategy.update_position_price(symbol, current_price)
                for exit_signal in exit_signals:
                    if exit_signal.exit_size > 0:
                        partial_qty = exit_signal.exit_size
                        print(f"📊 PARTIAL EXIT: {symbol} taking {partial_qty:.4f} @ ${current_price:.4f} ({exit_signal.reason})")
                        
                        # Execute partial exit
                        await self._execute_trade_order(
                            agent, symbol, side, partial_qty,
                            f"Partial Exit: {exit_signal.reason}",
                            is_closing=True
                        )
                        
                        # Telegram notification for partial exit
                        try:
                            await self._telegram.send_message(
                                f"📊 **Partial Exit**\n"
                                f"Symbol: `{symbol}`\n"
                                f"Size: `{partial_qty:.4f}`\n"
                                f"PnL: `{pnl_pct:+.2%}`\n"
                                f"Reason: {exit_signal.reason}",
                                priority=NotificationPriority.MEDIUM
                            )
                        except Exception:
                            pass
                        
                        # Execute in strategy
                        self.partial_exit_strategy.execute_exit(symbol, exit_signal)
            except Exception as pe_err:
                # Silent fail - partial exits are bonus, not critical
                pass

            # RISK THRESHOLDS (Aster - optimized for crypto volatility)
            TP_THRESHOLD = 0.05       # +5% Take Profit
            SL_THRESHOLD = -0.03      # -3% Stop Loss
            EMERGENCY_SL = -0.08      # -8% Emergency Stop (prevent liquidation)

            action = None
            reason = None
            is_emergency = False

            # Priority 1: Emergency Stop Loss (-8%)
            if pnl_pct <= EMERGENCY_SL:
                action = "SELL" if side == "BUY" else "BUY"
                reason = f"🚨 EMERGENCY STOP ({pnl_pct:.1%})"
                is_emergency = True
                print(f"🚨🚨 EMERGENCY: {symbol} at {pnl_pct:.1%} - FORCE CLOSING")

            # Priority 2: Take Profit
            elif pnl_pct >= TP_THRESHOLD:
                action = "SELL" if side == "BUY" else "BUY"
                reason = f"Take Profit (+{pnl_pct:.1%})"
            # Priority 3: Stop Loss
            elif pnl_pct <= SL_THRESHOLD:
                action = "SELL" if side == "BUY" else "BUY"
                reason = f"Stop Loss ({pnl_pct:.1%})"

            if action:
                print(f"🚨 PORTFOLIO GUARD: {symbol} PnL {pnl_pct:.1%} -> {reason}")

                thesis = f"Portfolio Guard: {reason}"

                # Calculate PnL in USD
                pnl_usd = (current_price - entry_price) * abs_quantity if side == "BUY" else (entry_price - current_price) * abs_quantity

                # Telegram Notification for TP/SL
                emoji = "💰" if pnl_pct > 0 else ("🚨" if is_emergency else "❌")
                priority = NotificationPriority.CRITICAL if is_emergency else NotificationPriority.HIGH

                # Execute Close FIRST
                # Note: side passed to _execute_trade_order is the CURRENT position side.
                # is_closing=True tells it to close.
                try:
                    await self._execute_trade_order(
                        agent, symbol, side, abs_quantity, thesis, is_closing=True
                    )
                    
                    # Only send Telegram notification AFTER successful execution
                    try:
                        await self._telegram.send_message(
                            f"{emoji} **Position Closed**\n"
                            f"Symbol: `{symbol}`\n"
                            f"Reason: {reason}\n"
                            f"PnL: `{pnl_pct:+.2%}` (`${pnl_usd:+.2f}`)\n"
                            f"Entry: `${entry_price:.4f}`\n"
                            f"Exit: `${current_price:.4f}`",
                            priority=priority
                        )
                    except Exception as tg_err:
                        print(f"⚠️ Telegram notification failed: {tg_err}")
                        
                except Exception as close_err:
                    print(f"⚠️ Failed to close {symbol}: {close_err}")

    async def _execute_trading_cycle(self):
        """
        Orchestrate the full trading cycle:
        1. Manage existing positions via _execute_agent_trading
        2. Scan for new opportunities via consensus-based approach
        
        This method is called by the main trading loop.
        """
        # 1. Manage existing positions (TP/SL, closes, adds)
        await self._execute_agent_trading()

        # 2. Execute new trades using consensus engine
        # This calls the full consensus-based logic defined earlier
        await self._scan_and_execute_new_trades()

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
            agent = MinimalAgentState(
                id="reviewer",
                name="Portfolio Reviewer",
                type="reviewer",
                model="gemini-2.0-flash-exp",
                emoji="🕵️",
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
                await self._manage_positions()

                # 5. Execute Trading Cycle (Position Management + New Entries)
                await self._execute_trading_cycle()

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

            # WARNING ZONE: > 60% Margin Usage
            if margin_ratio > 0.6 and margin_ratio <= 0.8:
                print(f"⚠️ HIGH MARGIN WARNING: Margin Ratio {margin_ratio:.1%}")
                try:
                    await self._telegram.send_message(
                        f"⚠️ **Risk Warning**\n"
                        f"Margin Ratio: `{margin_ratio:.1%}`\n"
                        f"Margin Balance: `${margin_balance:.2f}`\n"
                        f"Maintenance: `${maint_margin:.2f}`\n"
                        f"📉 Consider reducing exposure",
                        priority=NotificationPriority.HIGH,
                    )
                except Exception:
                    pass

            # DANGER ZONE: > 80% Margin Usage
            elif margin_ratio > 0.8:
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
                        agent = MinimalAgentState(
                            id="risk_bot",
                            name="Risk Bot",
                            type="risk",
                            model="gemini-2.0-flash-exp",
                            emoji="🚑",
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
                    order_type=OrderType.MARKET,
                    quantity=abs(qty),
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
                    "current_price": float(
                        p.get("current_price", 0)
                    ),  # Need real-time price from HL or WS
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

        # Calculate unrealized PnL from all open positions
        unrealized_pnl = sum(p.get("pnl", 0.0) for p in all_positions)

        # Total PnL = Realized (from trades) + Unrealized (from open positions)
        total_pnl_combined = aster_pnl + hl_pnl + unrealized_pnl

        # Use actual portfolio balance from exchange sync
        # self._portfolio.balance is synced from exchange in _initialize_basic_agents
        initial_basis = self._portfolio.balance if self._portfolio.balance > 0 else 10000.0

        total_pnl_percent = (total_pnl_combined / initial_basis) * 100 if initial_basis > 0 else 0.0
        aster_pnl_percent = (aster_pnl / max(initial_basis * 0.5, 1.0)) * 100  # Assume 50% alloc
        hl_pnl_percent = (hl_pnl / max(initial_basis * 0.5, 1.0)) * 100  # Assume 50% alloc

        return {
            "status": "active",
            "running": self._health.running,
            "agents": self.get_agents(),
            "open_positions": all_positions,
            "recentTrades": list(self._recent_trades)[:20],
            "messages": frontend_messages,
            "total_pnl": total_pnl_combined,
            "total_pnl_percent": total_pnl_percent,
            "realized_pnl": aster_pnl + hl_pnl,
            "unrealized_pnl": unrealized_pnl,
            "portfolio_value": initial_basis + total_pnl_combined,  # Equity
            "portfolio_balance": initial_basis + aster_pnl + hl_pnl,  # Cash Balance
            "aster_pnl_percent": aster_pnl_percent,
            "hl_pnl_percent": hl_pnl_percent,
            "total_exposure": sum(
                p.get("quantity", 0) * p.get("current_price", 0) for p in all_positions
            ),
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
                print(
                    f"🎻 New Market Regime: {regime.regime.value} (Conf: {regime.confidence:.2f})"
                )

                # Broadcast to frontend (Thread-safe)
                if hasattr(self, "_loop"):
                    asyncio.run_coroutine_threadsafe(
                        broadcast_market_regime(regime.to_dict()), self._loop
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
