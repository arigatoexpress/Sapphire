"""
Manual platform smoke tests.

This module is intentionally not part of CI: it may require live credentials
and external connectivity. It exists as a quick on-demand sanity check for
platform client wiring.

Run:
  python -m tests.test_all_platforms
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List

# Ensure repo root is on sys.path when executed as a module.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cloud_trader.aster_client import get_aster_client
from cloud_trader.lighter_client import get_lighter_client
from tests.test_base import PlatformTestBase, assert_price_valid


class LighterTests(PlatformTestBase):
    """On-demand smoke tests for the Lighter client."""

    def __init__(self) -> None:
        super().__init__("Lighter")

    async def setup(self) -> None:
        print("\n" + "=" * 70)
        print("💡 LIGHTER TESTS")
        print("=" * 70)
        self.client = get_lighter_client()

    async def test_initialization(self) -> Dict[str, Any]:
        print("🔧 Test: Initialization")
        if hasattr(self.client, "initialize"):
            maybe = self.client.initialize()
            if asyncio.iscoroutine(maybe):
                await maybe
        is_init = getattr(self.client, "is_initialized", True)
        print(f"   {'✅' if is_init else '⚠️'} Client initialized: {is_init}")
        return {"initialized": bool(is_init)}

    async def test_get_orderbook(self) -> Dict[str, Any]:
        print("\n📖 Test: Get Orderbook")
        if not hasattr(self.client, "get_orderbook"):
            return {"skipped": True, "reason": "client has no get_orderbook"}
        ob = await self.client.get_orderbook("WBTC-USDC")
        ok = ob is not None
        print(f"   {'✅' if ok else '⚠️'} Orderbook fetched")
        return {"fetched": ok}

    async def run_all_tests(self) -> Dict[str, Any]:
        await self.setup()
        await self.run_test("initialization", self.test_initialization)
        await self.run_test("get_orderbook", self.test_get_orderbook)
        await self.teardown()
        return self.get_summary()


class AsterTests(PlatformTestBase):
    """On-demand smoke tests for the Aster client."""

    def __init__(self) -> None:
        super().__init__("Aster")

    async def setup(self) -> None:
        print("\n" + "=" * 70)
        print("⭐ ASTER TESTS")
        print("=" * 70)
        self.client = get_aster_client()

    async def test_get_token_price(self) -> Dict[str, Any]:
        print("\n💰 Test: Get Token Price")
        if not hasattr(self.client, "get_token_price"):
            return {"skipped": True, "reason": "client has no get_token_price"}
        price = await self.client.get_token_price("BTC-USDT")
        assert_price_valid(float(price), "BTC-USDT")
        print(f"   ✅ BTC-USDT: ${float(price):.2f}")
        return {"price": float(price)}

    async def run_all_tests(self) -> Dict[str, Any]:
        await self.setup()
        await self.run_test("get_token_price", self.test_get_token_price)
        await self.teardown()
        return self.get_summary()


async def run_all_platform_tests() -> List[Dict[str, Any]]:
    print("\n" + "=" * 70)
    print("🧪 MANUAL PLATFORM SMOKE TESTS")
    print("=" * 70 + "\n")

    summaries: List[Dict[str, Any]] = []

    lighter_tests = LighterTests()
    summaries.append(await lighter_tests.run_all_tests())

    aster_tests = AsterTests()
    summaries.append(await aster_tests.run_all_tests())

    return summaries


def print_overall_summary(summaries: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 70)
    print("📊 OVERALL TEST SUMMARY")
    print("=" * 70 + "\n")

    total_tests = sum(s["total"] for s in summaries)
    total_passed = sum(s["passed"] for s in summaries)
    total_failed = sum(s["failed"] for s in summaries)
    overall_pass_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0.0

    print(f"{'Platform':<15} {'Total':>8} {'Passed':>8} {'Failed':>8} {'Pass Rate':>10}")
    print("-" * 70)

    for summary in summaries:
        print(
            f"{summary['platform']:<15} "
            f"{summary['total']:>8} "
            f"{summary['passed']:>8} "
            f"{summary['failed']:>8} "
            f"{summary['pass_rate']:>9.1f}%"
        )

    print("-" * 70)
    print(
        f"{'TOTAL':<15} {total_tests:>8} {total_passed:>8} {total_failed:>8} {overall_pass_rate:>9.1f}%"
    )
    print("=" * 70 + "\n")

    print("DETAILED RESULTS:")
    print("=" * 70 + "\n")
    for summary in summaries:
        for result in summary["results"]:
            print(result)
        print()


async def main() -> bool:
    summaries = await run_all_platform_tests()
    print_overall_summary(summaries)
    return sum(s["failed"] for s in summaries) == 0


if __name__ == "__main__":
    ok = asyncio.run(main())
    raise SystemExit(0 if ok else 1)
