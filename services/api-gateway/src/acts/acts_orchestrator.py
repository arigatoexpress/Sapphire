"""
Sapphire ACTS Orchestrator - Autonomous Cognitive Trading Swarm

This is the main entry point for the ACTS system, integrating:
- Cognitive Mesh (agent communication)
- Dual-Speed Cognition (Flash + Pro)
- Episodic Memory (regime learning)
- Executor Agents (platform execution)

Run this to start the full autonomous swarm.
"""

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ACTS")

from .cognitive_agent import CognitiveAgent, MarketContext, OracleAgent, ScoutAgent, SniperAgent

# Import ACTS components
from .cognitive_mesh import (
    CognitiveMesh,
    CognitiveMessage,
    ConsensusState,
    MessageType,
    get_cognitive_mesh,
    init_cognitive_mesh,
)
from .dual_speed_cognition import (
    CognitionRequest,
    CognitionSpeed,
    DualSpeedCognition,
    get_dual_cognition,
)
from .enhanced_episodic_memory import EnhancedMemoryBank, MarketSnapshot, get_enhanced_memory
from .executor_agent import (
    AsterExecutorAgent,
    DriftExecutorAgent,
    ExecutionRequest,
    HyperliquidExecutorAgent,
    create_executor_swarm,
)


class ACTSOrchestrator:
    """
    The Autonomous Cognitive Trading Swarm Orchestrator.

    Coordinates all components:
    - Scout agents observe markets
    - Sniper agents validate opportunities
    - Oracle decides based on consensus
    - Executors trade on platforms
    - Memory learns from outcomes
    """

    def __init__(self):
        self.running = False

        # Core components
        self.mesh: Optional[CognitiveMesh] = None
        self.cognition: Optional[DualSpeedCognition] = None
        self.memory: Optional[EnhancedMemoryBank] = None

        # Agent swarm
        self.scouts: List[ScoutAgent] = []
        self.snipers: List[SniperAgent] = []
        self.oracles: List[OracleAgent] = []
        self.executors: Dict[str, Any] = {}

        # Active consensus decisions
        self.pending_consensus: Dict[str, ConsensusState] = {}

        # Metrics
        self.decisions_made = 0
        self.trades_executed = 0
        self.overrides_triggered = 0

    async def initialize(self):
        """Initialize all ACTS components."""
        logger.info("🧬 Initializing ACTS Orchestrator...")

        # Initialize core systems
        self.mesh = await init_cognitive_mesh()
        self.cognition = get_dual_cognition()
        self.memory = get_enhanced_memory()

        # Create agent swarm
        logger.info("🐝 Spawning agent swarm...")

        # Scouts (market watchers)
        self.scouts = [ScoutAgent(f"scout-{i}") for i in range(2)]
        for scout in self.scouts:
            await scout.connect(self.mesh)

        # Snipers (execution timing)
        self.snipers = [SniperAgent(f"sniper-{i}") for i in range(2)]
        for sniper in self.snipers:
            await sniper.connect(self.mesh)

        # Oracles (consensus arbiters)
        self.oracles = [OracleAgent("oracle-1")]
        for oracle in self.oracles:
            await oracle.connect(self.mesh)

        # Executors (platform trading)
        self.executors = await create_executor_swarm()

        # Subscribe to mesh events
        self.mesh.subscribe("type:consensus", self._on_consensus_decision)
        self.mesh.subscribe("type:execution", self._on_execution_report)

        logger.info(
            f"""✅ ACTS Initialized:
  📡 Mesh: Active
  🧠 Cognition: Flash + Pro
  📚 Memory: {len(self.memory.episodes)} episodes
  🔭 Scouts: {len(self.scouts)}
  🎯 Snipers: {len(self.snipers)}
  🔮 Oracles: {len(self.oracles)}
  ⚡ Executors: {', '.join(self.executors.keys())}"""
        )

    async def start(self):
        """Start the ACTS main loop."""
        if not self.mesh:
            await self.initialize()

        self.running = True
        logger.info("🚀 ACTS Orchestrator Starting...")

        # Create initial snapshot (simulated)
        snapshot = MarketSnapshot(
            timestamp=datetime.utcnow(),
            prices={"SOL": 145.0, "BTC": 65000.0},
            volatility={"SOL": 0.05, "BTC": 0.02},
        )

        # Start market episode for tracking
        self.memory.start_episode(
            name=f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            snapshot=snapshot,
            symbols=["SOL", "BTC", "ETH"],
        )

        try:
            # Run main loops
            await asyncio.gather(
                self._market_scan_loop(),
                self._consensus_loop(),
                self._health_loop(),
            )
        except asyncio.CancelledError:
            logger.info("ACTS shutdown requested")
        finally:
            await self.stop()

    async def stop(self):
        """Gracefully stop ACTS."""
        logger.info("🛑 Stopping ACTS...")
        self.running = False

        # End current episode
        if self.memory.current_episode:
            # Create end snapshot (simulated)
            snapshot = MarketSnapshot(
                timestamp=datetime.utcnow(),
                prices={"SOL": 145.0, "BTC": 65000.0},
                volatility={"SOL": 0.05, "BTC": 0.02},
            )
            ep = self.memory.end_episode(snapshot)
            if ep:
                await self.memory.extract_multi_faceted_lessons(ep)

        logger.info("✅ ACTS stopped gracefully")

    async def _market_scan_loop(self):
        """Continuous market scanning by Scout agents."""
        scan_interval = 30  # seconds

        symbols = ["SOL", "BTC", "ETH"]  # Primary symbols to watch

        while self.running:
            try:
                for symbol in symbols:
                    # Get market context (would be from real data feed)
                    context = await self._get_market_context(symbol)

                    # Run full cognitive pipeline
                    opportunity = await self.process_opportunity(symbol, context)

                    if opportunity:
                        logger.info(f"✨ Opportunity processed: {opportunity}")

                    await asyncio.sleep(1)  # Stagger observations

            except Exception as e:
                logger.error(f"Scan loop error: {e}")

            await asyncio.sleep(scan_interval)

    async def _consensus_loop(self):
        """Process consensus decisions and trigger execution."""
        while self.running:
            try:
                # Check for mature consensus decisions
                for consensus_id, state in list(self.pending_consensus.items()):
                    if state.can_finalize() and not state.decision:
                        result = state.compute_consensus()

                        if result["status"] == "consensus_reached":
                            await self._execute_consensus(consensus_id, state, result)

            except Exception as e:
                logger.error(f"Consensus loop error: {e}")

            await asyncio.sleep(1)

    async def _health_loop(self):
        """Periodic health check and metrics reporting."""
        while self.running:
            await asyncio.sleep(60)

            logger.info(
                f"""📊 ACTS Health Report:
  Decisions: {self.decisions_made}
  Trades: {self.trades_executed}
  Overrides: {self.overrides_triggered}
  Memory: {self.memory.get_stats()}
  Cognition: {self.cognition.get_metrics()}"""
            )

    async def _get_market_context(self, symbol: str) -> MarketContext:
        """Get current market context for a symbol."""
        # In production, this would fetch real market data
        # For now, return simulated context
        import random

        return MarketContext(
            symbol=symbol,
            current_price=100 + random.uniform(-5, 5),
            price_change_1h=random.uniform(-3, 3),
            price_change_24h=random.uniform(-10, 10),
            volume_24h=random.uniform(100_000_000, 1_000_000_000),
            open_interest=random.uniform(500_000_000, 2_000_000_000),
            funding_rate=random.uniform(-0.01, 0.01),
            order_book_imbalance=random.uniform(-0.3, 0.3),
        )

    async def process_opportunity(
        self,
        symbol: str,
        context: MarketContext,
    ) -> Optional[Dict[str, Any]]:
        """
        Full cognitive pipeline for a trading opportunity.

        1. Scout observes
        2. Sniper validates
        3. Memory recalls
        4. Oracle decides (with dual-speed cognition)
        5. Executors trade
        6. Memory records
        """
        logger.info(f"🔍 Processing opportunity: {symbol}")

        # 1. Scout observation
        scout = self.scouts[0]
        scout_msg = await scout.analyze(context)

        if scout_msg.confidence < 0.5:
            logger.info(f"Scout low confidence ({scout_msg.confidence:.2f}), passing")
            return None

        # 2. Sniper validation
        sniper = self.snipers[0]
        sniper_msg = await sniper.analyze(context)

        if sniper_msg.confidence < 0.6:
            logger.info(f"Sniper low confidence ({sniper_msg.confidence:.2f}), passing")
            return None

        # 3. Memory recall
        # Create snapshot for memory recall (simulated for now)
        snapshot = MarketSnapshot(
            timestamp=datetime.utcnow(),
            prices={symbol: context.current_price},
            volatility={symbol: abs(context.price_change_1h) / 100},
            order_book_imbalance={symbol: context.order_book_imbalance},
        )

        memory_advice = await self.memory.recall_for_decision(
            symbol=symbol,
            snapshot=snapshot,
            context=scout_msg.reasoning[:200],
        )

        # 4. Oracle decision with dual-speed cognition
        cognition_prompt = f"""
Scout says: {scout_msg.reasoning[:300]}
Sniper says: {sniper_msg.reasoning[:300]}
Memory advises: {memory_advice}

Symbol: {symbol}
Price: ${context.current_price:.2f}
1H Change: {context.price_change_1h:+.2f}%

Should we trade? If yes, BUY or SELL?
"""

        # Use dual-speed cognition
        cognition_result = await self.cognition.process(
            CognitionRequest(
                prompt=cognition_prompt,
                speed=CognitionSpeed.DUAL,
            )
        )

        self.decisions_made += 1
        if cognition_result.was_overridden:
            self.overrides_triggered += 1

        # 5. Execute if decision is actionable
        if cognition_result.decision in ("BUY", "SELL"):
            execution_request = ExecutionRequest(
                symbol=symbol,
                side=cognition_result.decision,
                quantity=0.1,  # Base position size
                reasoning=cognition_result.reasoning,
            )

            # Execute on first available platform
            for platform, executor in self.executors.items():
                report = await executor.execute_with_reasoning(execution_request)

                if report.success:
                    self.trades_executed += 1

                    # Record in memory
                    self.memory.record_trade(
                        {
                            "symbol": symbol,
                            "side": cognition_result.decision,
                            "quantity": execution_request.quantity,
                            "platform": platform,
                            "avg_price": report.avg_price,
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )

                    return {
                        "decision": cognition_result.decision,
                        "platform": platform,
                        "trade_id": report.trade_id,
                        "reasoning": cognition_result.reasoning,
                    }

        return {"decision": cognition_result.decision, "reasoning": cognition_result.reasoning}

    async def _on_consensus_decision(self, message: CognitiveMessage):
        """Handle consensus decision from mesh."""
        logger.info(f"🔮 Consensus decision: {message.suggested_action} for {message.symbol}")

    async def _on_execution_report(self, message: CognitiveMessage):
        """Handle execution report from mesh."""
        logger.debug(f"⚡ Execution report: {message.metadata}")

    async def _execute_consensus(
        self,
        consensus_id: str,
        state: ConsensusState,
        result: Dict[str, Any],
    ):
        """Execute a finalized consensus decision."""
        logger.info(f"✅ Executing consensus {consensus_id}: {result['action']}")

        # Record event in memory
        self.memory.record_event(f"Consensus {result['action']} on {state.symbol}")

        # Create execution request
        request = ExecutionRequest(
            symbol=state.symbol,
            side=result["action"],
            quantity=0.1,
            consensus_id=consensus_id,
            reasoning=result["reasoning"],
        )

        # Execute across platforms based on availability
        for platform, executor in self.executors.items():
            report = await executor.execute_with_reasoning(request)
            if report.success:
                self.trades_executed += 1
                logger.info(f"✅ Consensus executed on {platform}: {report.trade_id}")
                break


async def main():
    """Main entry point for ACTS."""
    logger.info(
        """
    ╔═══════════════════════════════════════════════════╗
    ║   SAPPHIRE ACTS - Autonomous Cognitive Trading    ║
    ║         Swarm v1.0 (Genesis Release)              ║
    ╚═══════════════════════════════════════════════════╝
    """
    )

    orchestrator = ACTSOrchestrator()

    # Handle shutdown signals
    def shutdown(sig, frame):
        logger.info(f"Received {sig}, initiating shutdown...")
        asyncio.create_task(orchestrator.stop())

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    await orchestrator.start()


if __name__ == "__main__":
    asyncio.run(main())
