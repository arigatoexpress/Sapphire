import asyncio
import json
import os

import httpx

# Configuration
API_KEY = os.getenv("SYMPHONY_API_KEY")
AGENT_ID = os.getenv("SYMPHONY_AGENT_ID")
BASE_URL = "https://api.symphony.io"


async def probe_agent():
    print("🕵️ PROBING AGENT AUTHENTICATION")
    print(f"🔑 Key Prefix: {API_KEY[:10]}...")
    print(f"🤖 Agent ID:   {AGENT_ID}")
    print("=" * 50)

    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        # Test 1: GET /agent/{id}
        print(f"\n1. GET /agent/{AGENT_ID}")
        try:
            resp = await client.get(f"{BASE_URL}/agent/{AGENT_ID}", headers=headers)
            print(f"   Status: {resp.status_code}")
            print(f"   Response: {resp.text[:200]}")
        except Exception as e:
            print(f"   ❌ Error: {e}")

        # Test 2: GET /agent/positions (with agent_id query param?)
        print(f"\n2. GET /agent/positions?agentId={AGENT_ID}")
        try:
            resp = await client.get(
                f"{BASE_URL}/agent/positions", params={"agentId": AGENT_ID}, headers=headers
            )
            print(f"   Status: {resp.status_code}")
            print(f"   Response: {resp.text[:200]}")
        except Exception as e:
            print(f"   ❌ Error: {e}")

        # Test 3: POST /trade/open (with agent_id in body)
        print(f"\n3. POST /trade/open (Dry Run - No Execution expected due to auth)")
        payload = {
            "symbol": "BTC-USDC",
            "side": "LONG",
            "size": 10,
            "leverage": 1,
            "agent_id": AGENT_ID,  # Speculative field
            "agentId": AGENT_ID,  # Speculative field
        }
        try:
            resp = await client.post(f"{BASE_URL}/trade/open", json=payload, headers=headers)
            print(f"   Status: {resp.status_code}")
            print(f"   Response: {resp.text[:200]}")
        except Exception as e:
            print(f"   ❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(probe_agent())
