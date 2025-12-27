import asyncio
import os

import aiohttp

from cloud_trader.credentials import CredentialManager


async def run_diagnostics():
    print("\n🔐 STARTING STANDALONE AUTH DIAGNOSTICS...", flush=True)

    # Initialize Credential Manager
    try:
        cred_manager = CredentialManager()
        creds = cred_manager.get_credentials()
        api_key = creds.api_key
        secret = creds.api_secret

        if not api_key:
            print("   ❌ MISSING API KEY in CredentialManager!", flush=True)
        else:
            print(f"   🔑 Key Found: {api_key[:6]}... (Length: {len(api_key)})", flush=True)

        if not secret:
            print("   ❌ MISSING SECRET in CredentialManager!", flush=True)
        else:
            print(f"   🔑 Secret Found (Length: {len(secret)})", flush=True)

    except Exception as e:
        print(f"   ⚠️ Credential Load Failed: {e}", flush=True)
        return

    # 1. Check Public Data (No Auth)
    print("\n   1. Testing Public API (Time)...", flush=True)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://fapi.asterdex.com/fapi/v1/time", timeout=5.0) as resp:
                if resp.status == 200:
                    print("      ✅ Public API Accessible (200 OK)", flush=True)
                    text = await resp.text()
                    print(f"      🕒 Time: {text}", flush=True)
                else:
                    print(f"      ❌ Public API Blocked: {resp.status}", flush=True)
    except Exception as e:
        print(f"      ❌ Public API Network Error: {e}", flush=True)

    # 2. Check Private Data (Auth)
    print("\n   2. Testing Private API (Account)...", flush=True)
    try:
        from cloud_trader.exchange import AsterClient

        client = AsterClient(credentials=creds)

        # We need to run this in the loop
        print("      🚀 Sending Signed Request...", flush=True)
        account = await client.get_account_info_v4()

        if account:
            print(
                f"      ✅ SUCCESS! Account Balance: {account.get('totalMarginBalance', 'N/A')}",
                flush=True,
            )
            print("      🎉 THIS IP IS WHITELISTED AND KEY IS VALID!", flush=True)
        else:
            print("      ❌ Request failed (None returned)", flush=True)

    except Exception as e:
        print(f"      ❌ Private API Failed: {e}", flush=True)

    print("\n🔐 DIAGNOSTICS COMPLETE.", flush=True)


if __name__ == "__main__":
    asyncio.run(run_diagnostics())
