#!/usr/bin/env python3
"""
Lighter Protocol - API Key Registration Script

Registers (or verifies) the Lighter API key on the Lighter ZK-rollup.

Usage:
    # If keys already exist in env (from GCP secrets):
    python scripts/register_lighter_key.py

    # Provide ETH wallet key to register new API key:
    ETH_PRIVATE_KEY=0x... python scripts/register_lighter_key.py

    # Generate fresh keys and register:
    python scripts/register_lighter_key.py --generate

Environment Variables:
    LIGHTER_PUB_KEY          - Existing API public key (hex)
    LIGHTER_PRIV_KEY         - Existing API private key (hex)
    ETH_PRIVATE_KEY          - L1 wallet private key (needed for registration)
    LIGHTER_ACCOUNT_INDEX    - Account index (default: 1)
    LIGHTER_API_KEY_INDEX    - API key index (default: 0)
    LIGHTER_BASE_URL         - API base URL (default: mainnet)
"""

import asyncio
import json
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = os.environ.get("LIGHTER_BASE_URL", "https://mainnet.zklighter.elliot.ai")
ACCOUNT_INDEX = int(os.environ.get("LIGHTER_ACCOUNT_INDEX", "1"))
API_KEY_INDEX = int(os.environ.get("LIGHTER_API_KEY_INDEX", "0"))


async def main():
    try:
        import lighter
    except ImportError:
        print("ERROR: lighter-sdk not installed. Run: pip install lighter-sdk")
        sys.exit(1)

    try:
        import eth_account as eth_acc_module
    except ImportError:
        print("ERROR: eth-account not installed. Run: pip install eth-account")
        sys.exit(1)

    generate = "--generate" in sys.argv
    eth_private_key = os.environ.get("ETH_PRIVATE_KEY")

    # Load existing keys from environment
    pub_key = os.environ.get("LIGHTER_PUB_KEY", "").strip()
    priv_key = os.environ.get("LIGHTER_PRIV_KEY", "").strip()

    print("=" * 60)
    print("  Lighter Protocol - API Key Registration")
    print("=" * 60)
    print(f"  Base URL:       {BASE_URL}")
    print(f"  Account Index:  {ACCOUNT_INDEX}")
    print(f"  API Key Index:  {API_KEY_INDEX}")
    print()

    # Step 1: Check if account exists
    api_client = lighter.ApiClient(
        configuration=lighter.Configuration(host=BASE_URL)
    )

    if eth_private_key:
        eth_acc = eth_acc_module.Account.from_key(eth_private_key)
        eth_address = eth_acc.address
        print(f"  Wallet Address: {eth_address}")
    else:
        eth_address = "0xAf72Ae447aD3dcdcDfBAA01bB9c7b3C37a031aAf"
        print(f"  Wallet Address: {eth_address} (from config)")

    print()

    # Look up account
    print("[1/5] Looking up account by L1 address...")
    try:
        response = await lighter.AccountApi(api_client).accounts_by_l1_address(
            l1_address=eth_address
        )
        if response.sub_accounts:
            for sa in response.sub_accounts:
                print(f"  Found account index: {sa.index}")
            account_index = ACCOUNT_INDEX
            print(f"  Using account index: {account_index}")
        else:
            print("  ERROR: No accounts found for this address.")
            print("  You need to create an account on https://lighter.xyz first.")
            await api_client.close()
            return
    except Exception as e:
        if "account not found" in str(e).lower():
            print(f"  ERROR: No Lighter account found for {eth_address}")
            print("  Create an account at https://lighter.xyz first.")
            await api_client.close()
            return
        raise

    # Step 2: Generate or use existing keys
    if generate or (not pub_key and not priv_key):
        print("\n[2/5] Generating new API key pair...")
        private_key, public_key, err = lighter.create_api_key()
        if err is not None:
            print(f"  ERROR: Failed to generate key: {err}")
            await api_client.close()
            return
        priv_key = private_key
        pub_key = public_key
        print(f"  Public Key:  {pub_key}")
        print(f"  Private Key: {priv_key[:16]}...")
        print()
        print("  SAVE THESE KEYS! Add to GCP Secret Manager:")
        print(f"    LIGHTER_PUB_KEY  = {pub_key}")
        print(f"    LIGHTER_PRIV_KEY = {priv_key}")
    else:
        print(f"\n[2/5] Using existing keys from environment")
        print(f"  Public Key: {pub_key[:20]}..." if pub_key else "  Public Key: MISSING")
        print(f"  Private Key: {priv_key[:16]}..." if priv_key else "  Private Key: MISSING")

    if not priv_key:
        print("\n  ERROR: No private key available. Set LIGHTER_PRIV_KEY or use --generate.")
        await api_client.close()
        return

    # Step 3: Try to create a SignerClient to test if key is already registered
    print(f"\n[3/5] Testing if key is already registered (index={API_KEY_INDEX})...")
    api_private_keys = {API_KEY_INDEX: priv_key}

    try:
        tx_client = lighter.SignerClient(
            url=BASE_URL,
            account_index=account_index,
            api_private_keys=api_private_keys,
        )

        err = tx_client.check_client()
        if err is None:
            print("  KEY IS ALREADY REGISTERED AND WORKING!")
            print()
            print("  Status: Ready to trade")
            print(f"  Account Index:  {account_index}")
            print(f"  API Key Index:  {API_KEY_INDEX}")
            await tx_client.close()
            await api_client.close()
            return
        else:
            print(f"  Key not yet registered: {err}")
    except Exception as e:
        print(f"  Key not yet registered: {e}")

    # Step 4: Register the key (requires ETH private key)
    print(f"\n[4/5] Registering API key on Lighter...")

    if not eth_private_key:
        print("  ERROR: ETH_PRIVATE_KEY required to register API key.")
        print("  This is the private key of your Ethereum wallet:")
        print(f"    {eth_address}")
        print()
        print("  Run with:")
        print(f"    ETH_PRIVATE_KEY=0x... python {sys.argv[0]}")
        await api_client.close()
        return

    try:
        tx_client = lighter.SignerClient(
            url=BASE_URL,
            account_index=account_index,
            api_private_keys=api_private_keys,
        )

        response, err = await tx_client.change_api_key(
            eth_private_key=eth_private_key,
            new_pubkey=pub_key,
            api_key_index=API_KEY_INDEX,
        )
        if err is not None:
            print(f"  ERROR: Registration failed: {err}")
            await tx_client.close()
            await api_client.close()
            return

        print(f"  Registration submitted! Response: {response}")
    except Exception as e:
        print(f"  ERROR: Registration failed: {e}")
        await api_client.close()
        return

    # Step 5: Verify registration
    print(f"\n[5/5] Waiting for registration to propagate (10s)...")
    time.sleep(10)

    try:
        err = tx_client.check_client()
        if err is None:
            print("  SUCCESS! API key is registered and verified.")
        else:
            print(f"  WARNING: Verification returned: {err}")
            print("  The key may take a few more seconds to propagate.")
    except Exception as e:
        print(f"  Verification error: {e}")

    print()
    print("=" * 60)
    print("  Registration Complete")
    print("=" * 60)
    print(f"  Account Index:  {account_index}")
    print(f"  API Key Index:  {API_KEY_INDEX}")
    print(f"  Public Key:     {pub_key}")
    print()
    print("  Ensure these secrets are in GCP Secret Manager:")
    print(f"    LIGHTER_PUB_KEY  = {pub_key}")
    print(f"    LIGHTER_PRIV_KEY = {priv_key}")
    print()

    await tx_client.close()
    await api_client.close()


if __name__ == "__main__":
    asyncio.run(main())
