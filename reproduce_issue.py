import asyncio
import logging
import sys

from cloud_trader.autonomous_components_init import init_autonomous_components
from cloud_trader.platform_router import PlatformRouter, TradeResult


# Mock dependencies
class MockFeaturePipeline:
    pass


class MockExchangeClient:
    pass


class MockAsterClient:
    pass


class MockSettings:
    enabled_agents = ["trend-momentum-agent"]


async def test_platform_router():
    print("🚀 Starting reproduction test...")

    # Init components
    try:
        data_store, agents, router, scanner = init_autonomous_components(
            feature_pipeline=MockFeaturePipeline(),
            exchange_client=MockExchangeClient(),
            aster_client=MockAsterClient(),
            settings=MockSettings(),
        )

        print(f"✅ Components initialized.")
        print(f"👉 Router Type: {type(router)}")
        print(f"👉 Router Dir: {dir(router)}")

        # Check specific method
        if hasattr(router, "execute_trade"):
            print("✅ 'execute_trade' attribute FOUND.")
        else:
            print("❌ 'execute_trade' attribute MISSING!")

        if hasattr(router, "execute"):
            print("✅ 'execute' attribute FOUND.")
        else:
            print("❌ 'execute' attribute MISSING!")

        # Attempt to call it (mocking the internal adapter call would be needed for full run, but we just check attribute existence)
        print("Test complete.")

    except Exception as e:
        print(f"💥 Exception during test: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_platform_router())
