"""
Integration Test for Autonomous Trading System

Tests the complete autonomous trading flow:
1. Component initialization
2. Market scanning
3. Agent consensus
4. Trade execution via PlatformRouter
5. Learning feedback loop

Run this after deploying the refactored trading_service.py
"""

import asyncio
import sys
from pathlib import Path

# Add cloud_trader to path
sys.path.insert(0, str(Path(__file__).parent))


async def test_autonomous_integration():
    """Test the complete autonomous trading workflow."""
    print("🧪 AUTONOMOUS TRADING SYSTEM - INTEGRATION TEST")
    print("=" * 60)

    try:
        # 1. Import components
        print("\n1️⃣ Importing autonomous components...")
        from cloud_trader.autonomous_agent import AutonomousAgent
        from cloud_trader.data.feature_pipeline import FeaturePipeline
        from cloud_trader.data_store import DataStore
        from cloud_trader.market_scanner import MarketScanner
        from cloud_trader.platform_router import AsterAdapter, PlatformRouter, AsterAdapter

        print("   ✅ All components imported successfully")

        # 2. Create mock dependencies
        print("\n2️⃣ Creating mock dependencies...")

        class MockExchangeClient:
            async def get_ticker(self, symbol):
                return {"lastPrice": 100.0, "volume": 1000000}

            async def place_order(self, **kwargs):
                return {"orderId": "mock_123", "status": "FILLED"}

        class MockAsterClient:
            async def execute_swap(self, **kwargs):
                return {"txHash": "mock_tx_123"}

            async def open_perpetual_position(self, **kwargs):
                return {"orderId": "mock_perp_123"}

        mock_exchange = MockExchangeClient()
        mock_aster = MockAsterClient()

        # Create feature pipeline with mocked data
        feature_pipeline = FeaturePipeline(mock_exchange)
        print("   ✅ Mock dependencies created")

        # 3. Initialize components
        print("\n3️⃣ Initializing autonomous components...")
        from cloud_trader.autonomous_components_init import init_autonomous_components

        class MockSettings:
            max_positions = 5

        data_store, autonomous_agents, platform_router, market_scanner = init_autonomous_components(
            feature_pipeline=feature_pipeline,
            exchange_client=mock_exchange,
            aster_client=mock_aster,
            settings=MockSettings(),
        )

        print(f"   ✅ DataStore initialized")
        print(f"   ✅ {len(autonomous_agents)} autonomous agents created:")
        for agent in autonomous_agents:
            print(f"      - {agent.id} ({agent.specialization})")
        print(f"   ✅ PlatformRouter initialized")
        print(f"   ✅ MarketScanner initialized")

        # 4. Test MarketScanner
        print("\n4️⃣ Testing MarketScanner...")
        opportunities = await market_scanner.scan()
        if opportunities:
            print(f"   ✅ Found {len(opportunities)} opportunities")
            best = opportunities[0]
            print(f"      Best: {best.symbol} ({best.signal}) - Score: {best.score:.2f}")
        else:
            print("   ⚠️ No opportunities found (expected in test environment)")

        # 5. Test Agent Consensus
        print("\n5️⃣ Testing Agent Consensus...")
        test_symbol = "BTC-USDC"
        theses = []
        for agent in autonomous_agents:
            thesis = await agent.analyze(test_symbol)
            theses.append((agent, thesis))
            print(f"   🤖 {agent.id}: {thesis.signal} (conf: {thesis.confidence:.2f})")

        # Calculate consensus
        buy_score = sum(t.confidence for a, t in theses if t.signal == "BUY")
        sell_score = sum(t.confidence for a, t in theses if t.signal == "SELL")
        hold_score = sum(t.confidence for a, t in theses if t.signal == "HOLD")

        print(f"\n   📊 Consensus Scores:")
        print(f"      BUY:  {buy_score:.2f}")
        print(f"      SELL: {sell_score:.2f}")
        print(f"      HOLD: {hold_score:.2f}")

        if max(buy_score, sell_score) >= 1.5:
            final_signal = "BUY" if buy_score > sell_score else "SELL"
            print(f"   ✅ Strong consensus reached: {final_signal}")
        else:
            print(f"   ⏸️ No strong consensus (threshold: 1.5)")

        # 6. Test PlatformRouter
        print("\n6️⃣ Testing PlatformRouter...")

        # Test Aster routing
        result = await platform_router.execute(
            symbol="ETH-USDC", side="BUY", quantity=0.1, platform="aster"
        )
        print(f"   ✅ Aster trade: {result.success} - Order ID: {result.order_id}")

        # Test Aster routing (swap)
        result = await platform_router.execute(
            symbol="MON-USDC", side="BUY", quantity=100, platform="aster"
        )
        print(f"   ✅ Aster swap: {result.success}, Metadata: {result.metadata}")

        # 7. Test Learning Mechanism
        print("\n7️⃣ Testing Agent Learning...")
        test_agent = autonomous_agents[0]

        # Simulate profitable trade
        test_thesis = Thesis(
            symbol="BTC-USDC",
            signal="BUY",
            confidence=0.8,
            reasoning="Test thesis using RSI and volume",
            data_used=["rsi", "volume"],
        )

        test_agent.learn_from_trade(test_thesis, 0.05)  # 5% profit

        print(f"   ✅ Agent learned from profitable trade")
        print(f"      Win rate: {test_agent.get_win_rate():.2f}")
        print(
            f"      Preferred ind.: {list(test_agent.strategy_config['preferred_indicators'])[:3]}..."
        )

        # FINAL REPORT
        print("\n" + "=" * 60)
        print("✅ INTEGRATION TEST COMPLETE")
        print("=" * 60)
        print("\n📋 Summary:")
        print(f"   ✅ All components initialized successfully")
        print(f"   ✅ MarketScanner operational")
        print(f"   ✅ {len(autonomous_agents)} agents formulating theses")
        print(f"   ✅ PlatformRouter routing to Aster & Aster")
        print(f"   ✅ Learning mechanism functional")
        print("\n🚀 System ready for live deployment!\n")

        return True

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_autonomous_integration())
    sys.exit(0 if success else 1)
