#!/usr/bin/env python3
"""Test Aster API authentication with different secret encodings."""

import base64
import hashlib
import hmac
import json
import sys
from typing import Dict, Any

import httpx


def test_signature(api_key: str, api_secret: str, encoding: str = "plain") -> Dict[str, Any]:
    """Test Aster API with different secret encodings."""

    # Handle different encodings
    if encoding == "base64":
        try:
            api_secret = base64.b64decode(api_secret).decode('utf-8')
            print("✓ Base64 decoded secret successfully")
        except Exception as e:
            print(f"✗ Base64 decode failed: {e}")
            return {"error": str(e)}
    elif encoding == "hex":
        try:
            api_secret = bytes.fromhex(api_secret).decode('utf-8')
            print("✓ Hex decoded secret successfully")
        except Exception as e:
            print(f"✗ Hex decode failed: {e}")
            return {"error": str(e)}

    # Test signature generation
    timestamp = "1234567890000"  # Fixed timestamp for testing
    params = {"timestamp": timestamp}

    # Method 1: Query string only (current implementation)
    query1 = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    sig1 = hmac.new(api_secret.encode(), query1.encode(), hashlib.sha256).hexdigest()

    # Method 2: Include method and path
    method = "GET"
    path = "/fapi/v2/account"
    message2 = f"{method}{path}{query1}".encode()
    sig2 = hmac.new(api_secret.encode(), message2, hashlib.sha256).hexdigest()

    # Method 3: JSON body style
    message3 = json.dumps(params, separators=(',', ':'), sort_keys=True).encode()
    sig3 = hmac.new(api_secret.encode(), message3, hashlib.sha256).hexdigest()

    print(f"\nTesting {encoding} encoding:")
    print(f"  Query string: {query1}")
    print(f"  Signature 1 (query only): {sig1}")
    print(f"  Signature 2 (method+path+query): {sig2}")
    print(f"  Signature 3 (JSON): {sig3}")

    # Try actual API call with method 1
    try:
        client = httpx.Client(base_url="https://fapi.asterdex.com", timeout=10.0)

        # Get server time first
        time_resp = client.get("/fapi/v1/time")
        server_time = time_resp.json()["serverTime"]

        # Build auth params with real timestamp
        auth_params = {"timestamp": server_time}
        auth_query = "&".join(f"{k}={v}" for k, v in sorted(auth_params.items()))
        auth_params["signature"] = hmac.new(api_secret.encode(), auth_query.encode(), hashlib.sha256).hexdigest()

        # Make authenticated request
        headers = {"X-MBX-APIKEY": api_key}
        resp = client.get("/fapi/v2/account", params=auth_params, headers=headers)

        print(f"\n  API Response: {resp.status_code}")
        if resp.status_code == 200:
            print(f"  ✓ SUCCESS with {encoding} encoding!")
            return {"success": True, "encoding": encoding, "data": resp.json()}
        else:
            print(f"  ✗ Failed: {resp.text}")
            return {"success": False, "encoding": encoding, "error": resp.text}

    except Exception as e:
        print(f"  ✗ Request failed: {e}")
        return {"success": False, "encoding": encoding, "error": str(e)}
    finally:
        if 'client' in locals():
            client.close()


def main():
    """Test different secret encodings."""

    # Get credentials from environment or command line
    if len(sys.argv) == 3:
        api_key = sys.argv[1]
        api_secret = sys.argv[2]
    else:
        # Try to get from gcloud secrets
        print("Fetching credentials from Secret Manager...")
        try:
            import subprocess
            api_key = subprocess.check_output(
                ["gcloud", "secrets", "versions", "access", "latest", "--secret", "ASTER_API_KEY"],
                text=True
            ).strip()
            api_secret = subprocess.check_output(
                ["gcloud", "secrets", "versions", "access", "latest", "--secret", "ASTER_SECRET_KEY"],
                text=True
            ).strip()
            print("✓ Retrieved credentials from Secret Manager")
        except Exception as e:
            print(f"✗ Failed to get secrets: {e}")
            print("\nUsage: python test_aster_auth.py <api_key> <api_secret>")
            sys.exit(1)

    print(f"\nAPI Key: {api_key[:10]}...{api_key[-4:]}")
    print(f"Secret length: {len(api_secret)} chars")

    # Test different encodings
    results = []

    # Test 1: Plain text
    results.append(test_signature(api_key, api_secret, "plain"))

    # Test 2: Base64 encoded
    results.append(test_signature(api_key, api_secret, "base64"))

    # Test 3: Hex encoded
    results.append(test_signature(api_key, api_secret, "hex"))

    # Summary
    print("\n" + "=" * 50)
    print("SUMMARY:")
    for result in results:
        if result.get("success"):
            print(f"✓ {result['encoding']} encoding WORKS!")
            break
    else:
        print("✗ None of the encoding methods worked")
        print("\nPossible issues:")
        print("1. API credentials might be incorrect")
        print("2. IP might not be whitelisted correctly")
        print("3. Different signature algorithm needed")


if __name__ == "__main__":
    main()

