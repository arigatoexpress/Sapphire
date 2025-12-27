import asyncio
import os
import sys
import time
from datetime import datetime

# Enumerate Connections
CONNECTIONS = ["Symphony (Monad)", "Drift Protocol", "Jupiter DEX", "Database (Local FS)"]


async def check_symphony():
    print(f"\n🎵 Checking Symphony (Monad)...")
    start = time.time()
    try:
        from cloud_trader.symphony_client import get_symphony_client

        client = get_symphony_client()

        # 1. Connection/Auth (Read)
        progress = client.activation_progress
        print(f"   ✅ Auth: Connected (Trades: {progress['current']}/5)")

        # 2. Agent Connectivity
        positions = await client.get_perpetual_positions()
        print(f"   ✅ Read: Fetched {len(positions)} positions")

        # 3. Monad Specifics
        agent_id = client.agent_id or "Not Set"
        print(f"   🤖 Agent ID: {agent_id}")

        latency = (time.time() - start) * 1000
        return True, f"{latency:.0f}ms", None
    except Exception as e:
        return False, "0ms", str(e)


async def check_drift():
    print(f"\n🌊 Checking Drift Protocol...")
    start = time.time()
    try:
        from cloud_trader.drift_client import get_drift_client

        client = get_drift_client()

        # 1. Price Feed (Read)
        # DriftClient has get_perp_market -> returns dict with oracle_price
        market = await client.get_perp_market("SOL-PERP")
        price = market.get("oracle_price", 0.0)
        print(f"   ✅ Oracle: SOL-PERP @ ${price:.2f}")

        # 2. Market Info
        print(f"   ✅ Market: Connected (Funding: {market.get('funding_rate_24h', 0)*100:.4f}%)")

        latency = (time.time() - start) * 1000
        return True, f"{latency:.0f}ms", None
    except Exception as e:
        return False, "0ms", str(e)


async def check_jupiter():
    print(f"\n🪐 Checking Jupiter DEX...")
    start = time.time()
    try:
        from cloud_trader.jupiter_client import get_jupiter_client

        client = get_jupiter_client()

        # 1. Quote API
        token_a = "So11111111111111111111111111111111111111112"  # SOL
        # JupiterClient.get_price returns a float directly
        price = await client.get_price(token_a)
        print(f"   ✅ Price API: SOL @ ${price:.2f}")

        if price <= 0:
            return False, "0ms", "Price came back as 0.00 (DNS/Network Error)"

        latency = (time.time() - start) * 1000
        return True, f"{latency:.0f}ms", None
    except Exception as e:
        return False, "0ms", str(e)


async def check_database():
    print(f"\n💾 Checking Database (FileSystem)...")
    start = time.time()
    try:
        # Check permissions and existing files
        trades_path = "/tmp/logs/trades.json"

        # Read
        if os.path.exists(trades_path):
            size = os.path.getsize(trades_path)
            print(f"   ✅ Read: trades.json exists ({size} bytes)")
        else:
            print(f"   ⚠️ Read: trades.json not found (Fresh start)")

        # Write Test
        test_path = "/tmp/logs/health_check.tmp"
        os.makedirs(os.path.dirname(test_path), exist_ok=True)
        with open(test_path, "w") as f:
            f.write("health_check_ok")
        os.remove(test_path)
        print(f"   ✅ Write: Permissions OK")

        latency = (time.time() - start) * 1000
        return True, f"{latency:.0f}ms", None
    except Exception as e:
        return False, "0ms", str(e)


async def main():
    print("🏥 SAPPHIRE SYSTEM HEALTH CHECK")
    print("=" * 40)

    results = []

    # Run Checks
    results.append(("Symphony", await check_symphony()))
    results.append(("Drift", await check_drift()))
    results.append(("Jupiter", await check_jupiter()))
    results.append(("Database", await check_database()))

    print("\n" + "=" * 40)
    print("📢 FINAL REPORT")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 40)

    all_passed = True
    for name, (success, latency, error) in results:
        status = "✅ PASS" if success else "❌ FAIL"
        error_msg = f"- {error}" if error else ""
        print(f"{status} | {name:<15} | {latency:<6} {error_msg}")
        if not success:
            all_passed = False

    if all_passed:
        print("\n✨ SYSTEM PRISTINE AND FULLY OPERATIONAL ✨")
    else:
        print("\n⚠️ SYSTEM ACTIONS REQUIRED")


if __name__ == "__main__":
    # Ensure project root in path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    asyncio.run(main())
