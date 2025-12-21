#!/usr/bin/env python3
"""
Symphony MIT Fund Activation Script
Executes 5 trades to activate your Symphony fund.
"""

import asyncio
import os

import httpx

# Your Symphony API Key (set via environment variable)
API_KEY = os.getenv("SYMPHONY_API_KEY", "")
BASE_URL = "https://api.symphony.io"


async def get_agent_id():
    """Get your MIT agent ID."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/agent/all", headers={"x-api-key": API_KEY})
        if response.status_code == 200:
            agents = response.json()
            if agents:
                # Return first agent (should be your MIT fund)
                return agents[0].get("id") or agents[0].get("agentId")
        return None


async def open_perpetual_trade(
    agent_id: str, symbol: str, action: str, weight: float = 10, leverage: int = 1
):
    """Open a perpetual trade on Symphony."""
    async with httpx.AsyncClient() as client:
        payload = {
            "agentId": agent_id,
            "symbol": symbol,
            "action": action,  # LONG or SHORT
            "weight": weight,  # Size in USDC
            "leverage": leverage,
            "orderOptions": {"triggerPrice": 0, "stopLossPrice": 0, "takeProfitPrice": 0},
        }

        print(f"\n🔄 Opening {action} {symbol} ${weight} @{leverage}x...")

        response = await client.post(
            f"{BASE_URL}/agent/batch-open",
            headers={"x-api-key": API_KEY, "Content-Type": "application/json"},
            json=payload,
            timeout=30.0,
        )

        if response.status_code == 200:
            data = response.json()
            print(f"✅ Trade #{data.get('successful', 0)} executed successfully!")
            print(f"   Batch ID: {data.get('batchId', 'N/A')}")
            return True
        else:
            print(f"❌ Trade failed: {response.status_code} - {response.text}")
            return False


async def activate_mit_fund():
    """Execute 5 trades to activate MIT fund."""
    print("=" * 60)
    print("🎯 Symphony MIT Fund Activation")
    print("=" * 60)

    # Get agent ID
    print("\n📋 Fetching your agent ID...")
    agent_id = await get_agent_id()

    if not agent_id:
        print("❌ Could not find agent ID. Please check your API key.")
        print("Visit https://app.symphony.io/agentic-funds to see your funds.")
        return

    print(f"✅ Agent ID: {agent_id}")

    # Activation trades - small size to minimize risk
    trades = [
        ("BTC", "LONG", 10, 1),
        ("ETH", "LONG", 10, 1),
        ("SOL", "LONG", 10, 1),
        ("BTC", "SHORT", 10, 1),
        ("ETH", "SHORT", 10, 1),
    ]

    print(f"\n🚀 Executing 5 activation trades...")
    print("   Using $10 position size with 1x leverage (safe)")

    completed = 0
    for i, (symbol, action, weight, leverage) in enumerate(trades, 1):
        print(f"\n--- Trade {i}/5 ---")
        success = await open_perpetual_trade(agent_id, symbol, action, weight, leverage)
        if success:
            completed += 1
        await asyncio.sleep(2)  # Wait 2 seconds between trades

    print("\n" + "=" * 60)
    print(f"🎉 Activation Complete! {completed}/5 trades executed")
    print("=" * 60)

    if completed >= 5:
        print("\n✅ YOUR MIT FUND IS NOW ACTIVATED!")
        print("   - You can now accept subscribers")
        print("   - Configure your management fees")
        print("   - Start building your trading reputation")
        print(f"\n📊 Check your dashboard: https://sapphire-479610.web.app/mit")
    else:
        print(f"\n⚠️  Only {completed}/5 trades completed. Need {5-completed} more.")


if __name__ == "__main__":
    asyncio.run(activate_mit_fund())
