import asyncio
import logging
import os
import sys
from typing import Any, Dict

from google.api_core import exceptions as google_exceptions
from google.cloud import firestore

# Add project root to path
sys.path.insert(0, os.getcwd())

try:
    from cloud_trader.agents.model_router import MultiModelRouter
    from cloud_trader.config import get_settings
except ImportError as e:
    print(f"❌ Error importing project modules: {e}")
    print("Run from project root: python3 cloud_trader/deep_diagnostics.py")
    sys.exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("DeepDiagnostics")


async def check_aster_connectivity(settings):
    print("\n🔍 Checking Aster Connection...")
    if not settings.aster_api_key or not settings.aster_api_secret:
        print("⚠️ Aster Credentials missing")
        return False

    try:
        # Manual signature generation and request to avoid importing missing client
        import hashlib
        import hmac
        import time

        import requests

        base_url = "https://fapi.asterdex.com"
        endpoint = "/fapi/v1/account"
        timestamp = int(time.time() * 1000)
        query_string = f"timestamp={timestamp}"

        signature = hmac.new(
            settings.aster_api_secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        headers = {"X-MBX-APIKEY": settings.aster_api_key}
        url = f"{base_url}{endpoint}?{query_string}&signature={signature}"

        print(f"   Testing authenticated call to {endpoint}...")
        response = requests.get(url, headers=headers, timeout=5)

        if response.status_code == 200:
            print("✅ Aster Authenticated Success")
            return True
        else:
            print(f"❌ Aster Failed: {response.status_code} - {response.text[:100]}")
            return False

    except Exception as e:
        print(f"❌ Aster Connection Failed: {e}")
        return False


async def check_firestore(settings):
    print("\n🔍 Checking Firestore...")
    if not settings.gcp_project_id:
        print("⚠️ GCP_PROJECT_ID settings missing")
        return False

    try:
        db = firestore.AsyncClient(project=settings.gcp_project_id)
        # Try to read a dummy document
        ref = db.collection("system_diagnostics").document("connectivity_check")
        await ref.set({"status": "ok", "timestamp": firestore.SERVER_TIMESTAMP})
        print("✅ Firestore Write Success")
        doc = await ref.get()
        print(f"✅ Firestore Read Success: {doc.to_dict()}")
        return True
    except Exception as e:
        print(f"❌ Firestore Failed: {e}")
        print("   (Check GOOGLE_APPLICATION_CREDENTIALS or gcloud auth)")
        return False


async def check_gemini(settings):
    print("\n🔍 Checking Gemini (LLM)...")
    if not settings.gemini_api_key:
        print("⚠️ GEMINI_API_KEY missing")
        return False

    try:
        router = MultiModelRouter()
        # Initialize internal clients manually if needed or rely on init
        # MultiModelRouter usually inits in __init__

        # We need to ensure it's using the settings passed
        # Currently MultiModelRouter loads settings internally in _initialize_clients

        response = await router.query("Hello, reply with 'OK'.")
        print(f"✅ Gemini Response: {response}")
        return True
    except Exception as e:
        print(f"❌ Gemini Failed: {e}")
        return False


async def run_diagnostics():
    print("==================================================")
    print("   SAPPHIRE V2 - DEEP SYSTEM DIAGNOSTICS")
    print("==================================================")

    settings = get_settings()
    # print(f"Environment: {settings.environment}")
    print(f"Project: {settings.gcp_project_id}")

    results = {
        "firestore": await check_firestore(settings),
        "gemini": await check_gemini(settings),
        "aster": await check_aster_connectivity(settings),
    }

    print("\n==================================================")
    print("   RESULTS")
    print("==================================================")
    all_pass = True
    for component, passing in results.items():
        status = "✅ PASS" if passing else "❌ FAIL"
        print(f"{component.ljust(15)}: {status}")
        if not passing:
            all_pass = False

    if not all_pass:
        print("\n⚠️ SYSTEM ISSUES DETECTED")
        sys.exit(1)
    else:
        print("\n✅ ALL SYSTEMS FUNCTIONAL")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(run_diagnostics())
