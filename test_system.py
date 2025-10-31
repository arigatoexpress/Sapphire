#!/usr/bin/env python3
"""System validation and testing script"""

import sys
import asyncio
import os
sys.path.append('.')

async def test_system():
    print("🚀 Testing Autonomous Trading System Components")
    print("=" * 50)

    # Test 1: Imports
    print("\n📦 Testing Imports...")
    try:
        from cloud_trader.config import get_settings
        from cloud_trader.service import TradingService
        from cloud_trader.orchestrator.schemas import OrderIntent
        from cloud_trader.orchestrator.client import RiskOrchestratorClient
        print("✅ All imports successful")
    except Exception as e:
        print(f"❌ Import error: {e}")
        return False

    # Test 2: Configuration
    print("\n⚙️ Testing Configuration...")
    try:
        settings = get_settings()
        print(f"✅ Settings loaded: bot_id={settings.bot_id}")
        print(f"   Redis URL: {settings.redis_url}")
        print(f"   Orchestrator URL: {settings.orchestrator_url}")
        print(f"   LLM enabled: {settings.enable_llm_trading}")
        print(f"   LLM confidence threshold: {settings.min_llm_confidence}")
    except Exception as e:
        print(f"❌ Settings error: {e}")
        return False

    # Test 3: OrderIntent creation
    print("\n📋 Testing OrderIntent...")
    try:
        intent = OrderIntent(
            symbol='BTCUSDT',
            side='BUY',
            notional=100.0,
            order_type='MARKET'
        )
        print("✅ OrderIntent creation works")
        print(f"   Symbol: {intent.symbol}, Side: {intent.side}, Notional: ${intent.notional}")
    except Exception as e:
        print(f"❌ OrderIntent error: {e}")
        return False

    # Test 4: Orchestrator connectivity
    print("\n🌐 Testing Orchestrator Connectivity...")
    try:
        if settings.orchestrator_url:
            client = RiskOrchestratorClient(settings.orchestrator_url)
            # Test health endpoint
            response = await client._client.get("/")
            if response.status_code == 200:
                print("✅ Orchestrator connection successful")
            else:
                print(f"⚠️ Orchestrator responded with status {response.status_code}")
            await client.close()
        else:
            print("⚠️ No orchestrator URL configured")
    except Exception as e:
        print(f"❌ Orchestrator connectivity error: {e}")

    # Test 5: Redis connectivity (if available)
    print("\n💾 Testing Redis Connectivity...")
    try:
        import redis.asyncio as redis
        if settings.redis_url:
            r = redis.from_url(settings.redis_url)
            await r.ping()
            await r.close()
            print("✅ Redis connection successful")
        else:
            print("⚠️ No Redis URL configured")
    except Exception as e:
        print(f"❌ Redis connectivity error: {e}")

    print("\n🎯 System validation completed!")
    return True

if __name__ == "__main__":
    success = asyncio.run(test_system())
    if success:
        print("\n✅ All core components are functional!")
    else:
        print("\n❌ System validation failed!")
        sys.exit(1)
