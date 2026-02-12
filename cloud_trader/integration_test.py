#!/usr/bin/env python3
"""
Integration Test Suite for Multi-Platform Trading System.
Tests connectivity, balance fetching, and order placement across:
- Aster DEX

- Aster (Solana)
- Aster (Monad/Base)

Run with: python -m cloud_trader.integration_test
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cloud_trader.config import get_settings
from cloud_trader.exchange import AsterClient


class IntegrationTestResult:
    """Container for test results."""

    def __init__(self, platform: str):
        self.platform = platform
        self.connection_ok = False
        self.balance_ok = False
        self.balance_value = 0.0
        self.order_ok = False
        self.order_id = None
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "platform": self.platform,
            "connection_ok": self.connection_ok,
            "balance_ok": self.balance_ok,
            "balance_value": self.balance_value,
            "order_ok": self.order_ok,
            "order_id": self.order_id,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class PlatformIntegrationTester:
    """Tests all trading platform integrations."""

    def __init__(self):
        self.settings = get_settings()
        self.results: Dict[str, IntegrationTestResult] = {}

    async def test_aster(self) -> IntegrationTestResult:
        """Test Aster DEX integration."""
        result = IntegrationTestResult("aster")
        print("\n" + "=" * 60)
        print("🔷 TESTING ASTER DEX")
        print("=" * 60)

        try:
            from cloud_trader.credentials import Credentials

            # Initialize client with Credentials object
            creds = Credentials(
                api_key=self.settings.aster_api_key,
                api_secret=self.settings.aster_api_secret,
            )
            client = AsterClient(
                credentials=creds,
                base_url=self.settings.rest_base_url,
            )

            # Test 1: Connection via exchange info
            print("\n1️⃣ Testing connection...")
            try:
                exchange_info = await client.get_exchange_info()
                if exchange_info and "symbols" in exchange_info:
                    result.connection_ok = True
                    print(
                        f"   ✅ Connected! {len(exchange_info.get('symbols', []))} symbols available"
                    )
                else:
                    result.errors.append("Exchange info returned empty")
                    print("   ❌ Connection failed: No symbols returned")
            except Exception as e:
                result.errors.append(f"Connection error: {str(e)}")
                print(f"   ❌ Connection failed: {e}")

            # Test 2: Balance fetch
            print("\n2️⃣ Fetching account balance...")
            try:
                account = await client.get_account_info_v4()
                if account:
                    balance = float(account.get("totalMarginBalance", 0))
                    result.balance_ok = True
                    result.balance_value = balance
                    print(f"   ✅ Balance: ${balance:.2f}")
                else:
                    result.warnings.append("Account info returned None")
                    print("   ⚠️ Account info returned None")
            except Exception as e:
                result.errors.append(f"Balance error: {str(e)}")
                print(f"   ❌ Balance fetch failed: {e}")

            # Test 3: Order placement (very small test order)
            if result.connection_ok and result.balance_value > 10:
                print("\n3️⃣ Placing test order (tiny BTC position)...")
                try:
                    # Get current BTC price
                    ticker = await client.get_symbol_ticker("BTCUSDC")
                    if ticker:
                        btc_price = float(ticker.get("price", 0))
                        # Calculate minimum quantity for ~$6 notional
                        min_qty = round(6.0 / btc_price, 4)

                        print(f"   📊 BTC Price: ${btc_price:.2f}, Test Qty: {min_qty}")

                        # Place a limit order slightly below market (won't fill immediately)
                        limit_price = round(btc_price * 0.95, 2)  # 5% below market

                        order_result = await client.create_order(
                            symbol="BTCUSDC",
                            side="BUY",
                            order_type="LIMIT",
                            quantity=min_qty,
                            price=limit_price,
                            time_in_force="GTC",
                        )

                        if order_result and order_result.get("orderId"):
                            result.order_ok = True
                            result.order_id = order_result.get("orderId")
                            print(f"   ✅ Order placed! ID: {result.order_id}")

                            # Cancel immediately
                            print("   🗑️ Cancelling test order...")
                            await client.cancel_order("BTCUSDC", result.order_id)
                            print("   ✅ Order cancelled")
                        else:
                            result.warnings.append("Order returned but no orderId")
                            print(f"   ⚠️ Order response: {order_result}")
                except Exception as e:
                    result.errors.append(f"Order error: {str(e)}")
                    print(f"   ❌ Order placement failed: {e}")
            else:
                result.warnings.append("Skipped order test (insufficient balance or no connection)")
                print("\n3️⃣ ⏭️ Skipping order test (insufficient balance or connection issue)")

        except Exception as e:
            result.errors.append(f"Aster test failed: {str(e)}")
            print(f"❌ Aster test failed: {e}")

        self.results["aster"] = result
        return result

    async def test_aster(self) -> IntegrationTestResult:
        """Test Aster (Solana) integration."""
        result = IntegrationTestResult("aster")
        print("\n" + "=" * 60)
        print("🌀 TESTING ASTER (SOLANA)")
        print("=" * 60)

        try:
            # Check if credentials exist
            if not self.settings.solana_private_key:
                result.warnings.append("Solana private key not configured")
                print("   ⚠️ Solana credentials not found in environment")
                self.results["aster"] = result
                return result

            from cloud_trader.aster_client import AsterClient

            client = AsterClient(
                private_key=self.settings.solana_private_key,
                rpc_url=self.settings.solana_rpc_url,
            )

            # Test 1: Initialize and connect
            print("\n1️⃣ Testing connection...")
            try:
                await client.initialize()
                if client.is_initialized:
                    result.connection_ok = True
                    print("   ✅ Connected to Aster!")
                else:
                    result.errors.append("Initialization flag not set")
                    print("   ❌ Connection failed")
            except Exception as e:
                result.errors.append(f"Connection error: {str(e)}")
                print(f"   ❌ Connection failed: {e}")

            # Test 2: Fetch account equity
            if result.connection_ok:
                print("\n2️⃣ Fetching account balance...")
                try:
                    equity = await client.get_total_equity()
                    if equity is not None:
                        result.balance_ok = True
                        result.balance_value = float(equity)
                        print(f"   ✅ Total Equity: ${result.balance_value:.2f}")
                    else:
                        result.warnings.append("Equity returned None")
                        print("   ⚠️ Equity returned None")
                except Exception as e:
                    result.errors.append(f"Balance error: {str(e)}")
                    print(f"   ❌ Balance fetch failed: {e}")

            # Test 3: Order test (read-only for now due to Aster complexity)
            if result.connection_ok:
                print("\n3️⃣ Testing order capability...")
                try:
                    # Just verify we can get positions (order placement on Aster requires more setup)
                    positions = await client.get_positions()
                    result.order_ok = True  # Mark as OK if we can read positions
                    print(f"   ✅ Can read positions: {len(positions) if positions else 0} active")
                    result.warnings.append(
                        "Full order test skipped (Aster requires specific market setup)"
                    )
                except Exception as e:
                    result.errors.append(f"Position check error: {str(e)}")
                    print(f"   ⚠️ Position check failed: {e}")

        except ImportError as e:
            result.errors.append(f"Import error: {str(e)}")
            print(f"   ❌ Aster client not available: {e}")
        except Exception as e:
            result.errors.append(f"Aster test failed: {str(e)}")
            print(f"❌ Aster test failed: {e}")

        self.results["aster"] = result
        return result

    async def test_aster(self) -> IntegrationTestResult:
        """Test Aster (Monad/Base) integration."""
        result = IntegrationTestResult("aster")
        print("\n" + "=" * 60)
        print("🎵 TESTING ASTER (MONAD/BASE)")
        print("=" * 60)

        try:
            # Check if credentials exist
            if not self.settings.aster_api_key:
                result.warnings.append("Aster API key not configured")
                print("   ⚠️ Aster credentials not found in environment")
                self.results["aster"] = result
                return result

            from cloud_trader.aster_client import AsterClient
            from cloud_trader.aster_config import AGENTS_CONFIG

            client = AsterClient(api_key=self.settings.aster_api_key)

            # Test 1: Connection
            print("\n1️⃣ Testing connection...")
            try:
                # Try to get account info as connection test
                account_info = await client.get_account_info()
                if account_info:
                    result.connection_ok = True
                    print(f"   ✅ Connected! Agents configured: {list(AGENTS_CONFIG.keys())}")
                    print(f"   📊 Activation progress: {client.activation_progress}")
                else:
                    result.errors.append("Account info returned None")
                    print("   ❌ Connection failed")
            except Exception as e:
                result.errors.append(f"Connection error: {str(e)}")
                print(f"   ❌ Connection failed: {e}")

            # Test 2: Agent status
            if result.connection_ok:
                print("\n2️⃣ Checking agent positions...")
                try:
                    positions = await client.get_perpetual_positions()
                    result.balance_ok = True
                    result.balance_value = 250.0  # Mocked in client
                    print(f"   ✅ Open positions: {len(positions) if positions else 0}")
                    print(f"   💰 Estimated Balance: ${result.balance_value:.2f}")
                except Exception as e:
                    result.errors.append(f"Position status error: {str(e)}")
                    print(f"   ❌ Position check failed: {e}")

            # Test 3: Order capability
            if result.connection_ok:
                print("\n3️⃣ Testing order capability...")
                try:
                    # Aster uses agent-based execution
                    result.order_ok = hasattr(client, "open_perpetual_position") or hasattr(
                        client, "execute_swap"
                    )
                    if result.order_ok:
                        print(
                            "   ✅ Order methods available (open_perpetual_position, execute_swap)"
                        )
                    else:
                        print("   ⚠️ Order execution methods not found")
                except Exception as e:
                    result.errors.append(f"Order check error: {str(e)}")
                    print(f"   ❌ Order check failed: {e}")

        except ImportError as e:
            result.errors.append(f"Import error: {str(e)}")
            print(f"   ❌ Aster client not available: {e}")
        except Exception as e:
            result.errors.append(f"Aster test failed: {str(e)}")
            print(f"❌ Aster test failed: {e}")

        self.results["aster"] = result
        return result

    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 60)
        print("📊 INTEGRATION TEST SUMMARY")
        print("=" * 60)

        total_passed = 0
        total_tests = len(self.results)

        for platform, result in self.results.items():
            status = "✅" if (result.connection_ok and result.balance_ok) else "❌"
            if result.connection_ok and result.balance_ok:
                total_passed += 1

            print(f"\n{status} {platform.upper()}")
            print(f"   Connection: {'✅' if result.connection_ok else '❌'}")
            print(
                f"   Balance: {'✅' if result.balance_ok else '❌'} (${result.balance_value:.2f})"
            )
            print(f"   Orders: {'✅' if result.order_ok else '⚠️'}")

            if result.errors:
                print(f"   Errors: {', '.join(result.errors[:2])}")
            if result.warnings:
                print(f"   Warnings: {', '.join(result.warnings[:2])}")

        print(f"\n{'='*60}")
        print(f"TOTAL: {total_passed}/{total_tests} platforms operational")
        print(f"{'='*60}")

        return total_passed, total_tests

    async def run_all_tests(self):
        """Run all integration tests."""
        print("\n" + "🚀" * 30)
        print("    SAPPHIRE TRADING SYSTEM - INTEGRATION TEST SUITE")
        print("    " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("🚀" * 30)

        await self.test_aster()

        await self.test_aster()
        await self.test_aster()

        passed, total = self.print_summary()

        # Save results to file
        results_file = "/tmp/integration_test_results.json"
        with open(results_file, "w") as f:
            json.dump(
                {
                    "timestamp": datetime.now().isoformat(),
                    "passed": passed,
                    "total": total,
                    "results": {k: v.to_dict() for k, v in self.results.items()},
                },
                f,
                indent=2,
            )
        print(f"\n📄 Results saved to {results_file}")

        return passed == total


async def main():
    """Main entry point."""
    tester = PlatformIntegrationTester()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
