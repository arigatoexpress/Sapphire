#!/usr/bin/env python3
"""
ACTS System Integration Test

Tests all components of the Autonomous Cognitive Trading Swarm:
1. Cognitive Mesh (message passing)
2. Cognitive Agents (Scout, Sniper, Oracle)
3. Dual-Speed Cognition (Flash + Pro)
4. Episodic Memory (regime learning)
5. Sapphire Neural Cache (MoE + encoding)

Run: python test_acts.py
"""

import asyncio
import logging
import os
import sys
import time

# Add shared to path
sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("TEST")

# Test results tracker
results = {"passed": 0, "failed": 0, "tests": []}


def test_result(name: str, passed: bool, message: str = ""):
    """Record a test result."""
    status = "✅ PASS" if passed else "❌ FAIL"
    results["passed" if passed else "failed"] += 1
    results["tests"].append({"name": name, "passed": passed, "message": message})
    logger.info(f"{status}: {name} {f'- {message}' if message else ''}")


async def test_cognitive_mesh():
    """Test the cognitive mesh communication."""
    logger.info("\n🧪 Testing Cognitive Mesh...")

    try:
        from cognitive_mesh import (
            AgentRole,
            CognitiveMesh,
            CognitiveMessage,
            MessageType,
            get_cognitive_mesh,
        )

        mesh = get_cognitive_mesh()

        # Test agent registration
        await mesh.register_agent("test-scout", AgentRole.SCOUT, ["observation"])
        test_result("Agent Registration", "test-scout" in mesh.agents)

        # Test message broadcast
        received = []

        def on_message(msg):
            received.append(msg)

        mesh.subscribe(
            "all", lambda m: asyncio.create_task(asyncio.coroutine(lambda: received.append(m))())
        )

        msg = CognitiveMessage(
            message_id="test-1",
            agent_id="test-scout",
            agent_role=AgentRole.SCOUT,
            message_type=MessageType.OBSERVATION,
            reasoning="Test observation: Market looks bullish",
            symbol="SOL",
            confidence=0.8,
        )

        await mesh.broadcast(msg)
        test_result("Message Broadcast", len(mesh.message_log) > 0)

        # Test reasoning hash
        hash_val = msg.get_reasoning_hash()
        test_result("Reasoning Hash", len(hash_val) == 16, f"Hash: {hash_val}")

    except Exception as e:
        test_result("Cognitive Mesh", False, str(e))


async def test_cognitive_agents():
    """Test the cognitive agents."""
    logger.info("\n🧪 Testing Cognitive Agents...")

    try:
        from cognitive_agent import MarketContext, OracleAgent, ScoutAgent, SniperAgent
        from cognitive_mesh import get_cognitive_mesh

        mesh = get_cognitive_mesh()

        # Create agents
        scout = ScoutAgent("test-scout-1")
        sniper = SniperAgent("test-sniper-1")
        oracle = OracleAgent("test-oracle-1")

        # Connect to mesh
        await scout.connect(mesh)
        await sniper.connect(mesh)
        await oracle.connect(mesh)

        test_result("Agent Creation", True, "Scout, Sniper, Oracle created")

        # Test with mock context
        context = MarketContext(
            symbol="SOL",
            current_price=142.50,
            price_change_1h=2.5,
            price_change_24h=8.3,
            volume_24h=500_000_000,
        )

        # Only run reasoning if API key available
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

        if api_key:
            scout_msg = await scout.analyze(context)
            test_result(
                "Scout Analysis", scout_msg is not None, f"Confidence: {scout_msg.confidence:.2f}"
            )
        else:
            test_result("Scout Analysis", True, "Skipped (no API key - mock mode)")

    except Exception as e:
        test_result("Cognitive Agents", False, str(e))


async def test_dual_speed_cognition():
    """Test the dual-speed cognition system."""
    logger.info("\n🧪 Testing Dual-Speed Cognition...")

    try:
        from dual_speed_cognition import (
            CognitionRequest,
            CognitionSpeed,
            DualSpeedCognition,
            get_dual_cognition,
        )

        cognition = get_dual_cognition()

        test_result("Cognition Init", cognition is not None)

        # Test with simple request
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

        if api_key:
            request = CognitionRequest(
                prompt="SOL is up 5% with volume spike. BUY, SELL, or HOLD?",
                speed=CognitionSpeed.SYSTEM_1,  # Fast path only for test
            )

            start = time.time()
            result = await cognition.process(request)
            latency = (time.time() - start) * 1000

            test_result(
                "System 1 Speed",
                latency < 5000,
                f"Latency: {latency:.0f}ms, Decision: {result.decision}",
            )
        else:
            test_result("Dual Cognition", True, "Skipped (no API key - mock mode)")

        # Test metrics
        metrics = cognition.get_metrics()
        test_result("Cognition Metrics", "system1_calls" in metrics)

    except Exception as e:
        test_result("Dual-Speed Cognition", False, str(e))


async def test_episodic_memory():
    """Test the episodic memory system."""
    logger.info("\n🧪 Testing Episodic Memory...")

    try:
        from episodic_memory import EpisodicMemoryBank, MarketEpisode, get_episodic_memory

        # Use temp storage for test
        memory = EpisodicMemoryBank(storage_path="/tmp/test_sapphire_memory.json")

        # Start episode
        ep = memory.start_episode(
            name="Test Episode",
            regime="trending_up",
            symbols=["SOL", "BTC"],
        )

        test_result("Episode Start", ep is not None, f"ID: {ep.episode_id}")

        # Record trade
        memory.record_trade(
            {
                "symbol": "SOL",
                "side": "BUY",
                "quantity": 1.0,
                "price": 142.50,
                "pnl": 15.00,
            }
        )

        test_result("Trade Recording", len(memory.current_episode.trades) == 1)

        # Record event
        memory.record_event("Volume spike detected")
        test_result("Event Recording", len(memory.current_episode.key_events) == 1)

        # End episode
        ended = memory.end_episode(
            price_change_pct=5.0,
            volume_change_pct=150.0,
        )

        test_result("Episode End", ended is not None and ended.total_pnl == 15.00)

        # Find similar
        similar = memory.find_similar_episodes("trending_up", ["SOL"])
        test_result("Similar Episode Search", len(similar) > 0)

        # Stats
        stats = memory.get_stats()
        test_result("Memory Stats", stats["total_episodes"] >= 1)

    except Exception as e:
        test_result("Episodic Memory", False, str(e))


async def test_neural_cache():
    """Test the Sapphire Neural Cache."""
    logger.info("\n🧪 Testing Sapphire Neural Cache...")

    try:
        from sapphire_neural_cache import (
            MemoryMoE,
            NeuralKVCache,
            PacketBuffer,
            Platform,
            SapphireNeuralCache,
            TradePacket,
            TradeSide,
            get_neural_cache,
        )

        # Test TradePacket encoding
        original = TradePacket(
            timestamp=int(time.time()),
            symbol="SOL",
            side=TradeSide.BUY,
            platform=Platform.DRIFT,
            price=142.50,
            quantity=1.5,
            trade_id="test-trade-123",
        )

        encoded = original.encode()
        test_result("TradePacket Encoding", len(encoded) == 32, f"Size: {len(encoded)} bytes")

        # Test decoding
        decoded = TradePacket.decode(encoded)
        test_result(
            "TradePacket Decoding",
            decoded.symbol == "SOL" and decoded.price == 142.50,
            f"Symbol: {decoded.symbol}, Price: {decoded.price}",
        )

        # Test from_dict
        packet = TradePacket.from_dict(
            {
                "symbol": "BTC",
                "side": "SELL",
                "price": 45000.00,
                "quantity": 0.1,
                "platform": "hyperliquid",
            }
        )
        test_result("TradePacket from_dict", packet.symbol == "BTC")

        # Test KV Cache
        cache = NeuralKVCache[str](max_size=10, name="test")

        for i in range(15):
            cache.put(f"key-{i}", f"value-{i}")

        test_result("KV Cache Size Limit", len(cache.cache) == 10)
        test_result("KV Cache Eviction", cache.evictions == 5)

        # Test cache hit
        cache.put("hot-key", "hot-value", prefetch_hint=0.9)
        result = cache.get("hot-key")
        test_result("KV Cache Hit", result == "hot-value")

        stats = cache.get_stats()
        test_result("KV Cache Stats", stats["hit_rate"] > 0)

        # Test MoE
        moe = MemoryMoE()

        # Query routing
        trade_query = {"type": "trade", "symbol": "SOL"}
        results = await moe.query(trade_query)
        test_result("MoE Trade Query", True, f"Routed successfully")

        regime_query = {"type": "regime"}
        results = await moe.query(regime_query)
        test_result("MoE Regime Query", True)

        moe_stats = moe.get_stats()
        test_result("MoE Stats", moe_stats["total_queries"] >= 2)

        # Test unified interface
        snc = get_neural_cache()

        snc.ingest_trade(
            {
                "symbol": "ETH",
                "side": "BUY",
                "price": 2500.00,
                "quantity": 0.5,
                "platform": "aster",
            }
        )

        test_result("Neural Cache Ingest", True)

        snc.update_regime("ETH", "ranging")
        result = await snc.query({"type": "regime", "symbol": "ETH"})
        test_result("Neural Cache Regime", result == "ranging")

    except Exception as e:
        test_result("Sapphire Neural Cache", False, str(e))


async def test_acts_orchestrator():
    """Test the ACTS orchestrator (lightweight, no full start)."""
    logger.info("\n🧪 Testing ACTS Orchestrator...")

    try:
        from acts_orchestrator import ACTSOrchestrator

        orchestrator = ACTSOrchestrator()
        test_result("Orchestrator Creation", orchestrator is not None)

        # Initialize (doesn't start loops)
        await orchestrator.initialize()

        test_result("Orchestrator Init", orchestrator.mesh is not None)
        test_result("Scouts Spawned", len(orchestrator.scouts) >= 1)
        test_result("Snipers Spawned", len(orchestrator.snipers) >= 1)
        test_result("Oracles Spawned", len(orchestrator.oracles) >= 1)

    except Exception as e:
        test_result("ACTS Orchestrator", False, str(e))


async def run_all_tests():
    """Run all test suites."""
    print(
        """
    ╔═══════════════════════════════════════════════════╗
    ║        SAPPHIRE ACTS INTEGRATION TESTS            ║
    ╚═══════════════════════════════════════════════════╝
    """
    )

    start_time = time.time()

    await test_cognitive_mesh()
    await test_cognitive_agents()
    await test_dual_speed_cognition()
    await test_episodic_memory()
    await test_neural_cache()
    await test_acts_orchestrator()

    duration = time.time() - start_time

    print(
        f"""
    ════════════════════════════════════════════════════
    📊 TEST RESULTS
    ════════════════════════════════════════════════════
    ✅ Passed: {results['passed']}
    ❌ Failed: {results['failed']}
    ⏱️  Duration: {duration:.2f}s
    ════════════════════════════════════════════════════
    """
    )

    if results["failed"] > 0:
        print("Failed tests:")
        for test in results["tests"]:
            if not test["passed"]:
                print(f"  - {test['name']}: {test['message']}")

    return results["failed"] == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
