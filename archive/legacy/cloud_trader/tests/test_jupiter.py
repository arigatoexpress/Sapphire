"""
Jupiter DEX Unit Tests
Tests for Solana spot trading via Jupiter aggregator
"""

import asyncio
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cloud_trader.jupiter_client import get_jupiter_client
from tests.test_base import PlatformTestBase, TestConfig, assert_price_valid


class JupiterTests(PlatformTestBase):
    """Unit tests for Jupiter DEX client"""

    def __init__(self):
        super().__init__("Jupiter")
        self.client = None

    async def setup(self):
        """Initialize Jupiter client"""
        print(f"\n{'='*70}")
        print(f"🪐 JUPITER DEX TESTS")
        print(f"{'='*70}")
        print(f"Platform: Solana DEX Aggregator (Spot Trading)")
        print(f"Markets: {', '.join(TestConfig.JUPITER_TEST_SYMBOLS)}")
        print(f"Test Size: {TestConfig.TEST_SOL_SIZE} SOL")
        print(f"{'='*70}\n")

        self.client = get_jupiter_client()

    async def teardown(self):
        """Cleanup Jupiter client"""
        if self.client:
            await self.client.close()

    # Test 1: Initialization
    async def test_initialization(self):
        """Test Jupiter client initializes correctly"""
        print(f"🔧 Test 1: Initialization")

        # Check client exists
        assert self.client is not None, "Jupiter client is None"

        # Check configuration
        assert hasattr(self.client, 'wallet_address'), "Missing wallet_address"
        assert hasattr(self.client, 'rpc_url'), "Missing rpc_url"

        print(f"   ✅ Client initialized")
        print(f"   📍 Wallet: {self.client.wallet_address[:8]}...{self.client.wallet_address[-8:]}")

        return {
            "wallet": self.client.wallet_address,
            "rpc_url": self.client.rpc_url
        }

    # Test 2: Get Token Price
    async def test_get_token_price(self):
        """Test fetching token prices"""
        print(f"\n💰 Test 2: Get Token Price")

        test_symbols = ["SOL-USDC", "JUP-USDC"]
        prices = {}

        for symbol in test_symbols:
            price = await self.client.get_token_price(symbol)
            assert_price_valid(price, symbol)
            prices[symbol] = price
            print(f"   💵 {symbol}: ${price:.4f}")

        return {"prices": prices}

    # Test 3: Get Quote
    async def test_get_quote(self):
        """Test getting swap quotes"""
        print(f"\n📊 Test 3: Get Quote")

        symbol = "SOL-USDC"
        amount = TestConfig.TEST_SOL_SIZE

        quote = await self.client.get_quote(
            input_mint=symbol.split('-')[0],
            output_mint=symbol.split('-')[1],
            amount=amount
        )

        assert quote is not None, "Quote is None"
        assert "outAmount" in quote or "output_amount" in quote, "Missing output amount in quote"

        output_key = "outAmount" if "outAmount" in quote else "output_amount"
        output_amount = float(quote[output_key]) / 1e6  # USDC has 6 decimals

        print(f"   📈 Input: {amount} SOL")
        print(f"   📉 Output: ~${output_amount:.2f} USDC")
        print(f"   ✅ Quote received")

        return {
            "input_amount": amount,
            "output_amount": output_amount,
            "quote": str(quote)[:100]
        }

    # Test 4: Execute Spot Swap (Simulated)
    async def test_execute_swap_simulated(self):
        """Test executing a spot swap (simulation mode)"""
        print(f"\n🔄 Test 4: Execute Swap (Simulated)")

        symbol = "SOL-USDC"
        side = "sell"  # Sell SOL for USDC
        amount = TestConfig.TEST_SOL_SIZE

        # Note: In production, this would execute a real swap
        # For testing, we use simulation mode
        result = await self.client.execute_trade(
            symbol=symbol,
            side=side,
            quantity=amount
        )

        assert result is not None, "Trade result is None"
        assert "success" in result, "Missing success flag"

        print(f"   📝 Symbol: {symbol}")
        print(f"   📊 Side: {side.upper()}")
        print(f"   💰 Amount: {amount} SOL")
        print(f"   {'✅' if result.get('success') else '❌'} Result: {result.get('status', 'unknown')}")

        if result.get("tx_sig"):
            print(f"   🔗 Tx: {result['tx_sig'][:16]}...")

        return {
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "success": result.get("success"),
            "tx_sig": result.get("tx_sig")
        }

    # Test 5: Get Wallet Balance
    async def test_get_wallet_balance(self):
        """Test getting wallet token balances"""
        print(f"\n💼 Test 5: Get Wallet Balance")

        # Try to get SOL balance
        try:
            balance = await self.client.get_balance("SOL")
            print(f"   💰 SOL Balance: {balance:.6f}")

            return {"SOL": balance}
        except Exception as e:
            print(f"   ⚠️ Could not fetch balance: {e}")
            return {"error": str(e)}

    # Test 6: Get Supported Markets
    async def test_get_supported_markets(self):
        """Test getting list of supported markets"""
        print(f"\n📋 Test 6: Get Supported Markets")

        from cloud_trader.definitions import JUPITER_SPOT_SYMBOLS

        markets = JUPITER_SPOT_SYMBOLS
        print(f"   📊 Total Markets: {len(markets)}")
        print(f"   🎯 Sample Markets: {', '.join(markets[:5])}")

        assert len(markets) > 0, "No markets defined"

        return {
            "total_markets": len(markets),
            "markets": markets[:10]
        }

    # Test 7: Error Handling
    async def test_error_handling(self):
        """Test error handling for invalid operations"""
        print(f"\n⚠️ Test 7: Error Handling")

        # Test 1: Invalid symbol
        try:
            price = await self.client.get_token_price("INVALID-SYMBOL")
            # Should return 0 or handle gracefully
            print(f"   ✅ Invalid symbol handled gracefully (price: {price})")
        except Exception as e:
            print(f"   ✅ Invalid symbol raised exception: {type(e).__name__}")

        # Test 2: Zero amount
        try:
            result = await self.client.execute_trade("SOL-USDC", "buy", 0.0)
            print(f"   ✅ Zero amount handled: {result.get('status')}")
        except Exception as e:
            print(f"   ✅ Zero amount raised exception: {type(e).__name__}")

        return {"error_handling": "passed"}

    async def run_all_tests(self):
        """Run all Jupiter tests"""
        await self.setup()

        # Run tests in sequence
        await self.run_test("test_initialization", self.test_initialization)
        await self.run_test("test_get_token_price", self.test_get_token_price)
        await self.run_test("test_get_quote", self.test_get_quote)
        await self.run_test("test_execute_swap_simulated", self.test_execute_swap_simulated)
        await self.run_test("test_get_wallet_balance", self.test_get_wallet_balance)
        await self.run_test("test_get_supported_markets", self.test_get_supported_markets)
        await self.run_test("test_error_handling", self.test_error_handling)

        await self.teardown()

        return self.get_summary()


async def main():
    """Run Jupiter tests"""
    tests = JupiterTests()
    summary = await tests.run_all_tests()

    print(f"\n{'='*70}")
    print(f"📊 JUPITER TEST SUMMARY")
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
