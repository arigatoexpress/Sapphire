"""
Drift Protocol Unit Tests
Tests for Solana perpetual futures trading via Drift
"""

import asyncio
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cloud_trader.drift_client import get_drift_client
from tests.test_base import (
    PlatformTestBase,
    TestConfig,
    assert_price_valid,
    calculate_stop_loss_price,
    calculate_take_profit_price
)


class DriftTests(PlatformTestBase):
    """Unit tests for Drift Protocol client"""

    def __init__(self):
        super().__init__("Drift")
        self.client = None
        self.test_position_opened = False

    async def setup(self):
        """Initialize Drift client"""
        print(f"\n{'='*70}")
        print(f"🌊 DRIFT PROTOCOL TESTS")
        print(f"{'='*70}")
        print(f"Platform: Solana Perpetual Futures")
        print(f"Markets: {', '.join(TestConfig.DRIFT_TEST_SYMBOLS)}")
        print(f"Test Size: {TestConfig.TEST_SOL_SIZE} SOL")
        print(f"Leverage: {TestConfig.TEST_LEVERAGE}x")
        print(f"{'='*70}\n")

        self.client = get_drift_client()

    async def teardown(self):
        """Cleanup Drift client"""
        if self.client:
            await self.client.close()

    # Test 1: Initialization
    async def test_initialization(self):
        """Test Drift client initializes correctly"""
        print(f"🔧 Test 1: Initialization")

        await self.client.initialize()

        if not self.client.is_initialized:
            print(f"   ⚠️ Drift not initialized (expected in local testing)")
            print(f"      Drift requires private key from Cloud Run secrets")
            return {"initialized": False, "note": "Requires production environment"}

        print(f"   ✅ Client initialized")
        print(f"   📍 Wallet: {self.client.expected_wallet[:8]}...{self.client.expected_wallet[-8:]}")

        return {
            "initialized": True,
            "wallet": self.client.expected_wallet
        }

    # Test 2: Get Perp Market Info
    async def test_get_perp_market(self):
        """Test fetching perpetual market information"""
        print(f"\n📊 Test 2: Get Perp Market Info")

        if not self.client.is_initialized:
            print(f"   ⏭️ Skipped (client not initialized)")
            return {"skipped": True}

        market = "SOL-PERP"
        market_info = await self.client.get_perp_market(market)

        assert market_info is not None, "Market info is None"
        print(f"   📈 Market: {market}")

        if "oracle_price" in market_info:
            price = market_info["oracle_price"]
            assert_price_valid(price, market)
            print(f"   💰 Oracle Price: ${price:.2f}")

        if "funding_rate" in market_info:
            print(f"   📊 Funding Rate: {market_info['funding_rate']:.6f}%")

        return {
            "market": market,
            "info": {k: str(v)[:50] for k, v in market_info.items()}
        }

    # Test 3: Get All Perp Positions
    async def test_get_all_positions(self):
        """Test fetching all open positions"""
        print(f"\n📋 Test 3: Get All Positions")

        if not self.client.is_initialized:
            print(f"   ⏭️ Skipped (client not initialized)")
            return {"skipped": True}

        positions = await self.client.get_all_perp_positions()

        print(f"   📊 Total Positions: {len(positions)}")

        if positions:
            for pos in positions[:3]:  # Show first 3
                print(f"   • {pos['market']}: {pos['side'].upper()} {pos['size']:.4f}")
                print(f"     Entry: ${pos['entry_price']:.2f}, P&L: ${pos['unrealized_pnl']:.2f}")

        return {
            "position_count": len(positions),
            "positions": [
                {
                    "market": p["market"],
                    "side": p["side"],
                    "size": p["size"]
                }
                for p in positions[:5]
            ]
        }

    # Test 4: Market Index Mapping
    async def test_market_index_mapping(self):
        """Test market symbol to index conversion"""
        print(f"\n🔢 Test 4: Market Index Mapping")

        test_markets = ["SOL-PERP", "BTC-PERP", "ETH-PERP"]
        mappings = {}

        for market in test_markets:
            index = self.client._get_market_index(market)
            symbol = self.client._get_market_symbol(index)

            assert index is not None, f"No index for {market}"
            assert symbol == market, f"Mapping mismatch: {market} -> {index} -> {symbol}"

            mappings[market] = index
            print(f"   ✅ {market:12} → Index {index}")

        return {"mappings": mappings}

    # Test 5: Open Position (Simulated)
    async def test_open_position_simulated(self):
        """Test opening a perpetual position (simulated)"""
        print(f"\n🚀 Test 5: Open Position (Simulated)")

        if not self.client.is_initialized:
            print(f"   ⏭️ Skipped (client not initialized)")
            return {"skipped": True}

        market = "SOL-PERP"
        direction = "long"
        size = TestConfig.TEST_SOL_SIZE
        leverage = TestConfig.TEST_LEVERAGE

        # Get current price for stop-loss calculation
        market_info = await self.client.get_perp_market(market)
        current_price = market_info.get("oracle_price", 127.0)

        stop_loss = calculate_stop_loss_price(current_price, "buy", 0.05)
        take_profit = calculate_take_profit_price(current_price, "buy", 0.10)

        print(f"   📊 Market: {market}")
        print(f"   📈 Direction: {direction.upper()}")
        print(f"   💰 Size: {size} SOL")
        print(f"   ⚡ Leverage: {leverage}x")
        print(f"   🛡️ Stop-Loss: ${stop_loss:.2f}")
        print(f"   🎯 Take-Profit: ${take_profit:.2f}")

        # In simulation mode, this returns simulated result
        result = await self.client.open_perp_position(
            market=market,
            direction=direction,
            size=size,
            leverage=leverage,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

        assert result is not None, "Result is None"
        print(f"   {'✅' if result.get('success') else '❌'} Result: {result.get('success', False)}")

        if result.get("tx_sig"):
            print(f"   🔗 Tx: {result['tx_sig'][:16]}...")
            self.test_position_opened = True

        return {
            "market": market,
            "direction": direction,
            "size": size,
            "leverage": leverage,
            "success": result.get("success"),
            "tx_sig": result.get("tx_sig")
        }

    # Test 6: Close Position (Simulated)
    async def test_close_position_simulated(self):
        """Test closing a perpetual position (simulated)"""
        print(f"\n🔒 Test 6: Close Position (Simulated)")

        if not self.client.is_initialized:
            print(f"   ⏭️ Skipped (client not initialized)")
            return {"skipped": True}

        if not self.test_position_opened:
            print(f"   ⏭️ Skipped (no position opened in previous test)")
            return {"skipped": True}

        market = "SOL-PERP"

        result = await self.client.close_perp_position(
            market=market,
            size=None  # Close all
        )

        assert result is not None, "Result is None"
        print(f"   {'✅' if result.get('success') else '❌'} Result: {result.get('success', False)}")

        if result.get("pnl"):
            print(f"   💰 P&L: ${result['pnl']:.2f}")

        if result.get("tx_sig"):
            print(f"   🔗 Tx: {result['tx_sig'][:16]}...")

        return {
            "market": market,
            "success": result.get("success"),
            "pnl": result.get("pnl"),
            "tx_sig": result.get("tx_sig")
        }

    # Test 7: Get Supported Markets
    async def test_get_supported_markets(self):
        """Test getting list of supported perpetual markets"""
        print(f"\n📋 Test 7: Get Supported Markets")

        from cloud_trader.definitions import DRIFT_PERP_SYMBOLS

        markets = DRIFT_PERP_SYMBOLS
        print(f"   📊 Total Markets: {len(markets)}")
        print(f"   🎯 Markets: {', '.join(markets)}")

        assert len(markets) == 15, f"Expected 15 markets, got {len(markets)}"

        return {
            "total_markets": len(markets),
            "markets": markets
        }

    # Test 8: Wallet Verification
    async def test_wallet_verification(self):
        """Test wallet address verification"""
        print(f"\n🔑 Test 8: Wallet Verification")

        expected_wallet = "B1UUWzWr9hWYfUE2xLEDVpyWzWWNWcTPv7Ea2j6guEZD"
        assert self.client.expected_wallet == expected_wallet, "Wallet mismatch"

        print(f"   ✅ Expected Wallet: {expected_wallet[:8]}...{expected_wallet[-8:]}")
        print(f"   ✅ Verification config correct")

        return {
            "expected_wallet": expected_wallet,
            "verification": "configured"
        }

    async def run_all_tests(self):
        """Run all Drift tests"""
        await self.setup()

        # Run tests in sequence
        await self.run_test("test_initialization", self.test_initialization)
        await self.run_test("test_get_perp_market", self.test_get_perp_market)
        await self.run_test("test_get_all_positions", self.test_get_all_positions)
        await self.run_test("test_market_index_mapping", self.test_market_index_mapping)
        await self.run_test("test_open_position_simulated", self.test_open_position_simulated)
        await self.run_test("test_close_position_simulated", self.test_close_position_simulated)
        await self.run_test("test_get_supported_markets", self.test_get_supported_markets)
        await self.run_test("test_wallet_verification", self.test_wallet_verification)

        await self.teardown()

        return self.get_summary()


async def main():
    """Run Drift tests"""
    tests = DriftTests()
    summary = await tests.run_all_tests()

    print(f"\n{'='*70}")
    print(f"📊 DRIFT TEST SUMMARY")
    print(f"{'='*70}")
    print(f"Platform: {summary['platform']}")
    print(f"Total Tests: {summary['total']}")
    print(f"Passed: {summary['passed']} ✅")
    print(f"Failed: {summary['failed']} ❌")
    print(f"Pass Rate: {summary['pass_rate']:.1f}%")
    print(f"{'='*70}\n")

    # Print individual results
    for result in summary['results']:
        print(result)

    return summary['failed'] == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
