import json
import sys
import time

import requests

BASE_URL = "https://sapphire-v2-267358751314.us-central1.run.app"


def check(name, url, expected_status=200, json_key=None, expected_value=None):
    print(f"Checking {name}...", end=" ")
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != expected_status:
            print(f"❌ Failed: Status {r.status_code}")
            return False

        if json_key:
            data = r.json()
            val = data.get(json_key)
            if expected_value and val != expected_value:
                print(f"❌ Failed: {json_key}={val}, expected {expected_value}")
                return False
            if val is None:
                print(f"❌ Failed: Key {json_key} missing")
                return False

        print("✅ OK")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def verify():
    print(f"Target: {BASE_URL}")

    # 1. Health
    if not check("Health Check", f"{BASE_URL}/health", json_key="version", expected_value="2.1.0"):
        return False

    # 2. System Root
    if not check("System Root", f"{BASE_URL}/"):
        return False

    # 3. New Endpoint: Log System
    if not check("Log System", f"{BASE_URL}/logs/system?limit=5"):
        return False

    # 4. New Endpoint: Positions All
    if not check("Positions", f"{BASE_URL}/positions/all"):
        return False

    print("\n✅ Deployment Verification Successful!")
    return True


if __name__ == "__main__":
    for i in range(10):
        if verify():
            sys.exit(0)
        print("Retrying in 30s...")
        time.sleep(30)
    sys.exit(1)
