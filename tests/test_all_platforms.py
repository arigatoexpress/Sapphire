"""
Comprehensive Platform Tests
Tests for all trading platforms: Hyperliquid, Aster, Symphony, Lighter
"""

import asyncio
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cloud_trader.hyperliquid_client import get_hyperliquid_client
from cloud_trader.aster_client import get_aster_client
from cloud_trader.symphony_client import get_symphony_client
from cloud_trader.lighter_client import get_lighter_client
from tests.test_base import PlatformTestBase, TestConfig, assert_price_valid


class HyperliquidTests(Platform

TestBase):
    """Unit tests for Hyperliquid client"""

    def __init__(self):
        super().__init__("Hyperliquid")

    async def setup(self):
        """Initialize Hyperliquid client"""
        print(f"\n{'='*70}")
        print(f"🌐 HYPERLIQUID TESTS")
        print(f"{'='*70}")
        self.client = get_hyperliquid_client()

    async def test_initialization(self):
        """Test client initialization"""
        print(f"🔧 Test: Initialization")
        assert self.client is not None
        print(f"   ✅ Client initialized")
        return {"initialized": True}

    async def test_get_positions(self):
        """Test getting positions"""
        print(f"\n📊 Test: Get Positions")
        positions = await self.client.get_positions()
        print(f"   📋 Positions: {len(positions)}")
        return {"position_count": len(positions)}

    async def test_get_balance(self):
        """Test getting account balance"""
        print(f"\n💰 Test: Get Balance")
        try:
            balance = await self.client.get_balance()
            print(f"   💵 Balance: ${balance:.2f}")
            return {"balance": balance}
        except Exception as e:
            print(f"   ⚠️ Balance fetch failed: {e}")
            return {"error": str(e)}

    async def test_place_order(self):
        """Test placing order (simulated)"""
        print(f"\n📝 Test: Place Order (Simulated)")
        result = await self.client.place_order(
            symbol="BTC-USDC",
            side="buy",
            quantity=0.001,
            order_type="limit",
            price=50000.0
        )
        print(f"   {'✅' if result.get('success') else '❌'} Order result")
        return {"success": result.get("success")}

    async def run_all_tests(self):
        """Run all tests"""
        await self.setup()
        await self.run_test("initialization", self.test_initialization)
        await self.run_test("get_positions", self.test_get_positions)
        await self.run_test("get_balance", self.test_get_balance)
        await self.run_test("place_order", self.test_place_order)
        await self.teardown()
        return self.get_summary()


class AsterTests(PlatformTestBase):
    """Unit tests for Aster client"""

    def __init__(self):
        super().__init__("Aster")

    async def setup(self):
        """Initialize Aster client"""
        print(f"\n{'='*70}")
        print(f"⭐ ASTER TESTS")
        print(f"{'='*70}")
        self.client = get_aster_client()

    async def test_initialization(self):
        """Test client initialization"""
        print(f"🔧 Test: Initialization")
        assert self.client is not None
        print(f"   ✅ Client initialized")
        return {"initialized": True}

    async def test_get_token_price(self):
        """Test getting token price"""
        print(f"\n💰 Test: Get Token Price")
        try:
            price = await self.client.get_token_price("BTC-USDT")
            assert_price_valid(price, "BTC-USDT")
            print(f"   💵 BTC-USDT: ${price:.2f}")
            return {"price": price}
        except Exception as e:
            print(f"   ⚠️ Price fetch failed: {e}")
            return {"error": str(e)}

    async def test_place_order(self):
        """Test placing order (simulated)"""
        print(f"\n📝 Test: Place Order (Simulated)")
        result = await self.client.place_order(
            symbol="BTC-USDT",
            side="buy",
            quantity=0.001,
            order_type="limit",
            price=50000.0
        )
        print(f"   {'✅' if result.get('success') else '❌'} Order result")
        return {"success": result.get("success")}

    async def run_all_tests(self):
        """Run all tests"""
        await self.setup()
        await self.run_test("initialization", self.test_initialization)
        await self.run_test("get_token_price", self.test_get_token_price)
        await self.run_test("place_order", self.test_place_order)
        await self.teardown()
        return self.get_summary()


class SymphonyTests(PlatformTestBase):
    """Unit tests for Symphony client"""

    def __init__(self):
        super().__init__("Symphony")

    async def setup(self):
        """Initialize Symphony client"""
        print(f"\n{'='*70}")
        print(f"🎵 SYMPHONY TESTS")
        print(f"{'='*70}")
        self.client = get_symphony_client()

    async def test_initialization(self):
        """Test client initialization"""
        print(f"🔧 Test: Initialization")
        assert self.client is not None
        print(f"   ✅ Client initialized")
        return {"initialized": True}

    async def test_get_token_price(self):
        """Test getting token price"""
        print(f"\n💰 Test: Get Token Price")
        try:
            price = await self.client.get_token_price("MON-USDC")
            assert_price_valid(price, "MON-USDC")
            print(f"   💵 MON-USDC: ${price:.4f}")
            return {"price": price}
        except Exception as e:
            print(f"   ⚠️ Price fetch failed: {e}")
            return {"error": str(e)}

    async def test_execute_swap(self):
        """Test executing swap (simulated)"""
        print(f"\n🔄 Test: Execute Swap (Simulated)")
        result = await self.client.execute_swap(
            symbol="MON-USDC",
            side="buy",
            amount=1.0
        )
        print(f"   {'✅' if result.get('success') else '❌'} Swap result")
        return {"success": result.get("success")}

    async def run_all_tests(self):
        """Run all tests"""
        await self.setup()
        await self.run_test("initialization", self.test_initialization)
        await self.run_test("get_token_price", self.test_get_token_price)
        await self.run_test("execute_swap", self.test_execute_swap)
        await self.teardown()
        return self.get_summary()


class LighterTests(PlatformTestBase):
    """Unit tests for Lighter client"""

    def __init__(self):
        super().__init__("Lighter")

    async def setup(self):
        """Initialize Lighter client"""
        print(f"\n{'='*70}")
        print(f"💡 LIGHTER TESTS")
        print(f"{'='*70}")
        self.client = get_lighter_client()

    async def test_initialization(self):
        """Test client initialization"""
        print(f"🔧 Test: Initialization")
        await self.client.initialize()
        is_init = self.client.is_initialized if hasattr(self.client, 'is_initialized') else True
        print(f"   {'✅' if is_init else '⚠️'} Client initialized: {is_init}")
        return {"initialized": is_init}

    async def test_get_orderbook(self):
        """Test getting orderbook"""
        print(f"\n📖 Test: Get Orderbook")
        try:
            orderbook = await self.client.get_orderbook("WBTC-USDC")
            print(f"   ✅ Orderbook fetched")
            return {"orderbook": "fetched"}
        except Exception as e:
            print(f"   ⚠️ Orderbook fetch failed: {e}")
            return {"error": str(e)}

    async def test_place_order(self):
        """Test placing order (simulated)"""
        print(f"\n📝 Test: Place Order (Simulated)")
        result = await self.client.place_order(
            symbol="WBTC-USDC",
            side="buy",
            quantity=0.001,
            order_type="limit"
        )
        print(f"   {'✅' if result.get('status') == 'ok' else '❌'} Order result")
        return {"success": result.get("status") == "ok"}

    async def run_all_tests(self):
        """Run all tests"""
        await self.setup()
        await self.run_test("initialization", self.test_initialization)
        await self.run_test("get_orderbook", self.test_get_orderbook)
        await self.run_test("place_order", self.test_place_order)
        await self.teardown()
        return self.get_summary()


async def run_all_platform_tests() -> List[Dict[str, Any]]:
    """Run tests for all platforms"""
    print(f"\n{'='*70}")
    print(f"🧪 COMPREHENSIVE PLATFORM TESTS")
    print(f"{'='*70}")
    print(f"Testing: Hyperliquid, Aster, Symphony, Lighter")
    print(f"{'='*70}\n")

    summaries = []

    # Hyperliquid
    print(f"\n🌐 Running Hyperliquid Tests...")
    hl_tests = HyperliquidTests()
    summaries.append(await hl_tests.run_all_tests())

    # Aster
    print(f"\n⭐ Running Aster Tests...")
    aster_tests = AsterTests()
    summaries.append(await aster_tests.run_all_tests())

    # Symphony
    print(f"\n🎵 Running Symphony Tests...")
    symphony_tests = SymphonyTests()
    summaries.append(await symphony_tests.run_all_tests())

    # Lighter
    print(f"\n💡 Running Lighter Tests...")
    lighter_tests = LighterTests()
    summaries.append(await lighter_tests.run_all_tests())

    return summaries


def print_overall_summary(summaries: List[Dict[str, Any]]):
    """Print overall test summary"""
    print(f"\n{'='*70}")
    print(f"📊 OVERALL TEST SUMMARY")
    print(f"{'='*70}\n")

    total_tests = sum(s['total'] for s in summaries)
    total_passed = sum(s['passed'] for s in summaries)
    total_failed = sum(s['failed'] for s in summaries)
    overall_pass_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0

    print(f"{'Platform':<15} {'Total':>8} {'Passed':>8} {'Failed':>8} {'Pass Rate':>10}")
    print(f"{'-'*70}")

    for summary in summaries:
        print(f"{summary['platform']:<15} "
              f"{summary['total']:>8} "
              f"{summary['passed']:>8} "
              f"{summary['failed']:>8} "
              f"{summary['pass_rate']:>9.1f}%")

    print(f"{'-'*70}")
    print(f"{'TOTAL':<15} {total_tests:>8} {total_passed:>8} {total_failed:>8} {overall_pass_rate:>9.1f}%")
    print(f"{'='*70}\n")

    # Detailed results
    print(f"DETAILED RESULTS:")
    print(f"{'='*70}\n")
    for summary in summaries:
        for result in summary['results']:
            print(result)
        print()


async def main():
    """Main test runner"""
    summaries = await run_all_platform_tests()
    print_overall_summary(summaries)

    total_failed = sum(s['failed'] for s in summaries)
    return total_failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
