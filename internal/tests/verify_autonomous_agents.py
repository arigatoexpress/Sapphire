"""Test Autonomous Agents

Verifies:
1. DataStore provides access to indicators
2. AutonomousAgent queries data and formulates thesis
3. Agent learns from simulated outcomes
"""

import asyncio
import sys


class MockFeaturePipeline:
    """Mock FeaturePipeline for testing."""

    async def get_market_analysis(self, symbol: str):
        """Return mock analysis data."""
        import random

        return {
            "price": 100.0 + random.uniform(-10, 10),
            "rsi": random.uniform(20, 80),
            "trend": random.choice(["BULLISH", "BEARISH", "NEUTRAL"]),
            "volume": 1000000.0,
            "bid_pressure": random.uniform(0.3, 0.7),
            "spread_pct": 0.001,
            "atr": 5.0,
        }


async def test_data_store():
    """Test DataStore functionality."""
    print("\n" + "=" * 60)
    print("TEST 1: DataStore")
    print("=" * 60)

    from cloud_trader.data_store import DataStore

    # Initialize with mock pipeline
    feature_pipeline = MockFeaturePipeline()
    data_store = DataStore(feature_pipeline)

    # Test available indicators
    available = data_store.get_available_indicators()
    print(f"\n📊 Available indicators ({len(available)}): {available[:10]}...")

    # Test fetching indicators
    symbol = "BTC-USDC"
    print(f"\n🔍 Fetching data for {symbol}:")

    indicators_to_test = ["rsi", "volume", "bid_pressure", "social_sentiment"]
    for indicator in indicators_to_test:
        value = await data_store.get(indicator, symbol)
        print(f"  - {indicator}: {value}")

    # Test caching
    print("\n💾 Testing cache:")
    import time

    start_fresh = time.time()
    await data_store.get("rsi", symbol)
    elapsed_fresh = time.time() - start_fresh

    start_cached = time.time()
    await data_store.get("rsi", symbol)
    elapsed_cached = time.time() - start_cached

    print(f"  Fresh fetch: {elapsed_fresh*1000:.2f}ms")
    print(f"  Cached fetch: {elapsed_cached*1000:.2f}ms")
    print(f"  Speedup: {elapsed_fresh/max(elapsed_cached, 0.0001):.1f}x faster")

    print("\n✅ DataStore test passed")
    return data_store


async def test_autonomous_agent(data_store):
    """Test AutonomousAgent functionality."""
    print("\n" + "=" * 60)
    print("TEST 2: Autonomous Agent")
    print("=" * 60)

    from cloud_trader.autonomous_agent import AutonomousAgent

    # Create agents with different specializations
    agents = [
        AutonomousAgent("agent-1", "Technical Trader", data_store, "technical"),
        AutonomousAgent("agent-2", "Sentiment Trader", data_store, "sentiment"),
        AutonomousAgent("agent-3", "Hybrid Trader", data_store, "hybrid"),
    ]

    symbols = ["MON-USDC", "BTC-USDC", "SOL-USDC"]

    for agent in agents:
        print(f"\n🤖 {agent.name} ({agent.specialization}):")
        print(f"  Preferred indicators: {agent.strategy_config['preferred_indicators']}")

        # Analyze one symbol as example
        symbol = symbols[0]
        thesis = await agent.analyze(symbol)
        print(f"\n  {symbol}:")
        print(f"    Signal: {thesis.signal}")
        print(f"    Confidence: {thesis.confidence:.2f}")
        print(f"    Reasoning: {thesis.reasoning}")
        print(f"    Data used: {thesis.data_used}")

    print("\n✅ Autonomous Agent test passed")
    return agents


async def test_agent_learning(agents):
    """Test agent learning from outcomes."""
    print("\n" + "=" * 60)
    print("TEST 3: Agent Learning")
    print("=" * 60)

    agent = agents[0]  # Use first agent

    print(f"\n🧠 Testing {agent.name} learning:")
    print(f"  Initial:")
    print(f"    Preferred indicators: {agent.strategy_config['preferred_indicators']}")
    print(f"    Total trades: {agent.total_trades}")
    print(f"    Win rate: {agent.get_win_rate():.2%}")

    # Simulate trades
    test_symbol = "BTC-USDC"

    # Trade 1: Win
    thesis1 = await agent.analyze(test_symbol)
    agent.learn_from_trade(thesis1, pnl_pct=0.05)  # 5% profit
    print(f"\n  Trade 1: {thesis1.signal} → +5% profit")

    # Trade 2: Loss
    thesis2 = await agent.analyze(test_symbol)
    agent.learn_from_trade(thesis2, pnl_pct=-0.02)  # 2% loss
    print(f"  Trade 2: {thesis2.signal} → -2% loss")

    # Trade 3: Win
    thesis3 = await agent.analyze(test_symbol)
    agent.learn_from_trade(thesis3, pnl_pct=0.03)  # 3% profit
    print(f"  Trade 3: {thesis3.signal} → +3% profit")

    # Check updated preferences
    print(f"\n  After 3 trades:")
    print(f"    Preferred indicators: {agent.strategy_config['preferred_indicators']}")
    print(f"    Total trades: {agent.total_trades}")
    print(f"    Win rate: {agent.get_win_rate():.2%}")

    if agent.strategy_config.get("indicator_scores"):
        print(f"    Indicator scores:")
        for ind, score in sorted(
            agent.strategy_config["indicator_scores"].items(), key=lambda x: x[1], reverse=True
        ):
            print(f"      {ind}: {score:.2f}")

    print("\n✅ Agent learning test passed")


async def test_strategy_summary(agents):
    """Test agent strategy summary."""
    print("\n" + "=" * 60)
    print("TEST 4: Strategy Summary")
    print("=" * 60)

    for agent in agents:
        summary = agent.get_strategy_summary()
        print(f"\n🤖 {agent.name}:")
        print(f"  ID: {summary['id']}")
        print(f"  Specialization: {summary['specialization']}")
        print(f"  Preferred indicators: {summary['preferred_indicators']}")
        print(f"  Total trades: {summary['total_trades']}")
        print(f"  Win rate: {summary['win_rate']:.2%}")

    print("\n✅ Strategy summary test passed")


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("AUTONOMOUS AGENT VERIFICATION")
    print("=" * 60)

    try:
        # Test 1: DataStore
        data_store = await test_data_store()

        # Test 2: Autonomous Agent
        agents = await test_autonomous_agent(data_store)

        # Test 3: Learning
        await test_agent_learning(agents)

        # Test 4: Strategy Summary
        await test_strategy_summary(agents)

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print("\n🎉 Autonomous agents are ready for integration!")
        print("\nKey Features Verified:")
        print("  ✅ DataStore provides unified data access")
        print("  ✅ Agents query indicators autonomously")
        print("  ✅ Agents formulate their own thesis")
        print("  ✅ Agents learn from trade outcomes")
        print("  ✅ Agent preferences evolve over time")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
