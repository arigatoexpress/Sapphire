#!/usr/bin/env python3
"""
Symphony Spot Trading Activation Script (Monad).
Executes 5 spot swaps to activate the agent on Monad.

Per Docs: "Spot Trading is currently only active on Monad.
User's should start with $MON as their collateral asset"

Usage:
    python3 -m cloud_trader.scripts.activate_symphony_spot
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


async def main():
    print("🎵 SYMPHONY SPOT ACTIVATION (MONAD)")
    print("=" * 50)

    try:
        from cloud_trader.symphony_client import get_symphony_client

        agent_id = os.getenv("SYMPHONY_AGENT_ID")
        if not agent_id:
            print("❌ Error: SYMPHONY_AGENT_ID not set in environment")
            return

        client = get_symphony_client(agent_id=agent_id)
        print(f"🤖 Target Agent ID: {agent_id}")

        # Check current status
        progress = client.activation_progress
        print(f"📊 Current Progress: {progress['current']}/5 trades")

        if progress["activated"]:
            print("✅ Fund is already activated!")
            return

        trades_needed = 5 - progress["current"]
        print(f"📊 Trades Needed: {trades_needed}")
        print()

        # Spot swap configurations
        # Per docs: tokenIn=MON, tokenOut can be a token contract address
        # Example from docs: tokenOut="0x350035555e10d9afaf1566aaebfced5ba6c27777"
        # For activation, we can swap MON -> USDC and back

        # Common Monad token addresses (you may need to update these)
        MON = "MON"  # Native token
        USDC_MONAD = "USDC"  # Monad USDC symbol

        swaps = [
            ("MON", "USDC", 5),  # 5% MON -> USDC
            ("USDC", "MON", 5),  # 5% USDC -> MON
            ("MON", "USDC", 5),  # 5% MON -> USDC
            ("USDC", "MON", 5),  # 5% USDC -> MON
            ("MON", "USDC", 5),  # 5% MON -> USDC
        ]

        successful_trades = 0
        batch_ids = []

        for i, (token_in, token_out, weight) in enumerate(swaps[:trades_needed]):
            print(f"🔄 Swap {i + 1}/{trades_needed}: {weight}% {token_in} -> {token_out}...")

            try:
                result = await client.execute_swap(
                    token_in=token_in,
                    token_out=token_out,
                    weight=weight,
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

            except Exception as e:
                print(f"   ⚠️ FAILED: {e}")

        print()
        print("=" * 50)
        print(f"📊 RESULT: {successful_trades}/{trades_needed} swaps executed")
        print(f"📦 Batch IDs: {batch_ids}")

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
