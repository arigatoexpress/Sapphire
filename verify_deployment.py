import json
import sys
import time

import requests

BASE_URL = "https://sapphire-cloud-trader-267358751314.europe-west1.run.app"
TIMEOUT = 30


def check_endpoint(endpoint):
    url = f"{BASE_URL}{endpoint}"
    print(f"📡 Checking {url}...", end=" ")
    try:
        start_time = time.time()
        response = requests.get(url, timeout=TIMEOUT)
        latency = (time.time() - start_time) * 1000

        if response.status_code == 200:
            print(f"✅ OK ({latency:.1f}ms)")
            return True, response.json()
        else:
            print(f"❌ FAILED (Status: {response.status_code})")
            print(f"   Response: {response.text[:200]}")
            return False, None
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False, None


def verify_system():
    print("🚀 STARTING SYSTEM VERIFICATION")
    print("=" * 40)

    # 1. Health Check
    success, health_data = check_endpoint("/health/detailed")
    if success:
        status = health_data.get("status", "unknown")
        print(f"   Health Status: {status}")

        # Check components
        components = health_data.get("components", {})
        platform_router = components.get("platform_router", {})
        if isinstance(platform_router, dict) and platform_router.get("overall_healthy"):
            print("   ✅ Platform Router: HEALTHY")
        else:
            print("   ⚠️ Platform Router: UNHEALTHY/DEGRADED")

    # 2. Dashboard Data
    success, dashboard_data = check_endpoint("/api/dashboard")
    if success:
        portfolio = dashboard_data.get("portfolio", {})
        agents = dashboard_data.get("agents", [])
        print(f"   Portfolio Value: {portfolio.get('portfolio_value', 0)}")
        print(f"   Active Agents: {len(agents)}")

        if len(agents) > 0:
            print("   ✅ Agents are ACTIVE")
        else:
            print("   ⚠️ No Agents Found")

    print("\n✅ VERIFICATION COMPLETE")


if __name__ == "__main__":
    verify_system()
