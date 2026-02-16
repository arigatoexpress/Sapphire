import asyncio
import os
import sys
import time

# Ensure we can import modules
sys.path.append(os.getcwd())

from cloud_trader.vertex_ai_client import VertexAIClient


async def test_ai_caching():
    print("🧪 Testing AI Caching Upgrade...")
    client = VertexAIClient()

    # Enable API key mode if present (or mock it)
    # We just want to test the caching logic layer
    client._use_api_key = False

    # Mock settings to pass validation
    client._settings = type("Settings", (), {"enable_vertex_ai": True, "gemini_api_key": None})()

    client._initialized = True  # Force init for test

    # Mock the internal prediction method to avoid real API costs/errors during test
    async def mock_predict(*args, **kwargs):
        print("   🔄 (Simulating API Call - 500ms delay)")
        await asyncio.sleep(0.5)
        return {"confidence": 0.95, "response": "BUY", "metadata": {}}

    client._predict_with_vertex = mock_predict
    client._predict_with_api_key = mock_predict

    agent_id = "test-agent"
    prompt = "Analyze SOL-USDC"

    # Call 1: Should hit "API"
    print("\n1️⃣ First Call (Cold)...")
    start = time.time()
    res1 = await client.predict(agent_id, prompt)
    dur1 = time.time() - start
    print(f"   ⏱️ Duration: {dur1:.4f}s")

    if "cached" in res1.get("metadata", {}):
        print("❌ FAIL: First call was cached!")
        return

    # Call 2: Should hit Cache
    print("\n2️⃣ Second Call (Warm)...")
    start = time.time()
    res2 = await client.predict(agent_id, prompt)
    dur2 = time.time() - start
    print(f"   ⏱️ Duration: {dur2:.4f}s")

    if not res2.get("metadata", {}).get("cached"):
        print("❌ FAIL: Second call was NOT cached!")
    else:
        print(f"✅ SUCCESS: Second call cached! Age: {res2['metadata']['cache_age']:.4f}s")
        print(f"🚀 Speedup: {dur1/dur2:.1f}x faster")


if __name__ == "__main__":
    asyncio.run(test_ai_caching())
