#!/usr/bin/env python3
"""
Standalone Symphony Fund Activation Script.
Executes 5 trades to activate the Sapphire MIT Agent on Symphony.

Usage:
    python3 -m cloud_trader.scripts.activate_symphony
"""

import asyncio
import os
import sys

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


async def main():
    print("🎵 SYMPHONY FUND ACTIVATION SCRIPT")
    print("=" * 50)

    try:
        from cloud_trader.symphony_client import get_symphony_client

        # Load config
        agent_id = os.getenv("SYMPHONY_AGENT_ID")
        if not agent_id:
            print("❌ Error: SYMPHONY_AGENT_ID not set in environment")
            return

        client = get_symphony_client(agent_id=agent_id)
        print(f"🤖 Target Agent ID: {agent_id}")

        # Check current activation status
        progress = client.activation_progress
        print(f"📊 Current Progress: {progress['current']}/5 trades")
        print(f"📊 Percentage: {progress['percentage']:.1f}%")

        if progress["activated"]:
            print("✅ Fund is already activated!")
            return

        trades_needed = 5 - progress["current"]
        print(f"📊 Trades Needed: {trades_needed}")
        print()

        # Execute minimal trades to activate
        # Per docs: symbol is just "SOL", "BTC", "ETH" (not "BTC-USDC")
        # weight is 0-100 (% of collateral), minimum leverage is 1.1
        symbols = ["SOL", "BTC", "ETH", "SOL", "BTC"]
        actions = ["LONG", "SHORT", "LONG", "SHORT", "LONG"]

        successful_trades = 0
        batch_ids = []

        for i in range(min(trades_needed, 5)):
            symbol = symbols[i % len(symbols)]
            action = actions[i % len(actions)]

            print(f"🚀 Trade {i + 1}/{trades_needed}: {action} {symbol} (10% weight, 1.1x)...")

            try:
                result = await client.open_perpetual_position(
                    symbol=symbol,
                    action=action,
                    weight=10,  # 10% of collateral
                    leverage=1.1,  # Minimum per docs
                )

                if result.get("status") == "error":
                    print(f"   ⚠️ Error: {result.get('message')}")
                else:
                    batch_id = result.get("batchId")
                    successful_count = result.get("successful", 0)
                    print(f"   ✅ SUCCESS: batchId={batch_id}, successful={successful_count}")
                    if batch_id:
                        batch_ids.append(batch_id)
                    if successful_count > 0:
                        successful_trades += 1

            except Exception as trade_error:
                print(f"   ⚠️ FAILED: {trade_error}")

        print()
        print("=" * 50)
        print(f"📊 RESULT: {successful_trades}/{trades_needed} trades executed")

        # Final status
        final_progress = client.activation_progress
        print(f"📊 Final Progress: {final_progress['current']}/5 trades")
        print(f"📊 Activated: {final_progress['activated']}")

        if final_progress["activated"]:
            print("🎉 FUND ACTIVATED SUCCESSFULLY!")
        else:
            print(f"⏳ Need {5 - final_progress['current']} more trades")

    except Exception as e:
        print(f"❌ Activation failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
