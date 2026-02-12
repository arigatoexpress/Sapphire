import asyncio
import logging
import os
import sys

# Configure basic logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("VerifyAgents")

# Load environment using python-dotenv if available
try:
    from dotenv import load_dotenv

    load_dotenv("local.env")
    logger.info("Loaded local.env")
except ImportError:
    pass


async def verify_aster():
    logger.info("--- Verifying Aster Agent ---")

    api_key = os.getenv("ASTER_API_KEY")
    if not api_key:
        logger.error("❌ ASTER_API_KEY not found in environment.")
        return False

    logger.info(f"✅ API Key found (Prefix: {api_key[:8]}...)")

    # Try Import
    try:
        from cloud_trader.aster_client import get_aster_client

        client = get_aster_client()

        # Test Connectivity
        logger.info("Testing connectivity to Aster API...")
        try:
            # Using get_account_info as a proxy for valid auth
            info = await client.get_account_info()
            logger.info(f"✅ Connection Successful. Account Info: {info}")
            await client.close()
            return True
        except Exception as e:
            logger.error(f"❌ Connection/Auth Failed: {e}")
            await client.close()
            return False

    except Exception as e:
        logger.error(f"❌ Failed to import/init AsterClient: {e}")
        return False


async def verify_aster():
    logger.info("\n--- Verifying Aster Agent (Solana) ---")

    private_key = os.getenv("SOLANA_PRIVATE_KEY")
    rpc_url = os.getenv("SOLANA_RPC_URL")

    if not private_key:
        logger.warning("⚠️ SOLANA_PRIVATE_KEY not found. Aster will be Read-Only/Mocked.")
    else:
        logger.info("✅ Solana Private Key found.")

    logger.info(f"RPC URL: {rpc_url}")

    # Check Dependencies
    try:
        import asterpy
        import solana
        import solders

        logger.info(
            f"✅ Aster Dependencies Found: asterpy={asterpy.__version__}, solana={solana.__version__}"
        )
    except ImportError as e:
        logger.error(f"❌ Missing Dependency: {e}")
        logger.error("Run: pip install asterpy solana solders")
        return False

    # Try Client Init
    try:
        from cloud_trader.aster_client import get_aster_client

        client = get_aster_client()
        await client.initialize()

        if client.is_initialized:
            logger.info("✅ Aster Client Initialized Successfully (or via fallback).")
            # Retrieve Equity
            equity = await client.get_total_equity()
            logger.info(f"💰 Estimated Equity: ${equity}")
            await client.close()
            return True
        else:
            logger.warning("⚠️ Aster Client failed to initialize (likely auth/rpc issue).")
            await client.close()
            return False

    except Exception as e:
        logger.error(f"❌ Aster Verification Error: {e}")
        return False


async def verify_lighter():
    logger.info("\n--- Verifying Lighter Agent ---")

    address = os.getenv("HL_ACCOUNT_ADDRESS")
    secret = os.getenv("HL_SECRET_KEY")

    if not address or not secret:
        logger.error("❌ Lighter Credentials missing (HL_ACCOUNT_ADDRESS / HL_SECRET_KEY).")
        return False

    logger.info(f"✅ Credentials found for: {address}")

    try:
        from cloud_trader.lighter_client import LighterClient

        client = LighterClient()
        success = await client.initialize()

        if success:
            logger.info("✅ Lighter Client Initialized.")
            # summary = await client.get_account_summary()
            # logger.info(f"📊 Account Summary Fetched: {bool(summary)}")
            return True
        else:
            logger.error("❌ Lighter Initialization Failed.")
            return False

    except ImportError:
        logger.error("❌ Lighter SDK not installed (lighter-python-sdk).")
        return False
    except Exception as e:
        logger.error(f"❌ Lighter Error: {e}")
        return False


async def verify_jupiter():
    logger.info("\n--- Verifying Jupiter Agent ---")

    # Jupiter does not strictly require an API Key for public endpoints, but good to check if set
    api_key = os.getenv("JUPITER_API_KEY")
    if api_key:
        logger.info("✅ JUPITER_API_KEY found.")
    else:
        logger.info("ℹ️ No JUPITER_API_KEY found (using public tier).")

    try:
        from cloud_trader.jupiter_client import get_jupiter_client

        client = get_jupiter_client()

        # Fetch tokens as connectivity test
        tokens = await client.get_tokens(tags=["verified"])
        if tokens:
            logger.info(f"✅ Connectivity Successful. Fetched {len(tokens)} verified tokens.")

            # Fetch Price
            price = await client.get_price("SOL")
            logger.info(f"💰 Current SOL Price via Jupiter: ${price}")
            return True
        else:
            logger.error("❌ Failed to fetch Jupiter tokens.")
            return False

    except Exception as e:
        logger.error(f"❌ Jupiter Error: {e}")
        return False


async def main():
    print("========================================")
    print("   Sapphire Agent Verification Tool     ")
    print("========================================")

    aster_ok = await verify_aster()
    aster_ok = await verify_aster()
    hl_ok = await verify_lighter()
    jup_ok = await verify_jupiter()

    print("\n========================================")
    print("              RESULTS                   ")
    print("========================================")
    print(f"Aster:    {'✅ PASS' if aster_ok else '❌ FAIL (Auth/Env)'}")
    print(f"Aster:       {'✅ PASS' if aster_ok else '⚠️ PARTIAL (Mock/Auth)'}")
    print(f"Lighter: {'✅ PASS' if hl_ok else '❌ FAIL (Auth/Env)'}")
    print(f"Jupiter:     {'✅ PASS' if jup_ok else '❌ FAIL'}")
    print("========================================")


if __name__ == "__main__":
    asyncio.run(main())
