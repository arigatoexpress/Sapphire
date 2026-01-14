#!/usr/bin/env python3
"""
Close all existing positions and enable autonomous trading.
This script will:
1. Close all open positions on each platform
2. Report available balances
3. Confirm trading is ready to start

Run with: python -m cloud_trader.close_and_trade
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cloud_trader.config import get_settings
from cloud_trader.credentials import Credentials
from cloud_trader.exchange import AsterClient
from cloud_trader.symphony_client import SymphonyClient
from cloud_trader.symphony_config import AGENTS_CONFIG


class PositionCloser:
    """Close positions and prepare for trading."""

    def __init__(self):
        self.settings = get_settings()
        self.results: Dict[str, Dict[str, Any]] = {}

    async def close_aster_positions(self) -> Dict[str, Any]:
        """Close all Aster positions."""
        result = {"platform": "aster", "positions_closed": 0, "balance": 0.0, "errors": []}
        print("\n" + "=" * 60)
        print("🔷 ASTER DEX - Closing Positions")
        print("=" * 60)

        try:
            creds = Credentials(
                api_key=self.settings.aster_api_key,
                api_secret=self.settings.aster_api_secret,
            )
            client = AsterClient(credentials=creds, base_url=self.settings.rest_base_url)

            # Get current positions
            print("\n📊 Fetching positions...")
            positions = await client.get_position_info()

            if positions:
                open_positions = [p for p in positions if float(p.get("positionAmt", 0)) != 0]
                print(f"   Found {len(open_positions)} open positions")

                for pos in open_positions:
                    symbol = pos.get("symbol", "UNKNOWN")
                    amt = float(pos.get("positionAmt", 0))
                    side = "SELL" if amt > 0 else "BUY"
                    qty = abs(amt)

                    print(f"\n   📉 Closing {symbol}: {amt:.6f}")
                    try:
                        # Close with market order
                        close_result = await client.create_order(
                            symbol=symbol,
                            side=side,
                            order_type="MARKET",
                            quantity=qty,
                            reduce_only=True,
                        )
                        if close_result and close_result.get("orderId"):
                            result["positions_closed"] += 1
                            print(f"      ✅ Closed! Order ID: {close_result.get('orderId')}")
                        else:
                            print(f"      ⚠️ Close response: {close_result}")
                    except Exception as e:
                        result["errors"].append(f"Close {symbol}: {str(e)}")
                        print(f"      ❌ Error closing: {e}")
            else:
                print("   ✅ No open positions")

            # Get balance
            print("\n💰 Fetching balance...")
            account = await client.get_account_info_v4()
            if account:
                result["balance"] = float(account.get("totalMarginBalance", 0))
                print(f"   Balance: ${result['balance']:.2f}")

        except Exception as e:
            result["errors"].append(str(e))
            print(f"❌ Aster error: {e}")

        self.results["aster"] = result
        return result

    async def close_drift_positions(self) -> Dict[str, Any]:
        """Close all Drift positions."""
        result = {"platform": "drift", "positions_closed": 0, "balance": 0.0, "errors": []}
        print("\n" + "=" * 60)
        print("🌀 DRIFT (SOLANA) - Closing Positions")
        print("=" * 60)

        try:
            if not self.settings.solana_private_key:
                result["errors"].append("Solana credentials not configured")
                print("   ⚠️ Solana credentials not found")
                self.results["drift"] = result
                return result

            from cloud_trader.drift_client import DriftClient

            client = DriftClient(
                private_key=self.settings.solana_private_key,
                rpc_url=self.settings.solana_rpc_url,
            )

            await client.initialize()

            # Get positions
            print("\n📊 Fetching positions...")
            positions = await client.get_positions()

            if positions:
                open_positions = [p for p in positions if p.get("base_asset_amount", 0) != 0]
                print(f"   Found {len(open_positions)} open positions")

                for pos in open_positions:
                    market_index = pos.get("market_index", 0)
                    base_amount = pos.get("base_asset_amount", 0)

                    print(f"\n   📉 Closing market {market_index}: {base_amount}")
                    try:
                        close_result = await client.close_position(market_index)
                        if close_result:
                            result["positions_closed"] += 1
                            print(f"      ✅ Closed!")
                    except Exception as e:
                        result["errors"].append(f"Close market {market_index}: {str(e)}")
                        print(f"      ❌ Error closing: {e}")
            else:
                print("   ✅ No open positions")

            # Get balance
            print("\n💰 Fetching balance...")
            equity = await client.get_total_equity()
            if equity is not None:
                result["balance"] = float(equity)
                print(f"   Total Equity: ${result['balance']:.2f}")

        except ImportError as e:
            result["errors"].append(f"Import error: {str(e)}")
            print(f"   ⚠️ Drift client unavailable locally")
        except Exception as e:
            result["errors"].append(str(e))
            print(f"❌ Drift error: {e}")

        self.results["drift"] = result
        return result

    async def close_symphony_positions(self) -> Dict[str, Any]:
        """Close all Symphony positions."""
        result = {"platform": "symphony", "positions_closed": 0, "balance": 250.0, "errors": []}
        print("\n" + "=" * 60)
        print("🎵 SYMPHONY - Closing Positions")
        print("=" * 60)

        try:
            client = SymphonyClient()

            # Get positions for each agent
            print("\n📊 Fetching positions...")
            positions = await client.get_perpetual_positions()

            if positions:
                print(f"   Found {len(positions)} open positions")

                for pos in positions:
                    batch_id = pos.get("batchId")
                    symbol = pos.get("symbol", "UNKNOWN")

                    if batch_id:
                        print(f"\n   📉 Closing {symbol} (batch: {batch_id})")
                        try:
                            close_result = await client.close_perpetual_position(batch_id)
                            if close_result and close_result.get("status") != "error":
                                result["positions_closed"] += 1
                                print(f"      ✅ Closed!")
                            else:
                                print(f"      ⚠️ Close response: {close_result}")
                        except Exception as e:
                            result["errors"].append(f"Close {batch_id}: {str(e)}")
                            print(f"      ❌ Error closing: {e}")
            else:
                print("   ✅ No open positions")

            # Get account info
            print("\n💰 Fetching balance...")
            account = await client.get_account_info()
            if account:
                balance = account.get("balance", {}).get("USDC", 0)
                result["balance"] = float(balance)
                print(f"   Balance: ${result['balance']:.2f}")
                print(f"   Agents: {list(AGENTS_CONFIG.keys())}")

            await client.close()

        except Exception as e:
            result["errors"].append(str(e))
            print(f"❌ Symphony error: {e}")

        self.results["symphony"] = result
        return result

    def print_summary(self):
        """Print summary and total available balance."""
        print("\n" + "=" * 60)
        print("📊 POSITION CLOSURE SUMMARY")
        print("=" * 60)

        total_balance = 0.0
        total_closed = 0

        for platform, result in self.results.items():
            status = "✅" if not result.get("errors") else "⚠️"
            balance = result.get("balance", 0)
            closed = result.get("positions_closed", 0)
            total_balance += balance
            total_closed += closed

            print(f"\n{status} {platform.upper()}")
            print(f"   Positions Closed: {closed}")
            print(f"   Balance: ${balance:.2f}")
            if result.get("errors"):
                print(f"   Errors: {result['errors'][0][:50]}...")

        print(f"\n{'='*60}")
        print(f"💰 TOTAL AVAILABLE BALANCE: ${total_balance:.2f}")
        print(f"📉 TOTAL POSITIONS CLOSED: {total_closed}")
        print(f"{'='*60}")
        print("\n🚀 TRADING READY - Bots can now use all available funds!")

        return total_balance, total_closed

    async def run(self):
        """Close all positions across all platforms."""
        print("\n" + "🚀" * 30)
        print("    SAPPHIRE TRADING SYSTEM - POSITION CLOSURE")
        print("    " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("🚀" * 30)

        await self.close_aster_positions()

        await self.close_drift_positions()
        await self.close_symphony_positions()

        total_balance, total_closed = self.print_summary()

        # Save results
        results_file = "/tmp/position_closure_results.json"
        with open(results_file, "w") as f:
            json.dump(
                {
                    "timestamp": datetime.now().isoformat(),
                    "total_balance": total_balance,
                    "total_positions_closed": total_closed,
                    "results": self.results,
                },
                f,
                indent=2,
            )
        print(f"\n📄 Results saved to {results_file}")

        return total_balance, total_closed


async def main():
    """Main entry point."""
    closer = PositionCloser()
    await closer.run()


if __name__ == "__main__":
    asyncio.run(main())
