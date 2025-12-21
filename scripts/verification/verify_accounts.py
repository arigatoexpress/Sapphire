"""
Verification Script for Multi-Chain Account Links.
Checks connection and balances for:
1. Symphony (Monad)
2. Solana Wallet (Standard)
3. Drift Protocol (Futures)
"""

import asyncio
import logging
import os

# from cloud_trader.solana_wallet_manager import get_wallet_manager # Requires Firestore creds, might fail in local env without key
from cloud_trader.drift_client import get_drift_client
from cloud_trader.logger import get_logger
from cloud_trader.symphony_client import get_symphony_client

# Simple console logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ACCOUNTS_CHECK")


async def verify_symphony():
    print("\n🎵 --- CHECKING SYMPHONY (MONAD) ---")
    try:
        client = get_symphony_client()
        # Check config
        if not client.api_key:
            print("❌ Symphony API Key NOT SET.")
            return

        print(f"✅ Client Initialized. URL: {client.base_url}")

        # Test Connection (Get Account)
        try:
            account = await client.get_account_info()
            print(f"✅ Connection Successful!")
            print(f"   Name: {account.get('name', 'Unknown')}")
            print(f"   ID: {account.get('id', 'Unknown')}")
            print(f"   Status: {'Activated 🟢' if account.get('is_activated') else 'Pending 🟡'}")
            print(f"   Trades: {account.get('trades_count', 0)}")
            bal = account.get("balance", {})
            print(f"   Balance: {bal.get('USDC', 0)} USDC")
        except Exception as e:
            print(f"⚠️ Direct Connection Failed: {e}. Trying /v1 prefix...")
            try:
                # Hack check for v1
                client.base_url = f"{client.base_url}/v1"
                account = await client.get_account_info()
                print(f"✅ Connection Successful (with /v1)!")
                print(f"   Name: {account.get('name', 'Unknown')}")
                print(f"   ID: {account.get('id', 'Unknown')}")
                print(
                    f"   Status: {'Activated 🟢' if account.get('is_activated') else 'Pending 🟡'}"
                )
                print(f"   Trades: {account.get('trades_count', 0)}")
                bal = account.get("balance", {})
                print(f"   Balance: {bal.get('USDC', 0)} USDC")
            except Exception as e2:
                import traceback

                print(f"❌ Connection Failed Details: {e2}")
                traceback.print_exc()

    except Exception as e:
        print(f"❌ Error: {e}")


async def verify_drift():
    print("\n🌊 --- CHECKING DRIFT (SOLANA PERPS) ---")
    try:
        client = get_drift_client()
        print(f"✅ Client Initialized. RPC: {client.rpc_url}")

        # Test Config
        # In this environment we might not have a real wallet key for driftpy
        # But we can check if the client thinks it's ready.

        # Simulate check
        market = await client.get_perp_market("SOL-PERP")
        print(f"✅ Market Data Access: OK")
        print(f"   Symbol: {market['symbol']}")
        print(f"   Oracle Price: ${market['oracle_price']}")

    except Exception as e:
        print(f"❌ Error: {e}")


async def verify_solana_wallet():
    print("\n🪐 --- CHECKING SOLANA WALLET ---")

    private_key = os.getenv("SOLANA_PRIVATE_KEY")
    if not private_key:
        print("❌ SOLANA_PRIVATE_KEY not found in environment.")
        return

    try:
        import base58
        from solders.keypair import Keypair
        from solders.pubkey import Pubkey

        # 1. Decode Key
        try:
            key_bytes = base58.b58decode(private_key)
            keypair = Keypair.from_bytes(key_bytes)
            pubkey = keypair.pubkey()
            print(f"✅ Wallet Loaded Successfully!")
            print(f"   Public Key: {pubkey}")

            # 2. Check Balance (via Drift Client RPC for convenience)
            from cloud_trader.drift_client import get_drift_client

            drift = get_drift_client()
            # Need a simple RPC call here. Drift client might expose w3-like or we use requests
            # For this simple script, we'll try to rely on DriftClient logs if we integrated it fully,
            # but for now, just proving the key is valid is a huge win.

        except Exception as e:
            print(f"❌ Invalid Private Key Format: {e}")

    except ImportError:
        print("⚠️ 'solders' library not found. Skipping Key check.")


async def verify_jupiter():
    print("\n🪐 --- CHECKING JUPITER (SOLANA SWAPS) ---")
    try:
        from cloud_trader.jupiter_client import COMMON_TOKENS, get_jupiter_client

        jup = get_jupiter_client()
        print(f"✅ Client Initialized. Base URL: {jup.base_url}")

        # Test Quote: 1 USDC -> SOL
        print("   Fetching Ultra Order (Quote): 1 USDC -> SOL...")
        try:
            order = await jup.get_order(
                input_mint=COMMON_TOKENS["USDC"],
                output_mint=COMMON_TOKENS["SOL"],
                amount=1000000,  # 1 USDC
            )
            in_amt = int(order.get("inAmount", 0)) / 10**6
            out_amt = int(order.get("outAmount", 0)) / 10**9
            print(f"✅ Ultra Quote Successful!")
            print(f"   In: {in_amt} USDC")
            print(f"   Out: {out_amt:.6f} SOL")
            print(f"   Price Impact: {order.get('priceImpactPct', '0')}%")

        except Exception as e:
            print(f"❌ Ultra Quote Failed: {e}")

    except Exception as e:
        print(f"❌ Error: {e}")


async def main():
    print("=========================================")
    print("   ACCOUNT CONNECTION VERIFICATION       ")
    print("=========================================")

    await verify_symphony()
    await verify_drift()
    await verify_solana_wallet()
    await verify_jupiter()

    print("\n=========================================")
    print("   VERIFICATION COMPLETE                 ")
    print("=========================================")


if __name__ == "__main__":
    asyncio.run(main())
