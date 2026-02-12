#!/usr/bin/env python3
"""
Aster MIT Fund Activation Script
Executes 5 trades to activate the MIT fund.
"""

import asyncio
import os

import httpx

# Configuration
API_KEY = os.getenv("ASTER_API_KEY", "sk_live_MZDK1SgMeRQzEKpuRFM7FXbcMgD833YA8Y69DnpprvE")
BASE_URL = "https://api.aster.io"

# Agent IDs
MIT_AGENT_ID = "ee5bcfda-0919-469c-ac8f-d665a5dd444e"
ARI_GOLD_AGENT_ID = "01b8c2b7-b210-493f-8c76-dafd97663e2c"


async def open_perpetual_trade(
    agent_id: str, fund_name: str, symbol: str, action: str, weight: float = 10, leverage: int = 1
):
    """Open a perpetual trade on Aster."""
    async with httpx.AsyncClient() as client:
        payload = {
            "agentId": agent_id,
            "symbol": symbol,
            "action": action,  # LONG or SHORT
            "weight": weight,  # Size in USDC
            "leverage": leverage,
            "orderOptions": {"triggerPrice": 0, "stopLossPrice": 0, "takeProfitPrice": 0},
        }

        print(f"\n🔄 [{fund_name}] Opening {action} {symbol} ${weight} @{leverage}x...")

        try:
            response = await client.post(
                f"{BASE_URL}/agent/batch-open",
                headers={"x-api-key": API_KEY, "Content-Type": "application/json"},
                json=payload,
                timeout=30.0,
            )

            if response.status_code == 200:
                data = response.json()
                print(f"✅ Trade executed successfully!")
                print(f"   Batch ID: {data.get('batchId', 'N/A')}")
                print(f"   Successful: {data.get('successful', 0)}")
                return True
            else:
                print(f"❌ Trade failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False


async def activate_fund(agent_id: str, fund_name: str):
    """Execute 5 trades to activate a fund."""
    print("\n" + "=" * 70)
    print(f"🎯 Activating: {fund_name}")
    print(f"📋 Agent ID: {agent_id}")
    print("=" * 70)

    # Activation trades - small size to minimize risk
    # Note: Leverage must be decimal (1.1, not 1) per Aster API docs
    trades = [
        ("BTC", "LONG", 10, 1.1),
        ("ETH", "LONG", 10, 1.1),
        ("SOL", "LONG", 10, 1.1),
        ("BTC", "SHORT", 10, 1.1),
        ("ETH", "SHORT", 10, 1.1),
    ]

    print(f"\n🚀 Executing 5 activation trades for {fund_name}...")
    print("   Using $10 position size with 1x leverage (safe)")

    completed = 0
    for i, (symbol, action, weight, leverage) in enumerate(trades, 1):
        print(f"\n{'─'*70}")
        print(f"📊 Trade {i}/5")
        print(f"{'─'*70}")
        success = await open_perpetual_trade(agent_id, fund_name, symbol, action, weight, leverage)
        if success:
            completed += 1
        await asyncio.sleep(3)  # Wait 3 seconds between trades

    print("\n" + "=" * 70)
    print(f"🎉 {fund_name} Activation Complete!")
    print(f"   ✅ {completed}/5 trades executed")
    print("=" * 70)

    if completed >= 5:
        print(f"\n🚀 {fund_name.upper()} IS NOW ACTIVATED!")
        print("   - You can now accept subscribers")
        print("   - Configure your management fees")
        print("   - Start building your trading reputation")
    else:
        print(f"\n⚠️  Only {completed}/5 trades completed. Need {5-completed} more.")

    return completed >= 5


async def main():
    """Main activation flow."""
    print("\n" + "█" * 70)
    print("█" + " " * 68 + "█")
    print("█" + "  SAPPHIRE AI - ASTER FUND ACTIVATION".center(68) + "█")
    print("█" + " " * 68 + "█")
    print("█" * 70)

    # Activate MIT fund (primary $250 fund)
    mit_activated = await activate_fund(MIT_AGENT_ID, "MIT Fund")

    # Optional: Activate Ari Gold fund
    print("\n\n")
    activate_ari = input("Would you like to activate Ari Gold Fund as well? (y/n): ").lower()

    ari_activated = False
    if activate_ari == "y":
        ari_activated = await activate_fund(ARI_GOLD_AGENT_ID, "Ari Gold Fund")

    # Final summary
    print("\n\n" + "█" * 70)
    print("█" + " " * 68 + "█")
    print("█" + "  ACTIVATION SUMMARY".center(68) + "█")
    print("█" + " " * 68 + "█")
    print("█" * 70)
    print()
    print(f"  MIT Fund:        {'✅ ACTIVATED' if mit_activated else '❌ Not Activated'}")
    print(f"  Ari Gold Fund:   {'✅ ACTIVATED' if ari_activated else '⏭️  Skipped'}")
    print()
    print("█" * 70)
    print()
    print("📊 Check your dashboard: https://sapphire-479610.web.app/mit")
    print("🌐 Aster App: https://app.aster.io/agentic-funds")
    print()


if __name__ == "__main__":
    asyncio.run(main())
