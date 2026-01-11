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

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorConfig:
    """Configuration for the trading orchestrator."""

    enable_aster: bool = True
    enable_drift: bool = True
    enable_symphony: bool = True
    enable_hyperliquid: bool = False  # Deprecated
    max_concurrent_trades: int = 5
    loop_interval_seconds: float = 60.0
    paper_trading: bool = False


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
            paper_trading=getattr(self.settings, "paper_trading", False),
        )

        # Core components (injected)
        self.trading_loop = None
        self.agent_orchestrator = None
        self.position_tracker = None
        self.platform_router = None

        # Platform Clients
        self._exchange_client = None  # Aster
        self.drift = None
        self.symphony = None
        self.hl_client = None  # Hyperliquid (stub)

        # State
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._start_time: Optional[float] = None

        logger.info("🚀 TradingOrchestrator initialized")

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

        # Start main loop
        self._task = asyncio.create_task(self._run())

        logger.info("✅ Sapphire V2 Trading System ONLINE")

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

        logger.info("✅ Sapphire V2 stopped gracefully")

    async def _initialize_components(self):
        """Initialize all trading components."""
        # 0. API Credentials & Platform Clients
        from ..credentials import load_credentials
        from ..drift_client import DriftClient
        from ..exchange import AsterClient
        from ..hyperliquid_client import HyperliquidClient
        from ..symphony_client import SymphonyClient

        creds = load_credentials()

        # Inject secrets into settings for global reuse
        if creds.telegram_bot_token:
            self.settings.telegram_bot_token = creds.telegram_bot_token
        if creds.telegram_chat_id:
            self.settings.telegram_chat_id = creds.telegram_chat_id
        if creds.solana_private_key:
            self.settings.solana_private_key = creds.solana_private_key
        # Note: Symphony API key is handled by symphony_config.py usually,
        # but we'll store it here for consistency if needed.

        # Initialize Aster
        self._exchange_client = AsterClient(credentials=creds, base_url=self.settings.rest_base_url)
        logger.info("🔌 Aster Client Initialized")

        # Initialize Drift
        if self.config.enable_drift:
            self.drift = DriftClient(rpc_url=self.settings.solana_rpc_url)
            await self.drift.initialize()
            logger.info("🔌 Drift Client Initialized")

        # Initialize Symphony
        if self.config.enable_symphony:
            self.symphony = SymphonyClient()
            logger.info("🔌 Symphony Client Initialized")

        # Initialize Hyperliquid (Stub)
        self.hl_client = HyperliquidClient()

        # 1. Monitoring Service (First modular service)
        from ..agents.agent_orchestrator import AgentOrchestrator
        from ..execution.position_tracker import PositionTracker
        from .monitoring import MonitoringService
        from .trading_loop import TradingLoop

        self.monitoring = MonitoringService(self.settings)
        await self.monitoring.start()

        # 2. Platform Router
        self.platform_router = PlatformRouter(self)

        # 3. Position Tracker
        self.position_tracker = PositionTracker(self.platform_router)

        # 4. Agent Orchestrator (manages all AI agents)
        self.agent_orchestrator = AgentOrchestrator(monitoring=self.monitoring)

        # 5. Trading Loop
        self.trading_loop = TradingLoop(
            orchestrator=self,
            agents=self.agent_orchestrator,
            positions=self.position_tracker,
            router=self.platform_router,
            monitoring=self.monitoring,
        )

        logger.info("✅ All components initialized")

    async def _cleanup_components(self):
        """Cleanup all components."""
        if self.trading_loop:
            await self.trading_loop.stop()
        if self.agent_orchestrator:
            await self.agent_orchestrator.stop()

    async def _run(self):
        """Main orchestration loop."""
        while self._running:
            try:
                # Delegate to trading loop
                await self.trading_loop.run_cycle()

                # Wait for next cycle
                await asyncio.sleep(self.config.loop_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Orchestrator error: {e}")
                await asyncio.sleep(5)  # Brief pause before retry

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
                "paper_trading": self.config.paper_trading,
            },
            "components": {
                "trading_loop": self.trading_loop is not None,
                "agent_orchestrator": self.agent_orchestrator is not None,
                "position_tracker": self.position_tracker is not None,
                "platform_router": self.platform_router is not None,
            },
        }
