"""
Sapphire V2 Trading Orchestrator
Central coordinator for all trading operations.
Replaces the monolithic TradingService with clean separation of concerns.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..config import Settings
from ..platform_router import ExecutionResult, PlatformRouter
from .event_handler import EventHandler, MarketEventTypes, create_market_event
from .state_manager import StateManager

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorConfig:
    """Configuration for the trading orchestrator."""

    enable_aster: bool = True
    enable_drift: bool = True
    enable_symphony: bool = True
    enable_hyperliquid: bool = True
    enable_lighter: bool = True
    enable_jupiter: bool = True

    max_concurrent_trades: int = 5
    loop_interval_seconds: float = 60.0
    paper_trading: bool = False
    event_driven: bool = False  # CRITICAL: Must be False to run trading_loop.run_cycle()
    market_event_subscription: str = "sapphire-market-events-sub"
    signal_topic: str = "sapphire-signals"


class TradingOrchestrator:
    """
    Central coordinator for the Sapphire trading system.

    Responsibilities:
    - Lifecycle management (start/stop)
    - Component injection and coordination
    - Event bus management
    - Health monitoring

    Does NOT contain:
    - Trading logic (delegated to TradingLoop)
    - Position management (delegated to PositionTracker)
    - AI analysis (delegated to AgentOrchestrator)
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()
        self.config = OrchestratorConfig(
            enable_aster=self.settings.enable_aster,
            enable_drift=self.settings.enable_drift,
            enable_symphony=self.settings.enable_symphony,
            enable_hyperliquid=self.settings.enable_hyperliquid,
            enable_lighter=self.settings.enable_lighter,
            enable_jupiter=getattr(self.settings, "enable_jupiter", True),
            paper_trading=getattr(self.settings, "paper_trading", False),
        )

        # Core components (injected)
        self.trading_loop = None
        self.agent_orchestrator = None
        self.position_tracker = None
        self.platform_router = None
        self.telegram_listener = None

        # Platform Clients
        self._exchange_client = None  # Aster
        self.drift = None
        self.symphony = None
        self.hl_client = None  # Hyperliquid
        self.lighter_client = None  # Lighter
        self.jupiter_client = None  # Jupiter

        # Trade Verification
        self.trade_verification = None

        # State
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._start_time: Optional[float] = None

        # Event-Driven Components
        self.state_manager = StateManager(namespace="sapphire")
        self.event_handler = EventHandler()

        logger.info("🚀 TradingOrchestrator initialized")

    def _build_watchlist(self) -> List[str]:
        """Build trading watchlist from settings symbols."""
        # Get symbols from environment variable or platform-specific defaults
        raw_symbols = self.settings.symbols

        # Normalize symbols to match platform format (add -USDC suffix if needed)
        watchlist = []
        for symbol in raw_symbols:
            # If symbol doesn't have a quote currency, add -USDC
            if "-" not in symbol and "USDT" not in symbol and "USDC" not in symbol:
                watchlist.append(f"{symbol}-USDC")
            else:
                watchlist.append(symbol)

        logger.info(f"📋 Watchlist built from settings: {watchlist}")
        return watchlist

    def _normalize_for_aster(self, symbol: str) -> str:
        """Utility for platform router."""
        if not self._exchange_client:
            return symbol
        return self._exchange_client._normalize_symbol(symbol)

    async def start(self):
        """Start the trading system."""
        if self._running:
            logger.warning("Orchestrator already running")
            return

        logger.info("🔥 Starting Sapphire V2 Trading System...")
        self._running = True
        self._start_time = asyncio.get_event_loop().time()

        # Initialize components
        await self._initialize_components()

        # Start main loop or event listener
        if self.config.event_driven:
            await self._setup_event_handlers()
            self._task = asyncio.create_task(self._run_event_driven())
            logger.info("✅ Sapphire V2 Trading System ONLINE (Event-Driven Mode)")
        else:
            self._task = asyncio.create_task(self._run())
            logger.info("✅ Sapphire V2 Trading System ONLINE (Polling Mode)")

    async def stop(self):
        """Gracefully stop the trading system."""
        if not self._running:
            return

        logger.info("🛑 Stopping Sapphire V2...")
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        # Cleanup components
        await self._cleanup_components()

        # Stop event handler
        await self.event_handler.stop_listening()

        # Stop Telegram listener
        if self.telegram_listener:
            await self.telegram_listener.stop()

        logger.info("✅ Sapphire V2 stopped gracefully")

    async def _initialize_components(self):
        """Initialize all trading components."""
        # 0. API Credentials & Platform Clients
        from ..credentials import load_credentials
        from ..drift_client import DriftClient
        from ..exchange import AsterClient
        from ..symphony_client import SymphonyClient

        creds = load_credentials()

        # Inject ALL secrets into settings for global reuse
        if creds.telegram_bot_token:
            self.settings.telegram_bot_token = creds.telegram_bot_token
        if creds.telegram_chat_id:
            self.settings.telegram_chat_id = creds.telegram_chat_id
        if creds.solana_private_key:
            self.settings.solana_private_key = creds.solana_private_key
        # Use Vertex AI API key (Gemini API) - prioritize vertex_api_key, fallback to gemini_api_key
        if creds.vertex_api_key:
            self.settings.gemini_api_key = creds.vertex_api_key
            logger.info("🤖 Using Vertex AI API key for Gemini models")
        elif creds.gemini_api_key:
            self.settings.gemini_api_key = creds.gemini_api_key
            logger.info("🤖 Using Gemini API key")
        if creds.symphony_api_key:
            self.settings.symphony_api_key = creds.symphony_api_key

        logger.info("🔑 All API credentials loaded from GCP Secret Manager")

        # Initialize Aster (only if enabled)
        if self.config.enable_aster:
            self._exchange_client = AsterClient(credentials=creds, base_url=self.settings.rest_base_url)
            logger.info("🔌 Aster Client Initialized")
        else:
            logger.info("ℹ️ Aster disabled, skipping initialization")

        # Initialize Drift
        if self.config.enable_drift:
            self.drift = DriftClient(rpc_url=self.settings.solana_rpc_url)
            await self.drift.initialize()
            logger.info("🔌 Drift Client Initialized")
        else:
            logger.info("ℹ️ Drift disabled, skipping initialization")

        # Initialize Symphony
        if self.config.enable_symphony:
            self.symphony = SymphonyClient()
            logger.info("🔌 Symphony Client Initialized")
            # Ensure agents are registered on Symphony
            try:
                await self.symphony.ensure_agents_registered()
            except Exception as e:
                logger.warning(f"⚠️ Symphony agent registration check failed: {e}")
        else:
            logger.info("ℹ️ Symphony disabled, skipping initialization")

        # Initialize Hyperliquid (only if enabled AND credentials exist)
        if self.config.enable_hyperliquid and creds.hl_private_key and creds.hl_account_address:
            try:
                from ..v2.hyperliquid_client import HyperliquidClient
                self.hl_client = HyperliquidClient(
                    private_key=creds.hl_private_key,
                    wallet_address=creds.hl_account_address,
                )
                await self.hl_client.initialize()
                logger.info("🔌 Hyperliquid Client Initialized")
            except Exception as e:
                logger.warning(f"⚠️ Hyperliquid initialization failed: {e}")
                self.hl_client = None
        else:
            if not self.config.enable_hyperliquid:
                logger.info("ℹ️ Hyperliquid disabled, skipping initialization")
            else:
                logger.info("ℹ️ Hyperliquid credentials not found, skipping initialization")

        # Initialize Lighter (only if enabled AND credentials exist)
        if self.config.enable_lighter and creds.lighter_pub_key and creds.lighter_priv_key:
            try:
                from ..v2.lighter_client import LighterClient
                self.lighter_client = LighterClient(
                    pub_key=creds.lighter_pub_key,
                    priv_key=creds.lighter_priv_key,
                )
                await self.lighter_client.initialize()
                logger.info("🔌 Lighter Client Initialized")
            except Exception as e:
                logger.warning(f"⚠️ Lighter initialization failed: {e}")
                self.lighter_client = None
        else:
            if not self.config.enable_lighter:
                logger.info("ℹ️ Lighter disabled, skipping initialization")
            else:
                logger.info("ℹ️ Lighter credentials not found, skipping initialization")

        # Initialize Jupiter (only if enabled AND credentials exist)
        if self.config.enable_jupiter and creds.jupiter_api_key and creds.solana_private_key:
            try:
                from ..jupiter_trader_unified import JupiterTraderUnified
                self.jupiter_client = JupiterTraderUnified(
                    api_key=creds.jupiter_api_key,
                    private_key_b58=creds.solana_private_key,
                    telegram_bot_token=creds.telegram_bot_token,
                    telegram_chat_id=creds.telegram_chat_id,
                    capital_usd=self.settings.total_capital_usd if hasattr(self.settings, 'total_capital_usd') else 50.0,
                    enable_hft_strategy=False,  # Enable later when ready
                )
                await self.jupiter_client.start()
                logger.info("🔌 Jupiter Client Initialized")
            except Exception as e:
                logger.warning(f"⚠️ Jupiter initialization failed: {e}")
                self.jupiter_client = None
        else:
            if not self.config.enable_jupiter:
                logger.info("ℹ️ Jupiter disabled, skipping initialization")
            else:
                logger.info("ℹ️ Jupiter credentials not found, skipping initialization")

        # Initialize Trade Verification Service (for blockchain trades)
        try:
            from ..trade_verification import TradeVerificationService
            self.trade_verification = TradeVerificationService(
                solana_rpc_url=self.settings.solana_rpc_url,
                verification_timeout=30,
            )
            logger.info("🔌 Trade Verification Service Initialized")
        except Exception as e:
            logger.warning(f"⚠️ Trade Verification initialization failed: {e}")
            self.trade_verification = None

        # 1. Monitoring Service (First modular service)
        from ..agents.agent_orchestrator import AgentOrchestrator
        from ..execution.position_tracker import PositionTracker
        from .monitoring import MonitoringService
        from .trading_loop import TradingLoop

        self.monitoring = MonitoringService(self.settings)
        await self.monitoring.start()

        # 2. Telegram Listener (DISABLED - Using MonitoringService for notifications only)
        # Prevents HTTP 409 conflict with Telegram Bot API (can't have multiple polling instances)
        logger.info("ℹ️ Telegram Listener disabled - using MonitoringService for notifications only")

        # 2a. Platform Router
        self.platform_router = PlatformRouter(self)

        # 3. Position Tracker
        self.position_tracker = PositionTracker(self.platform_router)

        # Connect position tracker to monitoring for PnL updates
        self.monitoring.set_position_tracker(self.position_tracker)

        # 4. Agent Orchestrator (manages all AI agents)
        self.agent_orchestrator = AgentOrchestrator(monitoring=self.monitoring)

        # 5. Prepare watchlist from settings (respects TRADING_SYMBOLS env var)
        watchlist = self._build_watchlist()

        # 6. Trading Loop
        self.trading_loop = TradingLoop(
            orchestrator=self,
            agents=self.agent_orchestrator,
            positions=self.position_tracker,
            router=self.platform_router,
            monitoring=self.monitoring,
            watchlist=watchlist,
        )

        logger.info("✅ All components initialized")

        # Warm up precision cache for all platforms (prevents runtime errors)
        try:
            from ..precision_normalizer import get_precision_normalizer
            normalizer = get_precision_normalizer()

            # Get all symbols being traded
            symbols_to_warm = set(self.settings.symbols)  # Default symbols

            # Warm cache for all platforms
            logger.info(f"🔥 Warming precision cache for {len(symbols_to_warm)} symbols...")
            await normalizer.warm_cache(list(symbols_to_warm), "aster")
            if self.config.enable_hyperliquid and self.hl_client:
                await normalizer.warm_cache(list(symbols_to_warm), "hyperliquid")
            logger.info("✅ Precision cache warmed")
        except Exception as e:
            logger.warning(f"⚠️ Precision cache warmup failed (non-critical): {e}")

        # Restore state from Redis
        saved_state = self.state_manager.load_orchestrator_state()
        if saved_state:
            logger.info(f"🔄 Restored state from Redis: {len(saved_state)} keys")
            # Rehydrate positions if available
            if self.position_tracker and "positions" in saved_state:
                for symbol, pos in saved_state.get("positions", {}).items():
                    self.position_tracker._positions[symbol] = pos

    async def _cleanup_components(self):
        """Cleanup all components."""
        if self.trading_loop:
            await self.trading_loop.stop()
        if self.agent_orchestrator:
            await self.agent_orchestrator.stop()

    async def _run(self):
        """Main orchestration loop."""
        logger.info(f"🔄 [ORCHESTRATOR] Starting main loop (interval={self.config.loop_interval_seconds}s)")
        cycle_count = 0
        while self._running:
            try:
                cycle_count += 1
                logger.info(f"🔄 [ORCHESTRATOR] Cycle {cycle_count} starting...")

                # Delegate to trading loop
                await self.trading_loop.run_cycle()

                logger.info(f"✅ [ORCHESTRATOR] Cycle {cycle_count} complete, sleeping {self.config.loop_interval_seconds}s")
                # Wait for next cycle
                await asyncio.sleep(self.config.loop_interval_seconds)

            except asyncio.CancelledError:
                logger.warning(f"⚠️ [ORCHESTRATOR] Loop cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Orchestrator error: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                await asyncio.sleep(5)  # Brief pause before retry

    async def _setup_event_handlers(self):
        """Register event handlers for Pub/Sub."""
        # Register market event handler
        self.event_handler.subscribe(
            self.config.market_event_subscription, self._handle_market_event
        )

        # Start listening
        await self.event_handler.start_listening()
        logger.info("📡 Event handlers registered")

    async def _run_event_driven(self):
        """Event-driven main loop (replaces polling)."""
        logger.info("🎯 Running in event-driven mode (no polling)")

        while self._running:
            try:
                # Periodic state persistence (every 30s)
                await asyncio.sleep(30)
                await self._persist_state()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Event-driven loop error: {e}")
                await asyncio.sleep(5)

    async def _handle_market_event(self, event: Dict[str, Any]):
        """
        Handle incoming market events from Pub/Sub.
        This replaces the polling loop with reactive execution.
        """
        event_type = event.get("type")
        symbol = event.get("symbol")
        data = event.get("data", {})

        logger.info(f"⚡ Received event: {event_type} for {symbol}")

        try:
            if event_type == MarketEventTypes.PRICE_UPDATE:
                # Price update -> Check for trading signals
                if self.trading_loop:
                    await self.trading_loop.handle_price_update(symbol, data)

            elif event_type == MarketEventTypes.SIGNAL_GENERATED:
                # AI signal -> Execute trade
                if self.trading_loop:
                    await self.trading_loop.execute_signal(symbol, data)

            elif event_type == MarketEventTypes.ORDER_FILL:
                # Order filled -> Update positions
                if self.position_tracker:
                    await self.position_tracker.handle_fill(data)

            elif event_type == MarketEventTypes.LIQUIDATION_RISK:
                # Risk alert -> Emergency action
                logger.warning(f"🚨 Liquidation risk for {symbol}!")
                # TODO: Implement emergency close

            # Persist state after handling event
            await self._persist_state()

        except Exception as e:
            logger.error(f"❌ Event handler error for {event_type}: {e}")

    async def _persist_state(self):
        """Persist current state to Redis."""
        try:
            state = {
                "running": self._running,
                "timestamp": asyncio.get_event_loop().time(),
            }

            # Include positions if available
            if self.position_tracker:
                state["positions"] = {
                    k: v.__dict__ if hasattr(v, "__dict__") else v
                    for k, v in self.position_tracker._positions.items()
                }

            self.state_manager.save_orchestrator_state(state)
            logger.debug("💾 State persisted to Redis")

        except Exception as e:
            logger.warning(f"⚠️ State persistence failed: {e}")

    async def publish_signal(self, symbol: str, signal: str, confidence: float):
        """Publish a trading signal to Pub/Sub."""
        event = create_market_event(
            MarketEventTypes.SIGNAL_GENERATED, symbol, {"signal": signal, "confidence": confidence}
        )
        await self.event_handler.publish(self.config.signal_topic, event)

    def get_status(self) -> Dict[str, Any]:
        """Get current system status."""
        uptime = 0
        if self._start_time:
            uptime = asyncio.get_event_loop().time() - self._start_time

        return {
            "running": self._running,
            "uptime_seconds": uptime,
            "config": {
                "enable_aster": self.config.enable_aster,
                "enable_drift": self.config.enable_drift,
                "enable_symphony": self.config.enable_symphony,
                "enable_hyperliquid": self.config.enable_hyperliquid,
                "enable_lighter": self.config.enable_lighter,
                "paper_trading": self.config.paper_trading,
            },
            "components": {
                "trading_loop": self.trading_loop is not None,
                "agent_orchestrator": self.agent_orchestrator is not None,
                "position_tracker": self.position_tracker is not None,
                "platform_router": self.platform_router is not None,
            },
        }
